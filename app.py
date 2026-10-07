import streamlit as st
import os
import time
import json
import requests
from itertools import product as cartesian_product
from groq import Groq


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="SmartShop AI",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================================
# CSS
# =========================================================

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }

    .hero {
        padding: 2rem;
        border-radius: 22px;
        background: linear-gradient(135deg, #eef2ff, #f8fafc);
        border: 1px solid #e2e8f0;
        margin-bottom: 1.5rem;
    }

    .hero h1 {
        margin-bottom: .3rem;
    }

    .card {
        padding: 1.1rem;
        border-radius: 16px;
        border: 1px solid #e2e8f0;
        background: white;
        margin-bottom: .8rem;
    }

    .small-muted {
        color: #64748b;
        font-size: .9rem;
    }

    .score {
        font-size: 1.4rem;
        font-weight: 700;
    }

    .tag {
        display: inline-block;
        padding: .25rem .55rem;
        margin: .15rem;
        border-radius: 999px;
        background: #eef2ff;
        font-size: .78rem;
    }

    [data-testid="stSidebar"] {
        border-right: 1px solid #e2e8f0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# API CONFIGURATION
# =========================================================

def get_secret(name):
    """
    Reads API keys without crashing the website.
    """
    value = os.environ.get(name)

    if value:
        return value.strip()

    try:
        value = st.secrets.get(name, "")
        return str(value).strip() if value else ""
    except Exception:
        return ""


GROQ_API_KEY = get_secret("GROQ_API_KEY")
SERPAPI_API_KEY = get_secret("SERPAPI_API_KEY")

groq_client = None


def get_groq_client():
    global groq_client

    if groq_client is None and GROQ_API_KEY:
        try:
            groq_client = Groq(api_key=GROQ_API_KEY)
        except Exception:
            groq_client = None

    return groq_client


# =========================================================
# SESSION STATE
# =========================================================

defaults = {
    "products": [],
    "selected_ids": [],
    "comparison_ids": [],
    "saved_products": [],
    "search_history": [],
    "last_recommendation": None,
    "budget": 20000,
    "preferences": "",
    "categories": [],
    "last_search_message": "",
    "settings": {
        "max_results": 8,
        "currency": "INR (₹)",
        "ai_temperature": 0.1,
    },
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# GENERAL HELPERS
# =========================================================

def money(value):
    if value is None:
        return "Price unavailable"

    try:
        return f"₹{float(value):,.0f}"
    except Exception:
        return "Price unavailable"


def clean_price(price):
    if price is None:
        return None

    if isinstance(price, (int, float)):
        return float(price)

    text = str(price)

    for symbol in ["₹", "$", "€", "£"]:
        text = text.replace(symbol, "")

    text = text.replace(",", "").strip()

    number = ""
    decimal_seen = False

    for char in text:
        if char.isdigit():
            number += char

        elif char == "." and not decimal_seen:
            number += char
            decimal_seen = True

    try:
        return float(number) if number else None
    except Exception:
        return None


def safe_float(value, default=0):
    try:
        return float(value)
    except Exception:
        return default


def normalize_product(item, category):
    name = item.get("title", "Unknown Product")
    link = item.get("link", "")

    price = clean_price(item.get("price"))

    return {
        "id": f"{category}-{abs(hash(str(name) + str(link)))}",
        "category": category,
        "name": name,
        "price": price,
        "display_price": money(price),
        "source": item.get("source", "Unknown"),
        "rating": safe_float(item.get("rating"), 0),
        "reviews": safe_float(item.get("reviews"), 0),
        "link": link,
        "thumbnail": item.get("thumbnail", ""),
        "snippet": item.get("snippet", ""),
        "delivery": item.get("delivery", ""),
    }


def get_product_by_id(product_id):
    for product in st.session_state.products:
        if product["id"] == product_id:
            return product

    return None


def get_categories():
    return sorted(
        list(
            dict.fromkeys(
                p.get("category", "Other")
                for p in st.session_state.products
            )
        )
    )


# =========================================================
# SHOPPING API
# =========================================================

def search_shopping(query, max_results=8):

    if not SERPAPI_API_KEY:
        st.warning(
            "⚠️ Shopping search is not configured yet. "
            "Add SERPAPI_API_KEY in Streamlit Secrets."
        )
        return []

    params = {
        "engine": "google_shopping",
        "q": query,
        "api_key": SERPAPI_API_KEY,

        # India settings
        "location": "India",
        "google_domain": "google.co.in",
        "gl": "in",
        "hl": "en",

        "num": max_results,
    }

    try:

        response = requests.get(
            "https://serpapi.com/search.json",
            params=params,
            timeout=30,
        )

        if response.status_code == 401:
            st.error(
                "❌ Invalid SerpAPI key. "
                "Check SERPAPI_API_KEY in Streamlit Secrets."
            )
            return []

        if response.status_code == 429:
            st.warning(
                "⚠️ SerpAPI request limit reached. "
                "Please check your SerpAPI quota."
            )
            return []

        response.raise_for_status()

        data = response.json()

        if "error" in data:
            st.warning(
                f"SerpAPI error: {data['error']}"
            )
            return []

        return data.get("shopping_results", [])

    except requests.exceptions.Timeout:

        st.error(
            "⏱️ Shopping search timed out."
        )

        return []

    except requests.exceptions.RequestException as exc:

        st.error(
            f"Shopping search failed: {exc}"
        )

        return []


# =========================================================
# GROQ AI
# =========================================================

def run_agent(system_prompt, user_prompt, json_mode=True):

    client = get_groq_client()

    if not client:
        return None, 0

    start = time.time()

    try:

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",

            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],

            temperature=st.session_state.settings[
                "ai_temperature"
            ],

            response_format=(
                {"type": "json_object"}
                if json_mode
                else {"type": "text"}
            ),
        )

        latency = round(
            time.time() - start,
            2,
        )

        return (
            response.choices[0].message.content,
            latency,
        )

    except Exception as exc:

        st.warning(
            f"AI service unavailable: {exc}"
        )

        return None, 0


# =========================================================
# PRODUCT SCORING
# =========================================================

def product_score(
    product,
    preferences="",
    priorities=None,
):
    priorities = priorities or []

    rating = (
        min(
            max(
                safe_float(
                    product.get("rating")
                ),
                0,
            ),
            5,
        )
        / 5
        * 100
    )

    reviews = safe_float(
        product.get("reviews")
    )

    review_score = min(
        reviews / 1000 * 100,
        100,
    )

    # Base value component
    price_score = 70

    preference_bonus = 0

    text = (
        str(product.get("name", ""))
        + " "
        + str(product.get("snippet", ""))
    ).lower()

    for word in str(
        preferences
    ).lower().split():

        if len(word) > 3 and word in text:
            preference_bonus += 2

    preference_bonus = min(
        preference_bonus,
        20,
    )

    score = (
        rating * 0.40
        + review_score * 0.15
        + price_score * 0.20
        + preference_bonus * 0.25
    )

    if "High Rating" in priorities:
        score += rating * 0.10

    if "Customer Reviews" in priorities:
        score += review_score * 0.05

    return min(
        round(score, 1),
        100,
    )


# =========================================================
# OPTIMIZATION
# =========================================================

def optimize_combination(
    products,
    budget,
    strategy="Best Overall Value",
):

    valid = [
        p
        for p in products
        if p.get("price") is not None
        and p.get("price") <= budget
    ]

    categories = sorted(
        list(
            dict.fromkeys(
                p.get("category", "Other")
                for p in valid
            )
        )
    )

    if not categories:
        return None, []

    grouped = {}

    for category in categories:

        category_products = [
            p
            for p in valid
            if p.get("category") == category
        ]

        if strategy == "Highest Rating":

            category_products.sort(
                key=lambda x: (
                    safe_float(
                        x.get("rating")
                    ),
                    safe_float(
                        x.get("reviews")
                    ),
                ),
                reverse=True,
            )

        elif strategy == "Lowest Cost":

            category_products.sort(
                key=lambda x: (
                    x.get("price")
                    if x.get("price") is not None
                    else float("inf")
                )
            )

        else:

            category_products.sort(
                key=lambda x: product_score(
                    x,
                    st.session_state.preferences,
                ),
                reverse=True,
            )

        grouped[category] = category_products[:6]

    if any(
        not values
        for values in grouped.values()
    ):
        return None, []

    best = None
    alternatives = []

    for combo in cartesian_product(
        *grouped.values()
    ):

        total = sum(
            p.get("price") or 0
            for p in combo
        )

        if total > budget:
            continue

        scores = [
            product_score(
                p,
                st.session_state.preferences,
            )
            for p in combo
        ]

        average_score = (
            sum(scores)
            / len(scores)
        )

        if strategy == "Lowest Cost":

            final_score = (
                100
                - (total / budget * 100)
            )

        elif strategy == "Highest Rating":

            final_score = average_score

        else:

            budget_efficiency = (
                min(
                    total / budget,
                    1,
                )
                * 10
            )

            final_score = (
                average_score
                + budget_efficiency
            )

        record = {
            "products": list(combo),
            "total": total,
            "remaining": budget - total,
            "score": round(
                final_score,
                1,
            ),
        }

        alternatives.append(record)

        if (
            best is None
            or record["score"] > best["score"]
        ):
            best = record

    alternatives.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    return best, alternatives


# =========================================================
# UI HELPERS
# =========================================================

def show_page_header(title, description):

    st.markdown(
        f"""
        <div class="hero">
            <h1>{title}</h1>
            <p>{description}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_product_card(
    product,
    show_select=True,
    show_save=True,
):

    with st.container(border=True):

        col1, col2, col3 = st.columns(
            [1, 3, 1]
        )

        with col1:

            if product.get("thumbnail"):

                st.image(
                    product["thumbnail"],
                    width=120,
                )

            else:

                st.markdown(
                    "🛍️",
                    unsafe_allow_html=True,
                )

        with col2:

            st.markdown(
                f"### {product['name']}"
            )

            st.caption(
                f"Category: {product['category']}"
            )

            st.write(
                f"**Price:** "
                f"{product['display_price']}"
            )

            rating = product.get(
                "rating",
                0,
            )

            reviews = product.get(
                "reviews",
                0,
            )

            st.write(
                f"⭐ {rating:.1f}/5 "
                f"• {int(reviews):,} reviews"
            )

            if product.get("source"):

                st.caption(
                    f"Seller/Source: "
                    f"{product['source']}"
                )

            score = product_score(
                product,
                st.session_state.preferences,
            )

            st.markdown(
                f"**AI Value Score:** "
                f"{score}/100"
            )

            if product.get("snippet"):

                st.caption(
                    product["snippet"][:250]
                )

        with col3:

            if show_select:

                checked = (
                    product["id"]
                    in st.session_state.selected_ids
                )

                new_checked = st.checkbox(
                    "Compare",
                    value=checked,
                    key=f"compare_{product['id']}",
                )

                if new_checked:

                    if (
                        product["id"]
                        not in st.session_state.selected_ids
                    ):
                        st.session_state.selected_ids.append(
                            product["id"]
                        )

                else:

                    if (
                        product["id"]
                        in st.session_state.selected_ids
                    ):
                        st.session_state.selected_ids.remove(
                            product["id"]
                        )

            if show_save:

                is_saved = any(
                    p["id"] == product["id"]
                    for p in st.session_state.saved_products
                )

                if not is_saved:

                    if st.button(
                        "♡ Save",
                        key=f"save_{product['id']}",
                    ):

                        st.session_state.saved_products.append(
                            product
                        )

                        st.toast(
                            "Product saved!"
                        )

                        st.rerun()

                else:

                    st.caption(
                        "❤️ Saved"
                    )

            if product.get("link"):

                st.link_button(
                    "View Product",
                    product["link"],
                )


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.title("🛍️ SmartShop AI")

    st.caption(
        "AI Shopping Comparison & "
        "Budget Optimization"
    )

    st.divider()

    menu = st.radio(
        "Navigation",

        [
            "🏠 Home",
            "🔎 Product Research",
            "⚖️ Compare Products",
            "🤖 AI Shopping Advisor",
            "💰 Budget Planner",
            "❤️ Saved Products",
            "⚙️ Settings",
        ],
    )

    st.divider()

    st.metric(
        "Products",
        len(st.session_state.products),
    )

    st.metric(
        "Saved",
        len(st.session_state.saved_products),
    )

    st.metric(
        "Budget",
        money(st.session_state.budget),
    )


# =========================================================
# PAGE 1 — HOME
# =========================================================

if menu == "🏠 Home":

    st.markdown(
        """
        <div class="hero">
            <h1>🛍️ SmartShop AI</h1>
            <p>
            Compare products from shopping websites,
            select products manually or let AI choose
            the best combination within your budget.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader(
        "What can SmartShop AI do?"
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:

        st.info(
            "🔎\n\n"
            "**Product Research**\n\n"
            "Find products from shopping sources."
        )

    with c2:

        st.info(
            "⚖️\n\n"
            "**Comparison**\n\n"
            "Compare price, ratings and reviews."
        )

    with c3:

        st.info(
            "🤖\n\n"
            "**AI Selection**\n\n"
            "Let AI select the best option."
        )

    with c4:

        st.info(
            "💰\n\n"
            "**Budget Optimization**\n\n"
            "Find the best combination."
        )

    st.divider()

    st.subheader(
        "How it works"
    )

    steps = [
        ("1", "Enter Requirements"),
        ("2", "Collect Products"),
        ("3", "Compare Options"),
        ("4", "Select Manually or Automatically"),
        ("5", "Optimize Budget"),
        ("6", "Get AI Recommendation"),
    ]

    for number, text in steps:

        st.markdown(
            f"**{number}.** {text}"
        )

    st.divider()

    st.subheader(
        "🚀 Start Shopping Research"
    )

    if st.button(
        "Go to Product Research",
        type="primary",
    ):

        st.info(
            "Use the Product Research page "
            "from the sidebar."
        )


# =========================================================
# PAGE 2 — PRODUCT RESEARCH
# =========================================================

elif menu == "🔎 Product Research":

    show_page_header(
        "🔎 Product Research",
        "Search Indian shopping sources and collect products for comparison.",
    )

    col1, col2 = st.columns(
        [2, 1]
    )

    with col1:

        search_text = st.text_input(
            "What are you looking for?",
            placeholder=(
                "Example: gaming laptop under ₹80000"
            ),
        )

    with col2:

        max_results = st.number_input(
            "Results per category",
            min_value=3,
            max_value=15,
            value=int(
                st.session_state.settings[
                    "max_results"
                ]
            ),
        )

    categories_text = st.text_input(
        "Categories to search",
        placeholder=(
            "Example: Gaming Laptop, Headphones, Backpack"
        ),
    )

    preferences = st.text_area(
        "Your preferences",
        placeholder=(
            "Example: good battery, lightweight, "
            "high rating, suitable for students"
        ),
    )

    st.session_state.preferences = preferences

    if st.button(
        "🔎 Search Shopping Websites",
        type="primary",
        use_container_width=True,
    ):

        # Clear old products
        st.session_state.products = []
        st.session_state.selected_ids = []
        st.session_state.comparison_ids = []
        st.session_state.last_recommendation = None

        categories = [
            x.strip()
            for x in categories_text.split(",")
            if x.strip()
        ]

        if not categories:

            if search_text.strip():

                categories = [
                    search_text.strip()
                ]

            else:

                st.error(
                    "Please enter a product or category."
                )
                st.stop()

        all_products = []

        progress = st.progress(0)

        for index, category in enumerate(
            categories
        ):

            query = category

            if search_text.strip():
                query = (
                    f"{category} "
                    f"{search_text}"
                )

            raw_results = search_shopping(
                query,
                int(max_results),
            )

            for item in raw_results:

                product = normalize_product(
                    item,
                    category,
                )

                all_products.append(
                    product
                )

            progress.progress(
                (index + 1)
                / len(categories)
            )

        st.session_state.products = (
            all_products
        )

        st.session_state.categories = (
            categories
        )

        st.session_state.search_history.append(
            {
                "query": search_text,
                "categories": categories,
                "count": len(all_products),
            }
        )

        if all_products:

            st.success(
                f"Found {len(all_products)} products."
            )

        else:

            st.warning(
                "No products were found. "
                "Check your API key or search again."
            )

    if st.session_state.products:

        st.divider()

        st.subheader(
            f"🛒 {len(st.session_state.products)} Products Found"
        )

        categories = get_categories()

        selected_category = st.selectbox(
            "Filter by category",
            ["All"] + categories,
        )

        products_to_show = (
            st.session_state.products
        )

        if selected_category != "All":

            products_to_show = [
                p
                for p in products_to_show
                if p["category"]
                == selected_category
            ]

        sort_option = st.selectbox(
            "Sort products",
            [
                "AI Score",
                "Lowest Price",
                "Highest Rating",
                "Most Reviews",
            ],
        )

        if sort_option == "AI Score":

            products_to_show = sorted(
                products_to_show,
                key=lambda x: product_score(
                    x,
                    st.session_state.preferences,
                ),
                reverse=True,
            )

        elif sort_option == "Lowest Price":

            products_to_show = sorted(
                products_to_show,
                key=lambda x: (
                    x["price"]
                    if x["price"] is not None
                    else float("inf")
                ),
            )

        elif sort_option == "Highest Rating":

            products_to_show = sorted(
                products_to_show,
                key=lambda x: x["rating"],
                reverse=True,
            )

        else:

            products_to_show = sorted(
                products_to_show,
                key=lambda x: x["reviews"],
                reverse=True,
            )

        for product in products_to_show:

            render_product_card(
                product,
                show_select=True,
                show_save=True,
            )


# =========================================================
# PAGE 3 — COMPARE PRODUCTS
# =========================================================

elif menu == "⚖️ Compare Products":

    show_page_header(
        "⚖️ Compare Products",
        "Compare selected products before making a purchase decision.",
    )

    selected = [
        get_product_by_id(pid)
        for pid in st.session_state.selected_ids
    ]

    selected = [
        p for p in selected
        if p is not None
    ]

    if not selected:

        st.info(
            "No products selected yet. "
            "Go to Product Research and select products."
        )

    else:

        st.success(
            f"{len(selected)} products selected."
        )

        table_data = []

        for p in selected:

            table_data.append(
                {
                    "Category": p["category"],
                    "Product": p["name"],
                    "Price": p["display_price"],
                    "Rating": (
                        f"{p['rating']:.1f}/5"
                    ),
                    "Reviews": int(
                        p["reviews"]
                    ),
                    "AI Score": product_score(
                        p,
                        st.session_state.preferences,
                    ),
                    "Source": p["source"],
                }
            )

        st.dataframe(
            table_data,
            use_container_width=True,
            hide_index=True,
        )

        st.divider()

        st.subheader(
            "🏆 Best Overall Product"
        )

        best = max(
            selected,
            key=lambda x: product_score(
                x,
                st.session_state.preferences,
            ),
        )

        render_product_card(
            best,
            show_select=False,
            show_save=True,
        )

        st.subheader(
            "📊 Individual Comparison"
        )

        for p in selected:

            with st.expander(
                p["name"]
            ):

                c1, c2, c3 = st.columns(3)

                with c1:

                    st.metric(
                        "Price",
                        p["display_price"],
                    )

                with c2:

                    st.metric(
                        "Rating",
                        f"{p['rating']:.1f}/5",
                    )

                with c3:

                    st.metric(
                        "AI Score",
                        f"{product_score(p, st.session_state.preferences)}/100",
                    )

                st.write(
                    f"**Reviews:** "
                    f"{int(p['reviews']):,}"
                )

                st.write(
                    f"**Source:** {p['source']}"
                )

                if p.get("link"):

                    st.link_button(
                        "View Product",
                        p["link"],
                    )

        if st.button(
            "Clear Comparison"
        ):

            st.session_state.selected_ids = []

            st.rerun()


# =========================================================
# PAGE 4 — AI SHOPPING ADVISOR
# =========================================================

elif menu == "🤖 AI Shopping Advisor":

    show_page_header(
        "🤖 AI Shopping Advisor",
        "Let AI analyze the available products and recommend the best combination.",
    )

    if not st.session_state.products:

        st.info(
            "Search for products first."
        )

    else:

        budget = st.number_input(
            "Your total shopping budget (₹)",
            min_value=500,
            max_value=10000000,
            value=int(
                st.session_state.budget
            ),
            step=500,
        )

        st.session_state.budget = budget

        priorities = st.multiselect(
            "What matters most?",
            [
                "High Rating",
                "Customer Reviews",
                "Low Price",
                "Features",
                "Brand",
            ],
            default=[
                "High Rating",
                "Customer Reviews",
            ],
        )

        mode = st.radio(
            "Selection mode",
            [
                "Manual Selection",
                "Automatic AI Selection",
            ],
            horizontal=True,
        )

        if mode == "Manual Selection":

            st.subheader(
                "👤 Manual Selection"
            )

            selected = [
                get_product_by_id(pid)
                for pid in st.session_state.selected_ids
            ]

            selected = [
                p for p in selected
                if p is not None
            ]

            if not selected:

                st.warning(
                    "Select products from Product Research first."
                )

            else:

                total = sum(
                    p["price"] or 0
                    for p in selected
                )

                st.metric(
                    "Selected Products",
                    len(selected),
                )

                st.metric(
                    "Total Cost",
                    money(total),
                )

                if total <= budget:

                    st.success(
                        f"Within budget by "
                        f"{money(budget - total)}"
                    )

                else:

                    st.error(
                        f"Over budget by "
                        f"{money(total - budget)}"
                    )

                st.divider()

                for p in selected:

                    render_product_card(
                        p,
                        show_select=False,
                    )

        else:

            st.subheader(
                "🤖 Automatic AI Selection"
            )

            strategy = st.selectbox(
                "Optimization strategy",
                [
                    "Best Overall Value",
                    "Lowest Cost",
                    "Highest Rating",
                ],
            )

            if st.button(
                "🤖 Find Best Combination",
                type="primary",
                use_container_width=True,
            ):

                with st.spinner(
                    "Analyzing products and budget..."
                ):

                    best, alternatives = (
                        optimize_combination(
                            st.session_state.products,
                            budget,
                            strategy,
                        )
                    )

                    ai_result = {}

                    if best:

                        product_summary = [
                            {
                                "category": p[
                                    "category"
                                ],
                                "name": p["name"],
                                "price": p[
                                    "price"
                                ],
                                "rating": p[
                                    "rating"
                                ],
                                "reviews": p[
                                    "reviews"
                                ],
                                "source": p[
                                    "source"
                                ],
                            }
                            for p in best[
                                "products"
                            ]
                        ]

                        system_prompt = """
You are an expert AI shopping advisor.

Analyze the selected product combination.

Do not invent product facts.

Explain:
1. Why the products were selected.
2. Main advantages.
3. Main trade-offs.
4. Whether the combination fits the budget.
5. Buying tips.

Return JSON with:
recommendation,
reasons,
tradeoffs,
buying_tips
"""

                        user_prompt = json.dumps(
                            {
                                "budget": budget,
                                "strategy": strategy,
                                "preferences": st.session_state.preferences,
                                "products": product_summary,
                            },
                            indent=2,
                        )

                        raw, latency = run_agent(
                            system_prompt,
                            user_prompt,
                            True,
                        )

                        if raw:

                            try:

                                ai_result = json.loads(
                                    raw
                                )

                            except Exception:

                                ai_result = {
                                    "recommendation": raw,
                                    "reasons": [],
                                    "tradeoffs": [],
                                    "buying_tips": [],
                                }

                        st.session_state.last_recommendation = {
                            "best": best,
                            "alternatives": alternatives,
                            "ai": ai_result,
                            "budget": budget,
                            "mode": "Automatic",
                            "strategy": strategy,
                        }

            recommendation = (
                st.session_state.last_recommendation
            )

            if recommendation:

                best = recommendation["best"]
                alternatives = recommendation[
                    "alternatives"
                ]
                ai = recommendation["ai"]

                st.divider()

                st.subheader(
                    "🏆 AI Recommended Shopping Plan"
                )

                c1, c2, c3 = st.columns(3)

                with c1:

                    st.metric(
                        "Total Cost",
                        money(best["total"]),
                    )

                with c2:

                    st.metric(
                        "Remaining Budget",
                        money(
                            best["remaining"]
                        ),
                    )

                with c3:

                    st.metric(
                        "Plan Score",
                        f"{best['score']}/100",
                    )

                for p in best["products"]:

                    render_product_card(
                        p,
                        show_select=False,
                        show_save=True,
                    )

                if ai.get(
                    "recommendation"
                ):

                    st.info(
                        "🤖 "
                        + str(
                            ai[
                                "recommendation"
                            ]
                        )
                    )

                if ai.get("reasons"):

                    st.markdown(
                        "### Why AI selected this combination"
                    )

                    for reason in ai[
                        "reasons"
                    ]:

                        st.markdown(
                            f"• {reason}"
                        )

                if ai.get("tradeoffs"):

                    st.markdown(
                        "### ⚖️ Trade-offs"
                    )

                    for item in ai[
                        "tradeoffs"
                    ]:

                        st.markdown(
                            f"• {item}"
                        )

                if ai.get("buying_tips"):

                    st.markdown(
                        "### 💡 Buying Tips"
                    )

                    for item in ai[
                        "buying_tips"
                    ]:

                        st.markdown(
                            f"• {item}"
                        )

                if len(alternatives) > 1:

                    st.markdown(
                        "### 🔄 Alternative Combinations"
                    )

                    for index, option in enumerate(
                        alternatives[1:5],
                        1,
                    ):

                        with st.container(
                            border=True
                        ):

                            st.write(
                                f"**Option {index}**"
                            )

                            st.caption(
                                f"Total: "
                                f"{money(option['total'])} "
                                f"• Score: "
                                f"{option['score']}/100 "
                                f"• Remaining: "
                                f"{money(option['remaining'])}"
                            )

                            st.write(
                                ", ".join(
                                    p["name"]
                                    for p in option[
                                        "products"
                                    ]
                                )
                            )


# =========================================================
# PAGE 5 — BUDGET PLANNER
# =========================================================

elif menu == "💰 Budget Planner":

    show_page_header(
        "💰 Budget Planner",
        "Find the strongest product combination for your budget.",
    )

    if not st.session_state.products:

        st.info(
            "Research products first."
        )

    else:

        budget = st.number_input(
            "Available Budget (₹)",
            min_value=500,
            max_value=10000000,
            value=int(
                st.session_state.budget
            ),
            step=500,
        )

        strategy = st.radio(
            "Optimization strategy",
            [
                "Best Overall Value",
                "Lowest Cost",
                "Highest Rating",
            ],
            horizontal=True,
        )

        if st.button(
            "💰 Optimize My Budget",
            type="primary",
        ):

            best, alternatives = (
                optimize_combination(
                    st.session_state.products,
                    budget,
                    strategy,
                )
            )

            if not best:

                st.error(
                    "No complete combination fits "
                    "within this budget."
                )

            else:

                st.session_state.last_recommendation = {
                    "best": best,
                    "alternatives": alternatives,
                    "ai": {},
                    "budget": budget,
                    "mode": "Automatic",
                    "strategy": strategy,
                }

                st.success(
                    "Best combination found!"
                )

                c1, c2, c3 = st.columns(3)

                with c1:

                    st.metric(
                        "Budget",
                        money(budget),
                    )

                with c2:

                    st.metric(
                        "Plan Cost",
                        money(best["total"]),
                    )

                with c3:

                    st.metric(
                        "Remaining",
                        money(
                            best["remaining"]
                        ),
                    )

                st.markdown(
                    "### 🏆 Recommended Combination"
                )

                for p in best["products"]:

                    render_product_card(
                        p,
                        show_select=False,
                    )

                if len(alternatives) > 1:

                    st.markdown(
                        "### 🔄 Other Possible Plans"
                    )

                    for option in alternatives[
                        1:5
                    ]:

                        with st.container(
                            border=True
                        ):

                            st.write(
                                f"**Total:** "
                                f"{money(option['total'])}"
                            )

                            st.caption(
                                f"Score: "
                                f"{option['score']}/100 "
                                f"• Remaining: "
                                f"{money(option['remaining'])}"
                            )

                            st.write(
                                " + ".join(
                                    p["name"]
                                    for p in option[
                                        "products"
                                    ]
                                )
                            )


# =========================================================
# PAGE 6 — SAVED PRODUCTS
# =========================================================

elif menu == "❤️ Saved Products":

    show_page_header(
        "❤️ Saved Products",
        "Keep products that you may want to compare or purchase later.",
    )

    if not st.session_state.saved_products:

        st.info(
            "No saved products yet."
        )

    else:

        st.write(
            f"You have **"
            f"{len(st.session_state.saved_products)}"
            f"** saved products."
        )

        if st.button(
            "🗑️ Clear All Saved Products"
        ):

            st.session_state.saved_products = []

            st.success(
                "Saved products cleared."
            )

            st.rerun()

        for product in (
            st.session_state.saved_products
        ):

            render_product_card(
                product,
                show_select=False,
                show_save=False,
            )


# =========================================================
# PAGE 7 — SETTINGS
# =========================================================

elif menu == "⚙️ Settings":

    show_page_header(
        "⚙️ Settings",
        "Configure the shopping research and AI experience.",
    )

    st.subheader(
        "🔌 API Status"
    )

    c1, c2 = st.columns(2)

    with c1:

        if GROQ_API_KEY:

            st.success(
                "Groq API: Connected"
            )

        else:

            st.warning(
                "Groq API: Not configured"
            )

    with c2:

        if SERPAPI_API_KEY:

            st.success(
                "Shopping Search API: Connected"
            )

        else:

            st.warning(
                "Shopping Search API: Not configured"
            )

    st.divider()

    st.subheader(
        "🔎 Search Settings"
    )

    max_results = st.slider(
        "Maximum results per category",
        3,
        15,
        int(
            st.session_state.settings[
                "max_results"
            ]
        ),
    )

    st.subheader(
        "🤖 AI Settings"
    )

    temperature = st.slider(
        "AI creativity",
        0.0,
        0.5,
        float(
            st.session_state.settings[
                "ai_temperature"
            ]
        ),
        0.05,
    )

    if st.button(
        "💾 Save Settings"
    ):

        st.session_state.settings = {
            "max_results": max_results,
            "currency": "INR (₹)",
            "ai_temperature": temperature,
        }

        st.success(
            "Settings saved."
        )

    st.divider()

    st.subheader(
        "🧹 Session Management"
    )

    if st.button(
        "Reset Shopping Session"
    ):

        st.session_state.products = []
        st.session_state.selected_ids = []
        st.session_state.comparison_ids = []
        st.session_state.saved_products = []
        st.session_state.search_history = []
        st.session_state.last_recommendation = None
        st.session_state.categories = []
        st.session_state.preferences = ""
        st.session_state.last_search_message = ""

        st.success(
            "Shopping session reset."
        )

        st.rerun()

    st.divider()

    st.subheader(
        "📌 Project Information"
    )

    st.write(
        """
        **SmartShop AI** is an AI-powered shopping
        comparison and budget optimization system.

        ### Core Components

        • Shopping data collection

        • Product comparison

        • Product scoring

        • Manual product selection

        • Automatic product selection

        • Budget-constrained optimization

        • AI recommendation

        • Alternative combinations

        • Saved products

        ### Technology

        **Frontend:** Streamlit

        **Programming:** Python

        **AI:** Groq + Llama

        **Shopping Data:** SerpAPI Google Shopping

        **Data Processing:** Python

        **Optimization:** Budget-constrained combination search
        """
    )
