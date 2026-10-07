
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
# GLOBAL CSS
# =========================================================

st.markdown("""
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
        margin-bottom: .35rem;
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
        font-size: 1.45rem;
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
""", unsafe_allow_html=True)


# =========================================================
# API SETUP
# =========================================================

def get_secret(name):
    """Read an environment variable or Streamlit secret without crashing the UI."""
    value = os.environ.get(name)
    if value:
        return value.strip()
    try:
        value = st.secrets.get(name, "")
        return str(value).strip() if value else ""
    except Exception:
        return ""


groq_api_key = get_secret("GROQ_API_KEY")
serpapi_api_key = get_secret("SERPAPI_API_KEY")

# Do not create an API client during page startup. The website should always render,
# even when the optional Groq key has not been configured yet.
groq_client = None


def get_groq_client():
    global groq_client
    if groq_client is None and groq_api_key:
        try:
            groq_client = Groq(api_key=groq_api_key)
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
    "comparison_ids": [],
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
# HELPERS
# =========================================================

def money(value):
    try:
        return f"₹{float(value):,.0f}"
    except Exception:
        return "Price unavailable"

def clean_price(price):
    if price is None:
        return None

    if isinstance(price, (int, float)):
        return float(price)

    text = str(price).strip()
    text = (text.replace("₹", "").replace("$", "").replace("€", "")
             .replace("£", "").replace(",", "").strip())

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
    except ValueError:
        return None

def safe_float(value, default=0):
    try:
        return float(value)
    except Exception:
        return default


def normalize_product(item, category):
    price = clean_price(item.get("price"))
    name = item.get("title", "Unknown Product")
    link = item.get("link", "")
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

def search_shopping(query, max_results=8):
    if not serpapi_api_key:
        st.error("❌ SERPAPI_API_KEY is not configured. Add it in Streamlit Secrets.")
        return []

    params = {
        "engine": "google_shopping",
        "q": query,
        "api_key": serpapi_api_key,
        "location": "India",
        "google_domain": "google.co.in",
        "gl": "in",
        "hl": "en",
        "num": max_results,
    }

    try:
        response = requests.get("https://serpapi.com/search.json", params=params, timeout=30)
        if response.status_code == 401:
            st.error("❌ Invalid SerpAPI key. Check SERPAPI_API_KEY in Streamlit Secrets.")
            return []
        if response.status_code == 429:
            st.warning("⚠️ SerpAPI request limit reached. Check your quota or hourly request limit.")
            return []
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            st.warning(f"SerpAPI error: {data['error']}")
            return []
        return data.get("shopping_results", [])
    except requests.exceptions.Timeout:
        st.error("⏱️ Shopping search timed out. Please try again.")
        return []
    except requests.exceptions.RequestException as exc:
        st.error(f"Shopping search failed: {exc}")
        return []

def run_agent(system_prompt, user_prompt, json_mode=True):
    client = get_groq_client()
    if not client:
        return None, 0

    start = time.time()

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=st.session_state.settings["ai_temperature"],
        response_format={"type": "json_object"} if json_mode else {"type": "text"},
    )

    latency = round(time.time() - start, 2)
    return response.choices[0].message.content, latency


# Preference profiles used by both the shopping search and the ranking layer.
# The first terms are stronger signals; the rest are supporting signals.
PREFERENCE_PROFILES = {
    "gaming": [
        ("gaming", 10), ("rtx", 9), ("gtx", 9), ("geforce", 8),
        ("radeon", 8), ("arc graphics", 7), ("dedicated graphics", 8),
        ("high refresh", 7), ("144hz", 7), ("165hz", 7), ("240hz", 7),
        ("tuf", 6), ("rog", 6), ("legion", 6), ("loq", 6),
        ("nitro", 6), ("predator", 6), ("omen", 6), ("victus", 6)
    ],
    "student": [
        ("student", 10), ("study", 8), ("education", 8), ("portable", 7),
        ("lightweight", 7), ("battery", 6), ("long battery", 8),
        ("everyday", 5), ("office", 5), ("value", 5), ("budget", 5)
    ],
    "lightweight": [
        ("lightweight", 10), ("portable", 9), ("thin", 7), ("slim", 7),
        ("ultraportable", 9), ("compact", 6), ("thin and light", 10)
    ],
    "programming": [
        ("programming", 10), ("developer", 9), ("development", 8),
        ("coding", 10), ("code", 7), ("software", 7), ("linux", 6),
        ("16gb", 6), ("core i5", 5), ("core i7", 6), ("ryzen 5", 5),
        ("ryzen 7", 6), ("ssd", 5)
    ],
    "business": [
        ("business", 10), ("professional", 8), ("enterprise", 7),
        ("office", 6), ("productivity", 8), ("security", 6),
        ("reliable", 6), ("thinkpad", 7), ("latitude", 7), ("elitebook", 7)
    ],
    "long battery": [
        ("long battery", 10), ("battery life", 10), ("all day battery", 10),
        ("long-lasting battery", 10), ("battery", 6), ("power efficient", 7),
        ("energy efficient", 7)
    ],
    "16gb ram": [
        ("16gb", 10), ("16 gb", 10), ("16gb ram", 10), ("32gb", 8),
        ("32 gb", 8), ("memory", 4), ("ram", 4)
    ],
    "video editing": [
        ("video editing", 10), ("video editor", 9), ("premiere pro", 9),
        ("davinci resolve", 9), ("after effects", 8), ("4k editing", 9),
        ("rtx", 7), ("dedicated graphics", 8), ("32gb", 7), ("16gb", 6)
    ],
    "ai/ml": [
        ("ai/ml", 10), ("machine learning", 10), ("deep learning", 10),
        ("artificial intelligence", 9), ("cuda", 10), ("nvidia", 7),
        ("rtx", 8), ("dedicated graphics", 8), ("gpu", 8),
        ("16gb", 6), ("32gb", 7)
    ],
}


def get_preference_keys(preferences):
    text = str(preferences or "").lower().strip()
    keys = []
    for key in PREFERENCE_PROFILES:
        if key in text:
            keys.append(key)
    return keys


def preference_search_terms(preferences):
    """Return concise search terms for recognized preferences plus useful custom words."""
    text = str(preferences or "").lower().strip()
    keys = get_preference_keys(text)
    terms = []

    for key in keys:
        terms.append(key)

    # Keep meaningful custom words too, so user-entered preferences such as
    # OLED, 1TB SSD, touchscreen, etc. can influence the shopping query.
    custom_words = [
        word for word in text.replace(",", " ").split()
        if len(word) >= 4 and word not in {"with", "good", "best", "want", "need", "for", "laptop"}
    ]

    for word in custom_words:
        if word not in terms:
            terms.append(word)

    return terms[:10]


def preference_relevance(product, preferences=""):
    """Score how strongly a product matches the user's stated preferences."""
    text = (
        str(product.get("name", "")) + " " +
        str(product.get("snippet", "")) + " " +
        str(product.get("source", ""))
    ).lower()

    keys = get_preference_keys(preferences)
    if not keys and not str(preferences).strip():
        return 0

    score = 0
    matched = []

    for key in keys:
        for term, weight in PREFERENCE_PROFILES[key]:
            if term in text:
                score += weight
                matched.append(term)

    # Custom preference words still contribute.
    for word in preference_search_terms(preferences):
        if word not in keys and word in text:
            score += 3
            matched.append(word)

    # Normalize to a 0-100 range while preserving differences between products.
    max_possible = sum(
        max(weight for _, weight in PREFERENCE_PROFILES[key])
        for key in keys
    ) or 10

    relevance = min((score / max_possible) * 100, 100)
    product["preference_relevance"] = round(relevance, 1)
    product["matched_preferences"] = list(dict.fromkeys(matched))[:8]
    return product["preference_relevance"]


def product_score(product, preferences="", priorities=None):
    priorities = priorities or []

    rating = min(max(safe_float(product.get("rating")), 0), 5) / 5 * 100
    reviews = safe_float(product.get("reviews"))
    review_score = min(reviews / 1000 * 100, 100)

    price = product.get("price")
    price_score = 40 if price is None else 70

    preference_score = preference_relevance(product, preferences)

    # Preference relevance is deliberately the strongest factor.
    score = (
        rating * 0.30 +
        review_score * 0.10 +
        price_score * 0.10 +
        preference_score * 0.50
    )

    if "High Rating" in priorities:
        score += rating * 0.10

    if "Customer Reviews" in priorities:
        score += review_score * 0.05

    return min(round(score, 1), 100)


def get_categories():
    return sorted(
        list(
            dict.fromkeys(
                p.get("category", "Other")
                for p in st.session_state.products
            )
        )
    )


def get_product_by_id(product_id):
    for p in st.session_state.products:
        if p["id"] == product_id:
            return p
    return None


def optimize_combination(products, budget):
    """
    Deterministic optimization layer.
    Tries to choose one product per category.
    Uses a score that balances quality and budget.
    """
    valid = [
        p for p in products
        if p.get("price") is not None and p.get("price") <= budget
    ]

    categories = sorted(
        list(dict.fromkeys(p.get("category", "Other") for p in valid))
    )

    if not categories:
        return None, []

    grouped = {
        category: sorted(
            [p for p in valid if p.get("category") == category],
            key=lambda x: product_score(
                x,
                st.session_state.preferences
            ),
            reverse=True,
        )[:6]
        for category in categories
    }

    if any(not values for values in grouped.values()):
        return None, []

    best = None
    alternatives = []

    for combo in cartesian_product(*grouped.values()):
        total = sum((p.get("price") or 0) for p in combo)

        if total > budget:
            continue

        scores = [
            product_score(
                p,
                st.session_state.preferences
            )
            for p in combo
        ]

        average_score = sum(scores) / len(scores)

        # Slight preference for leaving some budget unused,
        # without overwhelming product quality.
        budget_efficiency = min(total / budget, 1) * 10
        final_score = average_score + budget_efficiency

        record = {
            "products": list(combo),
            "total": total,
            "remaining": budget - total,
            "score": round(final_score, 1),
        }

        alternatives.append(record)

        if best is None or record["score"] > best["score"]:
            best = record

    alternatives.sort(key=lambda x: x["score"], reverse=True)

    unique = []
    seen = set()

    for option in alternatives:
        ids = tuple(sorted(p["id"] for p in option["products"]))
        if ids not in seen:
            seen.add(ids)
            unique.append(option)

    return best, unique[:5]


def render_product_card(product, show_select=True, show_save=True):
    # Every card gets a unique widget namespace, even when shopping
    # results contain duplicate product IDs.
    widget_key = f"{product.get('id', 'product')}_{id(product)}"

    with st.container(border=True):
        cols = st.columns([4, 1.3, 1.3, 1.4])

        with cols[0]:
            st.markdown(f"### {product.get('name', 'Product')}")
            st.caption(
                f"{product.get('category', 'Other')} • "
                f"{product.get('source', 'Unknown')}"
            )
            if product.get("snippet"):
                st.write(product["snippet"][:300])

            if st.session_state.preferences:
                relevance = preference_relevance(
                    product,
                    st.session_state.preferences
                )
                matches = product.get("matched_preferences", [])
                st.caption(
                    f"🎯 Preference match: {relevance:.0f}%"
                    + (f" • {', '.join(matches[:5])}" if matches else "")
                )

        with cols[1]:
            st.metric("Price", money(product.get("price")))

        with cols[2]:
            st.metric(
                "Rating",
                f"{safe_float(product.get('rating')):.1f}/5"
            )
            st.caption(f"{int(safe_float(product.get('reviews'))):,} reviews")

        with cols[3]:
            if show_select:
                checked = product["id"] in st.session_state.selected_ids
                if st.checkbox(
                    "Select",
                    value=checked,
                    key=f"select_{product['id']}"
                ):
                    if product["id"] not in st.session_state.selected_ids:
                        st.session_state.selected_ids.append(product["id"])
                else:
                    if product["id"] in st.session_state.selected_ids:
                        st.session_state.selected_ids.remove(product["id"])

            if show_save:
                saved = any(
                    x["id"] == product["id"]
                    for x in st.session_state.saved_products
                )

                if st.button(
                    "❤️ Saved" if saved else "♡ Save",
                    key=f"save_{widget_key}"
                ):
                    if saved:
                        st.session_state.saved_products = [
                            x for x in st.session_state.saved_products
                            if x["id"] != product["id"]
                        ]
                    else:
                        st.session_state.saved_products.append(product)

                    st.rerun()

            if product.get("link"):
                st.link_button("View", product["link"])


def show_page_header(title, subtitle):
    st.markdown(
        f"""
        <div class="hero">
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:
    st.markdown("# 🛍️ SmartShop AI")
    st.caption("AI Shopping Comparison & Optimization")

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
            "⚙️ Settings",
        ],
        label_visibility="collapsed",
    )

    st.divider()

    st.markdown("### Current Shopping Session")
    st.metric("Products", len(st.session_state.products))
    st.metric("Saved", len(st.session_state.saved_products))
    st.metric("Budget", money(st.session_state.budget))

    st.divider()
    st.caption("SmartShop AI • Data-driven shopping decisions")


# =========================================================
# PAGE 1: HOME
# =========================================================

if menu == "🏠 Home":

    show_page_header(
        "🛍️ Shop Smarter with AI",
        "Compare products, optimize your budget, and let AI build the best shopping combination."
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Products Researched", len(st.session_state.products))

    with col2:
        st.metric("Saved Products", len(st.session_state.saved_products))

    with col3:
        st.metric("Current Budget", money(st.session_state.budget))

    st.markdown("## How SmartShop AI works")

    steps = [
        ("01", "🔎 Research", "Find products from shopping sources."),
        ("02", "⚖️ Compare", "Compare price, rating, reviews and available information."),
        ("03", "🎯 Select", "Choose manually or let AI select automatically."),
        ("04", "💰 Optimize", "Find the best combination within your budget."),
    ]

    cols = st.columns(4)

    for col, (number, title, text) in zip(cols, steps):
        with col:
            st.markdown(
                f"""
                <div class="card">
                    <div class="small-muted">{number}</div>
                    <h3>{title}</h3>
                    <p>{text}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("## Quick Start")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.info("**Example:** Headphones, shoes, backpack")

    with c2:
        st.info("**Example budget:** ₹20,000")

    with c3:
        st.info("**Example priority:** Quality + rating + value")

    st.markdown("## What makes this an AI/Data Science project?")

    st.write(
        """
        SmartShop AI combines shopping research with data-driven product scoring,
        user preference matching, budget-constrained optimization, and an AI
        explanation layer. The system can recommend a single product or optimize
        a combination of products from different categories.
        """
    )


# =========================================================
# PAGE 2: PRODUCT RESEARCH
# =========================================================

elif menu == "🔎 Product Research":

    show_page_header(
        "🔎 Product Research",
        "Search shopping sources and build your product comparison dataset."
    )

    col1, col2 = st.columns([2, 1])

    with col1:
        categories_text = st.text_input(
            "What do you want to buy?",
            value=", ".join(st.session_state.categories),
            placeholder="headphones, shoes, backpack",
        )

    with col2:
        budget = st.number_input(
            "Shopping Budget (₹)",
            min_value=500,
            value=int(st.session_state.budget),
            step=500,
        )

    preference_choices = st.multiselect(
        "🎯 Quick Preferences",
        [
            "Gaming",
            "Student",
            "Lightweight",
            "Programming",
            "Business",
            "Long Battery",
            "16GB RAM",
            "Video Editing",
            "AI/ML",
        ],
        help="Select one or more requirements. These will affect both the shopping search and product ranking.",
    )

    custom_preferences = st.text_area(
        "Additional Preferences",
        value="",
        placeholder="Example: OLED display, 1TB SSD, touchscreen, good keyboard",
    )

    preference_parts = list(preference_choices)
    if custom_preferences.strip():
        preference_parts.append(custom_preferences.strip())

    preferences = ", ".join(preference_parts)

    if preference_choices:
        st.info(
            "Preference matching is active: "
            + ", ".join(preference_choices)
        )

    col1, col2, col3 = st.columns(3)

    with col1:
        max_results = st.slider(
            "Results per category",
            3,
            15,
            int(st.session_state.settings["max_results"]),
        )

    with col2:
        priorities = st.multiselect(
            "Priorities",
            [
                "Low Price",
                "High Rating",
                "Quality",
                "Features",
                "Customer Reviews",
                "Brand",
                "Value for Money",
            ],
            default=[
                "Quality",
                "High Rating",
                "Value for Money",
            ],
        )

    with col3:
        search_mode = st.selectbox(
            "Research mode",
            ["Standard Search", "Preference-focused Search"],
        )

    if st.button("🔎 Search Shopping Sources", type="primary"):

        # Always clear previous search results before a new search.
        st.session_state.products = []
        st.session_state.selected_ids = []
        st.session_state.last_recommendation = None
        st.session_state.last_search_message = ""

        categories = [
            x.strip()
            for x in categories_text.split(",")
            if x.strip()
        ]

        if not categories:
            st.warning("Enter at least one product category.")
        elif not serpapi_api_key:
            st.error(
                "SERPAPI_API_KEY is not configured. Add it in Streamlit Secrets."
            )
        else:
            st.session_state.budget = budget
            st.session_state.preferences = preferences
            st.session_state.categories = categories
            st.session_state.settings["max_results"] = max_results

            found = []

            with st.status("Researching products...", expanded=True) as status:

                for category in categories:

                    query = category

                    # Always include the user's preferences in the shopping
                    # query. This makes preferences affect which products are
                    # retrieved, not only how they are ranked afterwards.
                    if preferences.strip():
                        search_terms = preference_search_terms(preferences)
                        if search_terms:
                            query += " " + " ".join(search_terms)

                    if search_mode == "Preference-focused Search" and preferences.strip():
                        query += " best match"

                    st.write(f"🛒 Searching for **{category}**...")

                    raw_products = search_shopping(
                        query,
                        max_results
                    )

                    for item in raw_products:
                        product_item = normalize_product(
                            item,
                            category
                        )

                        # Calculate preference relevance immediately so the
                        # returned dataset itself is preference-aware.
                        preference_relevance(
                            product_item,
                            preferences
                        )

                        found.append(product_item)

                # If matching products exist for a category, remove products
                # that have zero preference relevance. If the source gives no
                # detectable match at all, keep the results rather than showing
                # an empty page.
                if preferences.strip():
                    grouped = {}
                    for product_item in found:
                        grouped.setdefault(
                            product_item.get("category", "Other"), []
                        ).append(product_item)

                    preference_filtered = []
                    for category_products in grouped.values():
                        matching = [
                            p for p in category_products
                            if preference_relevance(p, preferences) > 0
                        ]
                        preference_filtered.extend(
                            matching if matching else category_products
                        )
                    found = preference_filtered

                # Preference-aware ranking happens before the products are
                # displayed, compared, or passed to the AI advisor.
                found.sort(
                    key=lambda p: (
                        preference_relevance(p, preferences),
                        safe_float(p.get("rating")),
                        safe_float(p.get("reviews")),
                    ),
                    reverse=True,
                )

                st.session_state.products = found
                st.session_state.selected_ids = []
                st.session_state.last_search_message = (
                    f"Shopping research completed — {len(found)} products found."
                )

                st.session_state.search_history.insert(
                    0,
                    {
                        "query": categories_text,
                        "budget": budget,
                        "count": len(found),
                    },
                )

                status.update(
                    label=st.session_state.last_search_message,
                    state="complete",
                    expanded=False,
                )

    if st.session_state.last_search_message:
        if st.session_state.products:
            st.success(st.session_state.last_search_message)
        else:
            st.warning(st.session_state.last_search_message)

    if st.session_state.products:

        st.divider()
        st.subheader(
            f"📦 {len(st.session_state.products)} Products Found"
        )

        categories = get_categories()

        selected_category = st.selectbox(
            "Filter by category",
            ["All"] + categories,
        )

        filtered = st.session_state.products

        if selected_category != "All":
            filtered = [
                p for p in filtered
                if p.get("category") == selected_category
            ]

        for product in filtered:
            render_product_card(product)


# =========================================================
# PAGE 3: COMPARE PRODUCTS
# =========================================================

elif menu == "⚖️ Compare Products":

    show_page_header(
        "⚖️ Compare Products",
        "Select products manually and compare their price, rating, reviews and value."
    )

    if not st.session_state.products:
        st.info("No products available. Go to Product Research first.")
    else:

        st.write(
            f"Selected products: **{len(st.session_state.selected_ids)}**"
        )

        if st.button("Clear Selection"):
            st.session_state.selected_ids = []
            st.rerun()

        st.divider()

        for product in st.session_state.products:
            render_product_card(product)

        selected = [
            get_product_by_id(pid)
            for pid in st.session_state.selected_ids
        ]
        selected = [p for p in selected if p]

        if len(selected) >= 2:

            st.divider()
            st.subheader("📊 Comparison")

            rows = []

            for p in selected:
                rows.append(
                    {
                        "Product": p["name"],
                        "Category": p["category"],
                        "Source": p["source"],
                        "Price": money(p["price"]),
                        "Rating": f"{p['rating']:.1f}/5",
                        "Reviews": int(p["reviews"]),
                        "Score": product_score(
                            p,
                            st.session_state.preferences
                        ),
                    }
                )

            st.dataframe(
                rows,
                use_container_width=True,
                hide_index=True,
            )

            best = max(
                selected,
                key=lambda p: product_score(
                    p,
                    st.session_state.preferences
                )
            )

            st.success(
                f"🏆 Current highest-scoring product: **{best['name']}**"
            )

        elif selected:
            st.info("Select at least 2 products to compare.")
        else:
            st.info("Select products above to start comparing.")


# =========================================================
# PAGE 4: AI SHOPPING ADVISOR
# =========================================================

elif menu == "🤖 AI Shopping Advisor":

    show_page_header(
        "🤖 AI Shopping Advisor",
        "Let the AI analyze products and select the best shopping combination."
    )

    if not st.session_state.products:
        st.info("Research products first.")
    else:

        col1, col2, col3 = st.columns(3)

        with col1:
            budget = st.number_input(
                "Budget (₹)",
                min_value=500,
                value=int(st.session_state.budget),
                step=500,
            )

        with col2:
            mode = st.selectbox(
                "Selection Mode",
                [
                    "Automatic Selection",
                    "Manual Selection",
                ],
            )

        with col3:
            priority = st.selectbox(
                "Main Strategy",
                [
                    "Best Overall Value",
                    "Lowest Cost",
                    "Highest Quality",
                    "Highest Rating",
                ],
            )

        preferences = st.text_area(
            "Shopping preferences",
            value=st.session_state.preferences,
        )

        selected_manual = [
            get_product_by_id(pid)
            for pid in st.session_state.selected_ids
        ]
        selected_manual = [p for p in selected_manual if p]

        if mode == "Manual Selection":

            st.info(
                f"You currently have {len(selected_manual)} selected products. "
                "Go to Compare Products if you want to change them."
            )

        if st.button(
            "🚀 Run AI Shopping Advisor",
            type="primary"
        ):

            products_for_ai = (
                selected_manual
                if mode == "Manual Selection"
                else st.session_state.products
            )

            if mode == "Manual Selection" and not products_for_ai:
                st.warning("Select products first.")
                st.stop()

            # Deterministic optimization
            best, alternatives = optimize_combination(
                products_for_ai,
                budget
            )

            # AI explanation
            ai_result = {}

            client = get_groq_client()
            if client:

                system_prompt = """
You are a shopping intelligence advisor.

Analyze the supplied product data and optimization result.

Do not invent specifications, prices, ratings or review facts.
Explain recommendations using only supplied data.

Return JSON:
{
    "recommendation": "string",
    "reasons": ["string"],
    "tradeoffs": ["string"],
    "buying_tips": ["string"]
}
"""

                user_prompt = json.dumps(
                    {
                        "budget": budget,
                        "mode": mode,
                        "strategy": priority,
                        "preferences": preferences,
                        "best_combination": best,
                        "alternatives": alternatives[:3],
                    },
                    indent=2,
                    default=str,
                )

                raw, _ = run_agent(
                    system_prompt,
                    user_prompt,
                    json_mode=True
                )

                try:
                    ai_result = json.loads(raw)
                except Exception:
                    ai_result = {
                        "recommendation": raw,
                        "reasons": [],
                        "tradeoffs": [],
                        "buying_tips": [],
                    }

            if not best:

                st.warning(
                    "No complete combination fits within the selected budget."
                )

            else:

                st.session_state.last_recommendation = {
                    "best": best,
                    "alternatives": alternatives,
                    "ai": ai_result,
                    "budget": budget,
                    "mode": mode,
                }

        recommendation = st.session_state.last_recommendation

        if recommendation:

            best = recommendation["best"]
            alternatives = recommendation["alternatives"]
            ai = recommendation["ai"]

            st.divider()
            st.subheader("🏆 AI Recommended Shopping Plan")

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

            for p in best["products"]:
                render_product_card(
                    p,
                    show_select=False,
                    show_save=True
                )

            if ai.get("recommendation"):
                st.info(
                    "**AI Recommendation:** "
                    + ai["recommendation"]
                )

            if ai.get("reasons"):
                st.markdown("### Why AI selected this combination")
                for reason in ai["reasons"]:
                    st.markdown(f"• {reason}")

            if ai.get("tradeoffs"):
                st.markdown("### ⚖️ Trade-offs")
                for item in ai["tradeoffs"]:
                    st.markdown(f"• {item}")

            if ai.get("buying_tips"):
                st.markdown("### 💡 Buying Tips")
                for item in ai["buying_tips"]:
                    st.markdown(f"• {item}")

            st.markdown("### 🔄 Alternative Combinations")

            for i, option in enumerate(alternatives[1:4], 1):

                with st.container(border=True):

                    st.markdown(
                        f"**Option {i}** — "
                        f"{money(option['total'])}"
                    )

                    st.caption(
                        f"Score: {option['score']}/100 • "
                        f"Remaining: {money(option['remaining'])}"
                    )

                    st.write(
                        ", ".join(
                            p["name"]
                            for p in option["products"]
                        )
                    )


# =========================================================
# PAGE 5: BUDGET PLANNER
# =========================================================

elif menu == "💰 Budget Planner":

    show_page_header(
        "💰 Budget Planner",
        "Find the strongest product combination for your budget."
    )

    if not st.session_state.products:
        st.info("Research products first.")
    else:

        budget = st.number_input(
            "Available Budget (₹)",
            min_value=500,
            value=int(st.session_state.budget),
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
            type="primary"
        ):

            best, alternatives = optimize_combination(
                st.session_state.products,
                budget
            )

            if not best:
                st.error(
                    "No combination containing all categories "
                    "can currently fit this budget."
                )
            else:

                st.session_state.last_recommendation = {
                    "best": best,
                    "alternatives": alternatives,
                    "ai": {},
                    "budget": budget,
                    "mode": "Automatic",
                }

                st.success(
                    f"Best combination found: "
                    f"{money(best['total'])}"
                )

                c1, c2, c3 = st.columns(3)

                with c1:
                    st.metric(
                        "Budget",
                        money(budget)
                    )

                with c2:
                    st.metric(
                        "Plan Cost",
                        money(best["total"])
                    )

                with c3:
                    st.metric(
                        "Remaining",
                        money(best["remaining"])
                    )

                st.markdown("### 🏆 Recommended Combination")

                for p in best["products"]:
                    render_product_card(
                        p,
                        show_select=False
                    )

                st.markdown("### 🔄 Other Possible Plans")

                for option in alternatives[1:5]:

                    with st.container(border=True):

                        st.write(
                            f"**Total:** {money(option['total'])} "
                            f"• **Score:** {option['score']}/100"
                        )

                        st.write(
                            " + ".join(
                                p["name"]
                                for p in option["products"]
                            )
                        )


# =========================================================
# PAGE 6: SAVED PRODUCTS
# =========================================================

elif menu == "❤️ Saved Products":

    show_page_header(
        "❤️ Saved Products",
        "Keep products you may want to compare or purchase later."
    )

    if not st.session_state.saved_products:
        st.info(
            "No saved products yet. Use the ♡ Save button in Product Research."
        )
    else:

        st.write(
            f"You have **{len(st.session_state.saved_products)}** saved products."
        )

        if st.button("Clear All Saved Products"):
            st.session_state.saved_products = []
            st.rerun()

        for product in st.session_state.saved_products:
            render_product_card(
                product,
                show_select=False,
                show_save=True
            )


# =========================================================
# PAGE 7: SETTINGS
# =========================================================

elif menu == "⚙️ Settings":

    show_page_header(
        "⚙️ Settings",
        "Configure the shopping research and AI experience."
    )

    st.subheader("🔌 API Status")

    c1, c2 = st.columns(2)

    with c1:
        if groq_api_key:
            st.success("Groq API: Connected")
        else:
            st.error("Groq API: Not configured")

    with c2:
        if serpapi_api_key:
            st.success("Shopping Search API: Connected")
        else:
            st.error("Shopping Search API: Not configured")

    st.divider()

    st.subheader("🔎 Search Settings")

    max_results = st.slider(
        "Maximum results per category",
        3,
        15,
        int(st.session_state.settings["max_results"]),
    )

    currency = st.selectbox(
        "Currency",
        [
            "INR (₹)",
            "USD ($)",
            "EUR (€)",
        ],
        index=[
            "INR (₹)",
            "USD ($)",
            "EUR (€)",
        ].index(st.session_state.settings["currency"]),
    )

    st.subheader("🤖 AI Settings")

    temperature = st.slider(
        "AI creativity",
        0.0,
        0.5,
        float(st.session_state.settings["ai_temperature"]),
        0.05,
    )

    if st.button("💾 Save Settings"):

        st.session_state.settings = {
            "max_results": max_results,
            "currency": currency,
            "ai_temperature": temperature,
        }

        st.success("Settings saved.")

    st.divider()

    st.subheader("🧹 Session Management")

    if st.button("Reset Shopping Session"):

        st.session_state.products = []
        st.session_state.selected_ids = []
        st.session_state.saved_products = []
        st.session_state.comparison_ids = []
        st.session_state.search_history = []
        st.session_state.last_recommendation = None
        st.session_state.categories = []
        st.session_state.preferences = ""

        st.success("Shopping session reset.")
        st.rerun()

    st.divider()

    st.subheader("📌 Project Information")

    st.write(
        """
        **SmartShop AI** is an AI-powered shopping comparison and
        budget optimization system.

        Core components:

        • Shopping data collection  
        • Product comparison  
        • Data-driven scoring  
        • Manual selection  
        • Automatic selection  
        • Budget-constrained optimization  
        • AI explanation  
        • Saved product management
        """
    )
