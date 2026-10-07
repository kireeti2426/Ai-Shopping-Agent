import streamlit as st
import os
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
    initial_sidebar_state="expanded"
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
        background: linear-gradient(
            135deg,
            #eef2ff,
            #f8fafc
        );
        border: 1px solid #e2e8f0;
        margin-bottom: 1.5rem;
    }

    .hero h1 {
        margin-bottom: .3rem;
    }

    .hero p {
        color: #475569;
        font-size: 1.05rem;
    }

    [data-testid="stSidebar"] {
        border-right: 1px solid #e2e8f0;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# API CONFIGURATION
# =========================================================

def get_secret(name):

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
            groq_client = Groq(
                api_key=GROQ_API_KEY
            )
        except Exception:
            groq_client = None

    return groq_client


# =========================================================
# SESSION STATE
# =========================================================

defaults = {
    "products": [],
    "selected_ids": [],
    "saved_products": [],
    "search_history": [],
    "last_recommendation": None,
    "budget": 20000,
    "preferences": "",
    "categories": [],
    "settings": {
        "max_results": 8,
        "ai_temperature": 0.1
    }
}

for key, value in defaults.items():

    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def money(value):

    if value is None:
        return "Price unavailable"

    try:
        return f"₹{float(value):,.0f}"
    except Exception:
        return "Price unavailable"


def clean_price(value):

    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value)

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


def normalize_product(
    item,
    category,
    index
):

    name = item.get(
        "title",
        "Unknown Product"
    )

    link = item.get(
        "link",
        ""
    )

    price = clean_price(
        item.get("price")
    )

    # Guaranteed unique product ID
    product_id = (
        f"{category}_"
        f"{index}_"
        f"{abs(hash(str(name) + str(link) + str(index)))}"
    )

    return {

        "id": product_id,

        "category": category,

        "name": name,

        "price": price,

        "display_price": money(price),

        "source": item.get(
            "source",
            "Unknown"
        ),

        "rating": safe_float(
            item.get("rating"),
            0
        ),

        "reviews": safe_float(
            item.get("reviews"),
            0
        ),

        "link": link,

        "thumbnail": item.get(
            "thumbnail",
            ""
        ),

        "snippet": item.get(
            "snippet",
            ""
        )
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
                p["category"]
                for p in st.session_state.products
            )
        )
    )


# =========================================================
# SHOPPING SEARCH
# =========================================================

def search_shopping(
    query,
    max_results=8
):

    if not SERPAPI_API_KEY:

        st.warning(
            "⚠️ SERPAPI_API_KEY is not configured. "
            "Add it in Streamlit Secrets."
        )

        return []

    params = {

        "engine":
            "google_shopping",

        "q":
            query,

        "api_key":
            SERPAPI_API_KEY,

        # India
        "location":
            "India",

        "google_domain":
            "google.co.in",

        "gl":
            "in",

        "hl":
            "en",

        "num":
            max_results
    }

    try:

        response = requests.get(
            "https://serpapi.com/search.json",
            params=params,
            timeout=30
        )

        if response.status_code == 401:

            st.error(
                "❌ Invalid SerpAPI key."
            )

            return []

        if response.status_code == 429:

            st.warning(
                "⚠️ SerpAPI request limit reached."
            )

            return []

        response.raise_for_status()

        data = response.json()

        if "error" in data:

            st.warning(
                f"SerpAPI error: "
                f"{data['error']}"
            )

            return []

        return data.get(
            "shopping_results",
            []
        )

    except requests.exceptions.Timeout:

        st.error(
            "⏱️ Shopping search timed out."
        )

        return []

    except requests.exceptions.RequestException as error:

        st.error(
            f"Shopping search failed: {error}"
        )

        return []


# =========================================================
# GROQ
# =========================================================

def run_ai(
    system_prompt,
    user_prompt
):

    client = get_groq_client()

    if client is None:
        return None

    try:

        response = client.chat.completions.create(

            model="llama-3.3-70b-versatile",

            messages=[

                {
                    "role":
                        "system",

                    "content":
                        system_prompt
                },

                {
                    "role":
                        "user",

                    "content":
                        user_prompt
                }
            ],

            temperature=
                st.session_state.settings[
                    "ai_temperature"
                ],

            response_format={
                "type":
                    "json_object"
            }
        )

        return response.choices[
            0
        ].message.content

    except Exception as error:

        st.warning(
            f"AI service unavailable: {error}"
        )

        return None


# =========================================================
# PRODUCT SCORE
# =========================================================

def product_score(
    product,
    preferences=""
):

    rating = safe_float(
        product.get("rating"),
        0
    )

    rating_score = (
        min(max(rating, 0), 5)
        / 5
        * 100
    )

    reviews = safe_float(
        product.get("reviews"),
        0
    )

    review_score = min(
        reviews / 1000 * 100,
        100
    )

    text = (
        str(product.get("name", ""))
        + " "
        + str(product.get("snippet", ""))
    ).lower()

    preference_bonus = 0

    for word in str(
        preferences
    ).lower().split():

        if (
            len(word) > 3
            and word in text
        ):

            preference_bonus += 3

    preference_bonus = min(
        preference_bonus,
        20
    )

    score = (

        rating_score * 0.45

        + review_score * 0.20

        + 70 * 0.20

        + preference_bonus * 0.15
    )

    return round(
        min(score, 100),
        1
    )


# =========================================================
# BUDGET OPTIMIZATION
# =========================================================

def optimize_combination(
    products,
    budget,
    strategy
):

    # IMPORTANT:
    # Only products <= budget are considered.
    eligible_products = [

        p

        for p in products

        if p.get("price") is not None

        and p["price"] <= budget
    ]

    if not eligible_products:
        return None, []

    categories = sorted(
        list(
            dict.fromkeys(
                p["category"]
                for p in eligible_products
            )
        )
    )

    if not categories:
        return None, []

    grouped = {}

    for category in categories:

        category_products = [

            p

            for p in eligible_products

            if p["category"] == category
        ]

        if strategy == "Lowest Cost":

            category_products.sort(
                key=lambda p:
                    p["price"]
            )

        elif strategy == "Highest Rating":

            category_products.sort(
                key=lambda p:
                    (
                        p["rating"],
                        p["reviews"]
                    ),
                reverse=True
            )

        else:

            category_products.sort(
                key=lambda p:
                    product_score(
                        p,
                        st.session_state.preferences
                    ),
                reverse=True
            )

        # Keep top 8 from each category
        grouped[category] = (
            category_products[:8]
        )

    # =====================================================
    # FIND VALID COMBINATIONS
    # =====================================================

    best = None
    alternatives = []

    category_lists = list(
        grouped.values()
    )

    for combination in cartesian_product(
        *category_lists
    ):

        total = sum(
            p["price"]
            for p in combination
        )

        # CRITICAL:
        # COMPLETE COMBINATION MUST BE
        # WITHIN THE USER'S BUDGET.
        if total > budget:
            continue

        # -------------------------------------------------
        # Score
        # -------------------------------------------------

        if strategy == "Lowest Cost":

            score = (
                100
                - (
                    total / budget
                ) * 100
            )

        elif strategy == "Highest Rating":

            score = (

                sum(
                    p["rating"]
                    for p in combination
                )

                / len(combination)

                * 20
            )

        else:

            scores = [

                product_score(
                    p,
                    st.session_state.preferences
                )

                for p in combination
            ]

            average_score = (
                sum(scores)
                / len(scores)
            )

            # Reward useful use of budget,
            # but never allow going over budget.
            budget_usage = (
                total / budget
            )

            score = (
                average_score
                + budget_usage * 10
            )

        result = {

            "products":
                list(combination),

            "total":
                total,

            "remaining":
                budget - total,

            "score":
                round(score, 1)
        }

        alternatives.append(
            result
        )

        if (
            best is None

            or result["score"]
            > best["score"]
        ):

            best = result

    alternatives.sort(
        key=lambda x:
            x["score"],
        reverse=True
    )

    return best, alternatives


# =========================================================
# PRODUCT CARD
# =========================================================

def render_product_card(
    product,
    card_key,
    show_compare=True,
    show_save=True
):

    with st.container(
        border=True
    ):

        col1, col2, col3 = st.columns(
            [1, 3, 1]
        )

        # =================================================
        # IMAGE
        # =================================================

        with col1:

            if product.get(
                "thumbnail"
            ):

                try:

                    st.image(
                        product["thumbnail"],
                        width=120
                    )

                except Exception:

                    st.markdown(
                        "## 🛍️"
                    )

            else:

                st.markdown(
                    "## 🛍️"
                )

        # =================================================
        # PRODUCT INFORMATION
        # =================================================

        with col2:

            st.markdown(
                f"### {product['name']}"
            )

            st.caption(
                f"Category: "
                f"{product['category']}"
            )

            st.write(
                f"**Price:** "
                f"{product['display_price']}"
            )

            st.write(
                f"⭐ "
                f"{product['rating']:.1f}/5"
                f"  •  "
                f"{int(product['reviews']):,} reviews"
            )

            st.write(
                f"**AI Score:** "
                f"{product_score(product, st.session_state.preferences)}/100"
            )

            st.caption(
                f"Seller: "
                f"{product['source']}"
            )

        # =================================================
        # ACTIONS
        # =================================================

        with col3:

            if show_compare:

                checkbox_key = (
                    f"compare_"
                    f"{card_key}_"
                    f"{product['id']}"
                )

                checked = (
                    product["id"]
                    in st.session_state.selected_ids
                )

                selected = st.checkbox(
                    "Compare",
                    value=checked,
                    key=checkbox_key
                )

                if selected:

                    if (
                        product["id"]
                        not in
                        st.session_state.selected_ids
                    ):

                        st.session_state.selected_ids.append(
                            product["id"]
                        )

                else:

                    if (
                        product["id"]
                        in
                        st.session_state.selected_ids
                    ):

                        st.session_state.selected_ids.remove(
                            product["id"]
                        )

            # -------------------------------------------------
            # SAVE
            # -------------------------------------------------

            if show_save:

                already_saved = any(

                    p["id"]
                    == product["id"]

                    for p in
                    st.session_state.saved_products
                )

                if not already_saved:

                    save_key = (
                        f"save_"
                        f"{card_key}_"
                        f"{product['id']}"
                    )

                    if st.button(
                        "♡ Save",
                        key=save_key
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

            # -------------------------------------------------
            # ACTUAL SHOPPING WEBSITE
            # -------------------------------------------------

            if product.get(
                "link"
            ):

                link_key = (
                    f"visit_"
                    f"{card_key}_"
                    f"{product['id']}"
                )

                st.link_button(
                    "🛒 Visit Website",
                    product["link"],
                    key=link_key
                )


# =========================================================
# PAGE HEADER
# =========================================================

def page_header(
    title,
    description
):

    st.markdown(
        f"""
        <div class="hero">

            <h1>{title}</h1>

            <p>{description}</p>

        </div>
        """,
        unsafe_allow_html=True
    )


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.title(
        "🛍️ SmartShop AI"
    )

    st.caption(
        "AI Shopping Comparison & "
        "Budget Optimization"
    )

    st.divider()

    menu = st.radio(
        "MENU",
        [
            "🏠 Home",
            "🔎 Product Research",
            "⚖️ Compare Products",
            "🤖 AI Shopping Advisor",
            "💰 Budget Planner",
            "❤️ Saved Products",
            "⚙️ Settings"
        ]
    )

    st.divider()

    st.metric(
        "Products",
        len(
            st.session_state.products
        )
    )

    st.metric(
        "Saved",
        len(
            st.session_state.saved_products
        )
    )

    st.metric(
        "Budget",
        money(
            st.session_state.budget
        )
    )


# =========================================================
# HOME
# =========================================================

if menu == "🏠 Home":

    page_header(
        "🛍️ SmartShop AI",
        "Compare products from shopping websites and find the best products within your budget."
    )

    st.subheader(
        "What can SmartShop AI do?"
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:

        st.info(
            """
            🔎

            **Product Research**

            Search products by category.
            """
        )

    with c2:

        st.info(
            """
            ⚖️

            **Compare Products**

            Compare price, ratings and reviews.
            """
        )

    with c3:

        st.info(
            """
            🤖

            **AI Selection**

            Automatically select the best options.
            """
        )

    with c4:

        st.info(
            """
            💰

            **Budget Planner**

            Find combinations within your budget.
            """
        )

    st.divider()

    st.subheader(
        "How it works"
    )

    steps = [

        "Set your total shopping budget",

        "Enter the product categories you need",

        "Search shopping websites",

        "Compare products",

        "Select products manually OR automatically",

        "Get the best combination within budget",

        "Open the product directly on the shopping website"
    ]

    for i, step in enumerate(
        steps,
        1
    ):

        st.markdown(
            f"**{i}.** {step}"
        )

    st.success(
        "👈 Select **Product Research** from the sidebar."
    )


# =========================================================
# PRODUCT RESEARCH
# =========================================================

elif menu == "🔎 Product Research":

    page_header(
        "🔎 Product Research",
        "Search shopping websites by category and only show products that fit your budget."
    )

    # =====================================================
    # NO "WHAT ARE YOU LOOKING FOR"
    # =====================================================

    budget = st.number_input(
        "💰 Total Shopping Budget (₹)",
        min_value=500,
        max_value=10000000,
        value=int(
            st.session_state.budget
        ),
        step=500
    )

    st.session_state.budget = budget

    categories_input = st.text_input(
        "🛍️ Product Categories",
        placeholder=(
            "Example: Gaming Laptop, Headphones, Backpack"
        )
    )

    preferences = st.text_area(
        "⭐ Preferences",
        placeholder=(
            "Example: high rating, lightweight, "
            "good battery, student friendly"
        )
    )

    st.session_state.preferences = preferences

    max_results = st.slider(
        "Products per category",
        min_value=3,
        max_value=15,
        value=int(
            st.session_state.settings[
                "max_results"
            ]
        )
    )

    if st.button(
        "🔎 Search Shopping Websites",
        type="primary",
        use_container_width=True
    ):

        if not categories_input.strip():

            st.error(
                "Please enter at least one product category."
            )

        else:

            # =================================================
            # CLEAR OLD PRODUCTS
            # =================================================

            st.session_state.products = []
            st.session_state.selected_ids = []
            st.session_state.last_recommendation = None

            categories = [

                x.strip()

                for x in
                categories_input.split(",")

                if x.strip()
            ]

            all_products = []

            progress = st.progress(
                0
            )

            for category_index, category in enumerate(
                categories
            ):

                # Search only the category
                query = category

                raw_results = search_shopping(
                    query,
                    max_results
                )

                for index, item in enumerate(
                    raw_results
                ):

                    product = normalize_product(
                        item,
                        category,
                        index
                    )

                    # =================================================
                    # IMPORTANT BUDGET FILTER
                    # =================================================

                    if (
                        product["price"]
                        is not None

                        and product["price"]
                        <= budget
                    ):

                        all_products.append(
                            product
                        )

                progress.progress(
                    (
                        category_index
                        + 1
                    )
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
                    "categories":
                        categories,

                    "budget":
                        budget,

                    "count":
                        len(all_products)
                }
            )

            if all_products:

                st.success(
                    f"Found "
                    f"{len(all_products)} "
                    f"products within your "
                    f"{money(budget)} budget."
                )

            else:

                st.warning(
                    "No products were found within "
                    "your budget."
                )

    # =====================================================
    # DISPLAY RESULTS
    # =====================================================

    if st.session_state.products:

        st.divider()

        st.subheader(
            "🛒 Products Within Budget"
        )

        st.info(
            f"Only products priced at or below "
            f"{money(st.session_state.budget)} "
            f"are displayed."
        )

        category_filter = st.selectbox(
            "Category",
            ["All"] + get_categories()
        )

        sort_by = st.selectbox(
            "Sort Products By",
            [
                "AI Score",
                "Lowest Price",
                "Highest Rating",
                "Most Reviews"
            ]
        )

        products = list(
            st.session_state.products
        )

        if category_filter != "All":

            products = [

                p

                for p in products

                if p["category"]
                == category_filter
            ]

        if sort_by == "AI Score":

            products.sort(
                key=lambda p:
                    product_score(
                        p,
                        st.session_state.preferences
                    ),
                reverse=True
            )

        elif sort_by == "Lowest Price":

            products.sort(
                key=lambda p:
                    p["price"]
            )

        elif sort_by == "Highest Rating":

            products.sort(
                key=lambda p:
                    p["rating"],
                reverse=True
            )

        else:

            products.sort(
                key=lambda p:
                    p["reviews"],
                reverse=True
            )

        for index, product in enumerate(
            products
        ):

            render_product_card(
                product,
                card_key=f"research_{index}",
                show_compare=True,
                show_save=True
            )


# =========================================================
# COMPARE PRODUCTS
# =========================================================

elif menu == "⚖️ Compare Products":

    page_header(
        "⚖️ Compare Products",
        "Compare your selected products before purchasing."
    )

    selected_products = []

    for product_id in (
        st.session_state.selected_ids
    ):

        product = get_product_by_id(
            product_id
        )

        if product:

            selected_products.append(
                product
            )

    if not selected_products:

        st.info(
            "No products selected. "
            "Go to Product Research and select Compare."
        )

    else:

        st.success(
            f"{len(selected_products)} "
            f"products selected."
        )

        comparison_data = []

        for product in selected_products:

            comparison_data.append(
                {
                    "Category":
                        product["category"],

                    "Product":
                        product["name"],

                    "Price":
                        product["display_price"],

                    "Rating":
                        f"{product['rating']:.1f}/5",

                    "Reviews":
                        int(product["reviews"]),

                    "AI Score":
                        product_score(
                            product,
                            st.session_state.preferences
                        ),

                    "Website":
                        product["source"]
                }
            )

        st.dataframe(
            comparison_data,
            use_container_width=True,
            hide_index=True
        )

        st.divider()

        best = max(
            selected_products,
            key=lambda p:
                product_score(
                    p,
                    st.session_state.preferences
                )
        )

        st.subheader(
            "🏆 Best Overall"
        )

        render_product_card(
            best,
            card_key="best_comparison",
            show_compare=False,
            show_save=True
        )

        st.divider()

        st.subheader(
            "Product Details"
        )

        for index, product in enumerate(
            selected_products
        ):

            with st.expander(
                product["name"]
            ):

                c1, c2, c3 = st.columns(3)

                with c1:

                    st.metric(
                        "Price",
                        product["display_price"]
                    )

                with c2:

                    st.metric(
                        "Rating",
                        f"{product['rating']:.1f}/5"
                    )

                with c3:

                    st.metric(
                        "AI Score",
                        f"{product_score(product, st.session_state.preferences)}/100"
                    )

                st.write(
                    f"Reviews: "
                    f"{int(product['reviews']):,}"
                )

                if product.get(
                    "link"
                ):

                    st.link_button(
                        "🛒 Visit Website",
                        product["link"],
                        key=f"compare_link_{index}"
                    )

        if st.button(
            "🗑️ Clear Comparison"
        ):

            st.session_state.selected_ids = []

            st.rerun()


# =========================================================
# AI SHOPPING ADVISOR
# =========================================================

elif menu == "🤖 AI Shopping Advisor":

    page_header(
        "🤖 AI Shopping Advisor",
        "Select products manually or let AI find the best combination within your total budget."
    )

    if not st.session_state.products:

        st.info(
            "Search products first."
        )

    else:

        budget = st.number_input(
            "💰 Shopping Budget (₹)",
            min_value=500,
            max_value=10000000,
            value=int(
                st.session_state.budget
            ),
            step=500
        )

        st.session_state.budget = budget

        mode = st.radio(
            "Selection Mode",
            [
                "👤 Manual Selection",
                "🤖 Automatic Selection"
            ],
            horizontal=True
        )

        # =================================================
        # MANUAL
        # =================================================

        if mode == "👤 Manual Selection":

            st.subheader(
                "👤 Manual Selection"
            )

            selected = []

            for product_id in (
                st.session_state.selected_ids
            ):

                product = get_product_by_id(
                    product_id
                )

                if product:

                    selected.append(
                        product
                    )

            if not selected:

                st.warning(
                    "Select products from Product Research."
                )

            else:

                total = sum(
                    p["price"]
                    for p in selected
                )

                remaining = (
                    budget - total
                )

                c1, c2, c3 = st.columns(3)

                with c1:

                    st.metric(
                        "Products",
                        len(selected)
                    )

                with c2:

                    st.metric(
                        "Total",
                        money(total)
                    )

                with c3:

                    st.metric(
                        "Remaining",
                        money(remaining)
                    )

                if total <= budget:

                    st.success(
                        "✅ Selection is within budget."
                    )

                else:

                    st.error(
                        "❌ Selection is above budget."
                    )

                for index, product in enumerate(
                    selected
                ):

                    render_product_card(
                        product,
                        card_key=f"manual_{index}",
                        show_compare=False,
                        show_save=True
                    )

        # =================================================
        # AUTOMATIC
        # =================================================

        else:

            st.subheader(
                "🤖 Automatic Selection"
            )

            strategy = st.selectbox(
                "Optimization Strategy",
                [
                    "Best Overall Value",
                    "Lowest Cost",
                    "Highest Rating"
                ]
            )

            if st.button(
                "🤖 Find Best Combination",
                type="primary",
                use_container_width=True
            ):

                with st.spinner(
                    "Finding the best combination..."
                ):

                    best, alternatives = (
                        optimize_combination(
                            st.session_state.products,
                            budget,
                            strategy
                        )
                    )

                    if not best:

                        st.error(
                            "No complete combination "
                            "fits within your budget."
                        )

                    else:

                        ai_data = {}

                        # =====================================
                        # AI ANALYSIS
                        # =====================================

                        if GROQ_API_KEY:

                            product_data = []

                            for product in best[
                                "products"
                            ]:

                                product_data.append(
                                    {
                                        "category":
                                            product[
                                                "category"
                                            ],

                                        "name":
                                            product[
                                                "name"
                                            ],

                                        "price":
                                            product[
                                                "price"
                                            ],

                                        "rating":
                                            product[
                                                "rating"
                                            ],

                                        "reviews":
                                            product[
                                                "reviews"
                                            ]
                                    }
                                )

                            system_prompt = """
You are an expert AI shopping advisor.

Analyze the selected shopping combination.

Never invent product facts.

Explain:
1. Why these products were selected.
2. Main advantages.
3. Main trade-offs.
4. Whether the combination fits the budget.
5. Buying tips.

Return JSON with:
recommendation
reasons
tradeoffs
buying_tips
"""

                            user_prompt = json.dumps(
                                {
                                    "budget":
                                        budget,

                                    "strategy":
                                        strategy,

                                    "preferences":
                                        st.session_state.preferences,

                                    "products":
                                        product_data
                                },
                                indent=2
                            )

                            raw = run_ai(
                                system_prompt,
                                user_prompt
                            )

                            if raw:

                                try:

                                    ai_data = json.loads(
                                        raw
                                    )

                                except Exception:

                                    ai_data = {
                                        "recommendation":
                                            raw,

                                        "reasons":
                                            [],

                                        "tradeoffs":
                                            [],

                                        "buying_tips":
                                            []
                                    }

                        st.session_state.last_recommendation = {

                            "best":
                                best,

                            "alternatives":
                                alternatives,

                            "ai":
                                ai_data,

                            "budget":
                                budget
                        }

            recommendation = (
                st.session_state.last_recommendation
            )

            if recommendation:

                best = recommendation[
                    "best"
                ]

                alternatives = recommendation[
                    "alternatives"
                ]

                ai = recommendation[
                    "ai"
                ]

                st.divider()

                st.subheader(
                    "🏆 Recommended Combination"
                )

                c1, c2, c3 = st.columns(3)

                with c1:

                    st.metric(
                        "Total Cost",
                        money(best["total"])
                    )

                with c2:

                    st.metric(
                        "Remaining Budget",
                        money(best["remaining"])
                    )

                with c3:

                    st.metric(
                        "Plan Score",
                        f"{best['score']}/100"
                    )

                # Safety check
                if best["total"] > budget:

                    st.error(
                        "⚠️ ERROR: Recommended combination "
                        "exceeds your budget."
                    )

                else:

                    st.success(
                        f"✅ Combination is within "
                        f"{money(budget)} budget."
                    )

                for index, product in enumerate(
                    best["products"]
                ):

                    render_product_card(
                        product,
                        card_key=f"recommendation_{index}",
                        show_compare=False,
                        show_save=True
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

                if ai.get(
                    "reasons"
                ):

                    st.subheader(
                        "Why this combination?"
                    )

                    for reason in ai[
                        "reasons"
                    ]:

                        st.markdown(
                            f"• {reason}"
                        )

                if ai.get(
                    "tradeoffs"
                ):

                    st.subheader(
                        "⚖️ Trade-offs"
                    )

                    for tradeoff in ai[
                        "tradeoffs"
                    ]:

                        st.markdown(
                            f"• {tradeoff}"
                        )

                if ai.get(
                    "buying_tips"
                ):

                    st.subheader(
                        "💡 Buying Tips"
                    )

                    for tip in ai[
                        "buying_tips"
                    ]:

                        st.markdown(
                            f"• {tip}"
                        )

                if len(
                    alternatives
                ) > 1:

                    st.subheader(
                        "🔄 Alternative Combinations"
                    )

                    for index, option in enumerate(
                        alternatives[1:5],
                        1
                    ):

                        with st.container(
                            border=True
                        ):

                            st.write(
                                f"**Option {index}**"
                            )

                            st.write(
                                " + ".join(
                                    p["name"]
                                    for p in option[
                                        "products"
                                    ]
                                )
                            )

                            st.caption(
                                f"Total: "
                                f"{money(option['total'])}"
                                f" | Remaining: "
                                f"{money(option['remaining'])}"
                                f" | Score: "
                                f"{option['score']}/100"
                            )


# =========================================================
# BUDGET PLANNER
# =========================================================

elif menu == "💰 Budget Planner":

    page_header(
        "💰 Budget Planner",
        "Find product combinations that never exceed your total budget."
    )

    if not st.session_state.products:

        st.info(
            "Search products first."
        )

    else:

        budget = st.number_input(
            "💰 Available Budget (₹)",
            min_value=500,
            max_value=10000000,
            value=int(
                st.session_state.budget
            ),
            step=500
        )

        strategy = st.selectbox(
            "Strategy",
            [
                "Best Overall Value",
                "Lowest Cost",
                "Highest Rating"
            ]
        )

        if st.button(
            "💰 Optimize Budget",
            type="primary"
        ):

            best, alternatives = (
                optimize_combination(
                    st.session_state.products,
                    budget,
                    strategy
                )
            )

            if not best:

                st.error(
                    "No complete combination fits "
                    "within your budget."
                )

            else:

                # Final safety check
                if best["total"] > budget:

                    st.error(
                        "Invalid combination detected."
                    )

                else:

                    st.success(
                        "Best combination found!"
                    )

                    c1, c2, c3 = st.columns(3)

                    with c1:

                        st.metric(
                            "Budget",
                            money(budget)
                        )

                    with c2:

                        st.metric(
                            "Total",
                            money(best["total"])
                        )

                    with c3:

                        st.metric(
                            "Remaining",
                            money(best["remaining"])
                        )

                    st.subheader(
                        "🏆 Recommended Combination"
                    )

                    for index, product in enumerate(
                        best["products"]
                    ):

                        render_product_card(
                            product,
                            card_key=f"budget_{index}",
                            show_compare=False,
                            show_save=True
                        )

                    st.subheader(
                        "🔄 Alternative Plans"
                    )

                    for index, option in enumerate(
                        alternatives[1:5],
                        1
                    ):

                        with st.container(
                            border=True
                        ):

                            st.write(
                                f"**Option {index}**"
                            )

                            st.write(
                                " + ".join(
                                    p["name"]
                                    for p in option[
                                        "products"
                                    ]
                                )
                            )

                            st.caption(
                                f"Total: "
                                f"{money(option['total'])}"
                                f" | Remaining: "
                                f"{money(option['remaining'])}"
                                f" | Score: "
                                f"{option['score']}/100"
                            )


# =========================================================
# SAVED PRODUCTS
# =========================================================

elif menu == "❤️ Saved Products":

    page_header(
        "❤️ Saved Products",
        "Products you saved for later."
    )

    if not st.session_state.saved_products:

        st.info(
            "No saved products yet."
        )

    else:

        st.write(
            f"You have "
            f"**{len(st.session_state.saved_products)}** "
            f"saved products."
        )

        if st.button(
            "🗑️ Clear All Saved Products"
        ):

            st.session_state.saved_products = []

            st.rerun()

        for index, product in enumerate(
            st.session_state.saved_products
        ):

            render_product_card(
                product,
                card_key=f"saved_{index}",
                show_compare=False,
                show_save=False
            )


# =========================================================
# SETTINGS
# =========================================================

elif menu == "⚙️ Settings":

    page_header(
        "⚙️ Settings",
        "Configure SmartShop AI."
    )

    st.subheader(
        "🔌 API Status"
    )

    col1, col2 = st.columns(2)

    with col1:

        if GROQ_API_KEY:

            st.success(
                "Groq API: Connected"
            )

        else:

            st.warning(
                "Groq API: Not configured"
            )

    with col2:

        if SERPAPI_API_KEY:

            st.success(
                "SerpAPI: Connected"
            )

        else:

            st.warning(
                "SerpAPI: Not configured"
            )

    st.divider()

    st.subheader(
        "🔎 Search Settings"
    )

    max_results = st.slider(
        "Results per category",
        3,
        15,
        int(
            st.session_state.settings[
                "max_results"
            ]
        )
    )

    st.subheader(
        "🤖 AI Settings"
    )

    temperature = st.slider(
        "AI Temperature",
        0.0,
        0.5,
        float(
            st.session_state.settings[
                "ai_temperature"
            ]
        ),
        0.05
    )

    if st.button(
        "💾 Save Settings"
    ):

        st.session_state.settings = {

            "max_results":
                max_results,

            "ai_temperature":
                temperature
        }

        st.success(
            "Settings saved."
        )

    st.divider()

    st.subheader(
        "🧹 Reset Application"
    )

    if st.button(
        "Reset Shopping Session"
    ):

        st.session_state.products = []

        st.session_state.selected_ids = []

        st.session_state.saved_products = []

        st.session_state.search_history = []

        st.session_state.last_recommendation = None

        st.session_state.categories = []

        st.session_state.preferences = ""

        st.success(
            "Shopping session reset."
        )

        st.rerun()

    st.divider()

    st.subheader(
        "📌 About SmartShop AI"
    )

    st.write(
        """
        **SmartShop AI** is an AI-powered shopping
        comparison and budget optimization agent.

        ### Features

        • Shopping website product search

        • Budget filtering

        • Product comparison

        • Price comparison

        • Rating analysis

        • Review analysis

        • Manual product selection

        • Automatic product selection

        • Budget-constrained optimization

        • AI recommendation

        • Alternative combinations

        • Direct shopping website links

        ### Technology

        Python + Streamlit + Groq + SerpAPI

        Shopping data is retrieved from Google Shopping
        through SerpAPI and localized for India.
        """
    )
