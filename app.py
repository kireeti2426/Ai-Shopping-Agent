import streamlit as st
import os
import json
import requests
from itertools import product as cartesian_product
from groq import Groq


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="SmartShop AI",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown("""
<style>

.main-title {
    font-size: 42px;
    font-weight: 800;
    margin-bottom: 5px;
}

.subtitle {
    font-size: 18px;
    color: #777;
    margin-bottom: 25px;
}

.product-card {
    padding: 18px;
    border-radius: 15px;
    border: 1px solid #ddd;
    margin-bottom: 15px;
    background-color: rgba(255,255,255,0.03);
}

.product-title {
    font-size: 20px;
    font-weight: 700;
}

.product-price {
    font-size: 24px;
    font-weight: 800;
}

.brand-badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 20px;
    background: #eeeeee;
    margin-bottom: 8px;
    font-size: 13px;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# API KEYS
# ============================================================

def get_secret(name):
    value = os.environ.get(name)

    if value:
        return value

    try:
        return st.secrets[name]
    except Exception:
        return None


GROQ_API_KEY = get_secret("GROQ_API_KEY")
SERPAPI_API_KEY = get_secret("SERPAPI_API_KEY")


# ============================================================
# SESSION STATE
# ============================================================

defaults = {
    "products": [],
    "selected_ids": [],
    "saved_products": [],
    "search_history": [],
    "last_recommendation": None,

    "min_price": 5000,
    "max_price": 100000,

    "preferences": "",
    "categories": [],

    "settings": {
        "max_results": 10,
        "ai_temperature": 0.1
    }
}

for key, value in defaults.items():

    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def money(value):

    if value is None:
        return "Price unavailable"

    try:
        return f"₹{float(value):,.0f}"
    except:
        return "Price unavailable"


def clean_price(value):

    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value)

    text = (
        text.replace("₹", "")
        .replace(",", "")
        .replace("INR", "")
        .replace("Rs.", "")
        .replace("Rs", "")
        .strip()
    )

    numbers = ""

    for char in text:

        if char.isdigit() or char == ".":

            numbers += char

        elif numbers:
            break

    try:
        return float(numbers)
    except:
        return None


def safe_float(value, default=0):

    try:
        return float(value)
    except:
        return default


def normalize_brand(brand):

    if not brand:
        return ""

    return str(brand).strip().lower()


# ============================================================
# PRODUCT NORMALIZATION
# ============================================================

def normalize_product(item, index=0):

    title = (
        item.get("title")
        or item.get("name")
        or "Unknown Product"
    )

    price = clean_price(
        item.get("price")
        or item.get("extracted_price")
    )

    rating = safe_float(
        item.get("rating"),
        0
    )

    reviews = safe_float(
        item.get("reviews")
        or item.get("review_count"),
        0
    )

    link = (
        item.get("link")
        or item.get("product_link")
        or item.get("url")
        or ""
    )

    thumbnail = (
        item.get("thumbnail")
        or item.get("image")
        or ""
    )

    source = (
        item.get("source")
        or item.get("merchant")
        or "Shopping Website"
    )

    brand = item.get("brand", "")

    # Try to identify brand from title if API does not provide it
    if not brand:

        known_brands = [
            "HP",
            "Lenovo",
            "Acer",
            "ASUS",
            "Dell",
            "Apple",
            "MSI",
            "Samsung",
            "LG",
            "Sony",
            "OnePlus",
            "Xiaomi",
            "Realme",
            "Oppo",
            "Vivo",
            "Motorola",
            "Google",
            "Nothing",
            "Boat",
            "JBL",
            "Canon",
            "Nikon",
            "Logitech"
        ]

        title_lower = title.lower()

        for b in known_brands:

            if b.lower() in title_lower:

                brand = b
                break

    return {
        "id": str(
            item.get("product_id")
            or item.get("id")
            or f"product_{index}_{abs(hash(title))}"
        ),

        "title": title,

        "price": price,

        "rating": rating,

        "reviews": reviews,

        "link": link,

        "thumbnail": thumbnail,

        "source": source,

        "brand": brand,

        "raw": item
    }


# ============================================================
# CATEGORY DETECTION
# ============================================================

def get_category_from_query(query):

    q = query.lower()

    if "laptop" in q:
        return "Laptop"

    if "phone" in q or "smartphone" in q or "mobile" in q:
        return "Smartphone"

    if "headphone" in q or "earphone" in q or "earbuds" in q:
        return "Audio"

    if "tv" in q or "television" in q:
        return "TV"

    if "camera" in q:
        return "Camera"

    if "watch" in q:
        return "Smartwatch"

    return query.strip().title()


# ============================================================
# SERPAPI SHOPPING SEARCH
# ============================================================

def search_shopping(
    query,
    min_price,
    max_price,
    brands=None,
    max_results=10
):

    if not SERPAPI_API_KEY:

        st.error(
            "⚠️ SERPAPI_API_KEY not found. "
            "Add it to Streamlit secrets."
        )

        return []

    category = get_category_from_query(query)

    # --------------------------------------------------------
    # Add selected brands to search query
    # --------------------------------------------------------

    if brands:

        brand_query = " OR ".join(
            [f'"{brand}"' for brand in brands]
        )

        search_query = f"{query} ({brand_query})"

    else:

        search_query = query

    url = "https://serpapi.com/search.json"

    params = {

        "engine": "google_shopping",

        "q": search_query,

        "api_key": SERPAPI_API_KEY,

        "location": "India",

        "google_domain": "google.co.in",

        "gl": "in",

        "hl": "en",

        "num": max_results
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=30
        )

        if response.status_code != 200:

            st.error(
                f"Shopping API error: "
                f"{response.status_code}"
            )

            return []

        data = response.json()

        results = data.get(
            "shopping_results",
            []
        )

        products = []

        for i, item in enumerate(results):

            p = normalize_product(
                item,
                i
            )

            p["category"] = category

            products.append(p)

        return products

    except Exception as e:

        st.error(
            f"Unable to fetch shopping data: {e}"
        )

        return []


# ============================================================
# STRICT PRODUCT FILTER
# ============================================================

def filter_products(
    products,
    min_price,
    max_price,
    selected_brands=None,
    products_per_category=10
):

    selected_brands_normalized = []

    if selected_brands:

        selected_brands_normalized = [
            normalize_brand(b)
            for b in selected_brands
        ]

    filtered = []

    for p in products:

        price = p.get("price")

        # ----------------------------------------------------
        # PRICE FILTER
        # ----------------------------------------------------

        if price is None:
            continue

        if price < min_price:
            continue

        if price > max_price:
            continue

        # ----------------------------------------------------
        # BRAND FILTER
        # ----------------------------------------------------

        if selected_brands_normalized:

            product_brand = normalize_brand(
                p.get("brand", "")
            )

            title_lower = p.get(
                "title",
                ""
            ).lower()

            brand_match = False

            for brand in selected_brands_normalized:

                if product_brand == brand:

                    brand_match = True
                    break

                # Also check product title
                if brand in title_lower:

                    brand_match = True
                    break

            # IMPORTANT:
            # If a brand was selected and the product
            # does not belong to it, REMOVE it.

            if not brand_match:

                continue

        filtered.append(p)

    # --------------------------------------------------------
    # GROUP BY CATEGORY
    # --------------------------------------------------------

    category_groups = {}

    for p in filtered:

        category = p.get(
            "category",
            "Other"
        )

        if category not in category_groups:

            category_groups[category] = []

        category_groups[category].append(p)

    # --------------------------------------------------------
    # STRICT PRODUCTS PER CATEGORY
    # --------------------------------------------------------

    final_products = []

    for category, items in category_groups.items():

        # Remove duplicates
        unique = {}

        for p in items:

            pid = p["id"]

            if pid not in unique:

                unique[pid] = p

        items = list(unique.values())

        # Sort by rating first
        items.sort(
            key=lambda x: (
                safe_float(x.get("rating")),
                safe_float(x.get("reviews"))
            ),
            reverse=True
        )

        # HARD LIMIT
        items = items[
            :products_per_category
        ]

        final_products.extend(items)

    return final_products


# ============================================================
# PRODUCT LOOKUP
# ============================================================

def get_product_by_id(product_id):

    for p in st.session_state.products:

        if p["id"] == product_id:

            return p

    return None


# ============================================================
# PRODUCT SCORING
# ============================================================

def product_score(product):

    rating = safe_float(
        product.get("rating"),
        0
    )

    reviews = safe_float(
        product.get("reviews"),
        0
    )

    price = safe_float(
        product.get("price"),
        0
    )

    rating_score = min(
        rating / 5,
        1
    )

    review_score = min(
        reviews / 1000,
        1
    )

    if price > 0:

        price_score = min(
            100000 / price,
            1
        )

    else:

        price_score = 0

    return (
        rating_score * 0.50
        + review_score * 0.20
        + price_score * 0.30
    )


# ============================================================
# OPTIMIZE COMBINATION
# ============================================================

def optimize_combination(
    products,
    min_price,
    max_price,
    strategy="Best Overall Value"
):

    if not products:

        return None

    # --------------------------------------------------------
    # Group by category
    # --------------------------------------------------------

    category_groups = {}

    for p in products:

        price = p.get("price")

        if price is None:
            continue

        if price < min_price:
            continue

        if price > max_price:
            continue

        category = p.get(
            "category",
            "Other"
        )

        if category not in category_groups:

            category_groups[category] = []

        category_groups[category].append(p)

    if not category_groups:

        return None

    groups = list(
        category_groups.values()
    )

    best = None

    # --------------------------------------------------------
    # Generate combinations
    # --------------------------------------------------------

    try:

        combinations = cartesian_product(
            *groups
        )

        for combo in combinations:

            prices = [
                safe_float(
                    p.get("price"),
                    0
                )
                for p in combo
            ]

            total = sum(prices)

            # STRICT RANGE
            if total < min_price:
                continue

            if total > max_price:
                continue

            # ----------------------------------------------
            # Strategy scoring
            # ----------------------------------------------

            if strategy == "Lowest Cost":

                score = -total

            elif strategy == "Highest Rating":

                score = sum(
                    safe_float(
                        p.get("rating"),
                        0
                    )
                    for p in combo
                )

            else:

                score = sum(
                    product_score(p)
                    for p in combo
                )

            if best is None:

                best = {
                    "products": list(combo),
                    "total": total,
                    "score": score
                }

            elif score > best["score"]:

                best = {
                    "products": list(combo),
                    "total": total,
                    "score": score
                }

    except Exception:

        return None

    return best


# ============================================================
# AI FUNCTION
# ============================================================

def run_ai(prompt):

    if not GROQ_API_KEY:

        return None

    try:

        client = Groq(
            api_key=GROQ_API_KEY
        )

        response = client.chat.completions.create(

           model="openai/gpt-oss-20b",
            messages=[

                {
                    "role": "system",
                    "content": """
You are an AI shopping advisor.

Analyze products objectively.

Consider:
- Price
- Rating
- Reviews
- Brand
- Value
- User preferences

Do not invent specifications.
"""
                },

                {
                    "role": "user",
                    "content": prompt
                }
            ],

            temperature=st.session_state.settings[
                "ai_temperature"
            ]
        )

        return response.choices[0].message.content

    except Exception as e:

        return f"AI error: {e}"


# ============================================================
# PRODUCT CARD
# ============================================================

def render_product_card(
    product,
    card_key,
    show_compare=True
):

    st.markdown(
        '<div class="product-card">',
        unsafe_allow_html=True
    )

    col1, col2 = st.columns(
        [1, 3]
    )

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    with col1:

        if product.get("thumbnail"):

            try:

                st.image(
                    product["thumbnail"],
                    use_container_width=True
                )

            except:

                st.write("🛍️")

        else:

            st.write("🛍️")

    # --------------------------------------------------------
    # DETAILS
    # --------------------------------------------------------

    with col2:

        st.markdown(
            f"""
            <div class="product-title">
            {product.get("title", "Product")}
            </div>
            """,
            unsafe_allow_html=True
        )

        brand = product.get(
            "brand",
            ""
        )

        if brand:

            st.markdown(
                f"""
                <span class="brand-badge">
                {brand}
                </span>
                """,
                unsafe_allow_html=True
            )

        st.markdown(
            f"""
            <div class="product-price">
            {money(product.get("price"))}
            </div>
            """,
            unsafe_allow_html=True
        )

        rating = product.get(
            "rating",
            0
        )

        reviews = product.get(
            "reviews",
            0
        )
# --------------------------------------------------------
# PREFERENCE MATCH
# --------------------------------------------------------

if st.session_state.get("preferences", "").strip():

    def preference_relevance(product, preferences):
    Calculate how relevant a product is based on user preferences.
    Returns a score from 0 to 100.
    """

    if not preferences:
        return 0

    # Convert product information into searchable text
    product_text = " ".join([
        str(product.get("title", "")),
        str(product.get("brand", "")),
        str(product.get("description", "")),
        str(product.get("category", "")),
    ]).lower()

    score = 0

    # Handle preferences as a list
    if isinstance(preferences, list):
        for preference in preferences:
            preference = str(preference).strip().lower()

            if preference and preference in product_text:
                score += 20

    # Handle preferences as a dictionary
    elif isinstance(preferences, dict):
        for key, value in preferences.items():
            if value:
                search_text = str(value).lower()

                if search_text in product_text:
                    score += 20

    return min(score, 100)
    
    relevance = preference_relevance(
        product,
        st.session_state.preferences
    )

    matches = product.get(
        "matched_preferences",
        []
    )

    st.markdown(
        f"""
        <div style="margin-top:8px;">
            <b>🎯 Preference Match:</b>
            {relevance:.0f}%
        </div>
        """,
        unsafe_allow_html=True
    )

    if matches:

        st.caption(
            "Matched: "
            + ", ".join(matches[:5])
        )
        st.write(
            f"⭐ {rating}  |  "
            f"💬 {int(reviews):,} reviews"
        )

        st.write(
            f"🏪 {product.get('source', 'Shopping Website')}"
        )

        # ----------------------------------------------------
        # BUTTONS
        # ----------------------------------------------------

        b1, b2, b3 = st.columns(3)

        # UNIQUE KEYS
        compare_key = (
            f"compare_{card_key}_{product['id']}"
        )

        save_key = (
            f"save_{card_key}_{product['id']}"
        )

        visit_key = (
            f"visit_{card_key}_{product['id']}"
        )

        with b1:

            if show_compare:

                checked = (
                    product["id"]
                    in st.session_state.selected_ids
                )

                new_checked = st.checkbox(
                    "Compare",
                    value=checked,
                    key=compare_key
                )

                if new_checked:

                    if product["id"] not in st.session_state.selected_ids:

                        st.session_state.selected_ids.append(
                            product["id"]
                        )

                else:

                    if product["id"] in st.session_state.selected_ids:

                        st.session_state.selected_ids.remove(
                            product["id"]
                        )

        with b2:

            already_saved = any(
                x["id"] == product["id"]
                for x in st.session_state.saved_products
            )

            if st.button(
                "❤️ Saved" if already_saved else "♡ Save",
                key=save_key
            ):

                if already_saved:

                    st.session_state.saved_products = [
                        x for x in st.session_state.saved_products
                        if x["id"] != product["id"]
                    ]

                else:

                    st.session_state.saved_products.append(
                        product
                    )

                st.rerun()

        with b3:

            if product.get("link"):

               st.link_button(
    "🛒 Visit Website",
    product["link"]
)

    st.markdown(
        "</div>",
        unsafe_allow_html=True
    )


# ============================================================
# PAGE HEADER
# ============================================================

def page_header(title, subtitle=""):

    st.markdown(
        f'<div class="main-title">{title}</div>',
        unsafe_allow_html=True
    )

    if subtitle:

        st.markdown(
            f'<div class="subtitle">{subtitle}</div>',
            unsafe_allow_html=True
        )


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("🛍️ SmartShop AI")

page = st.sidebar.radio(

    "Navigation",

    [
        "🏠 Home",
        "🔎 Product Research",
        "⚖️ Compare Products",
        "🤖 AI Shopping Advisor",
        "💰 Smart Combination",
        "❤️ Saved Products",
        "⚙️ Settings"
    ]
)


# ============================================================
# HOME
# ============================================================

if page == "🏠 Home":

    page_header(
        "🛍️ SmartShop AI",
        "AI-powered shopping comparison and product research"
    )

    st.info(
        """
        Search products from shopping websites,
        filter them by price and brand,
        compare them, and find the best combination.
        """
    )

    c1, c2, c3 = st.columns(3)

    with c1:

        st.metric(
            "Products",
            len(st.session_state.products)
        )

    with c2:

        st.metric(
            "Saved",
            len(st.session_state.saved_products)
        )

    with c3:

        st.metric(
            "Compared",
            len(st.session_state.selected_ids)
        )

    st.markdown("### 🚀 Features")

    st.markdown(
        """
        - 🔎 Search products from shopping websites
        - 💰 Filter by price range
        - 🏷️ Optional brand filtering
        - 📦 Limit products per category
        - ⚖️ Compare multiple products
        - 🤖 AI shopping recommendations
        - 🧮 Smart combination optimization
        - 🛒 Direct product website links
        """
    )


# ============================================================
# PRODUCT RESEARCH
# ============================================================

elif page == "🔎 Product Research":

    page_header(
        "🔎 Product Research",
        "Find products within your selected price range and optional brands"
    )

    # --------------------------------------------------------
    # PRICE RANGE
    # --------------------------------------------------------

    st.subheader("💰 Price Range")

    c1, c2 = st.columns(2)

    with c1:

        min_price = st.number_input(
            "Minimum Price (₹)",
            min_value=0,
            value=5000,
            step=500,
            key="research_min_price"
        )

    with c2:

        max_price = st.number_input(
            "Maximum Price (₹)",
            min_value=0,
            value=100000,
            step=500,
            key="research_max_price"
        )

    if min_price > max_price:

        st.error(
            "Minimum price cannot be greater than maximum price."
        )

        st.stop()

    # --------------------------------------------------------
    # CATEGORY
    # --------------------------------------------------------

    st.subheader("🛍️ Product Categories")

    categories_text = st.text_input(
        "Enter categories separated by commas",
        placeholder="Laptop, Smartphone, Headphones",
        key="categories_input"
    )

    categories = [
        x.strip()
        for x in categories_text.split(",")
        if x.strip()
    ]

    # --------------------------------------------------------
    # BRAND OPTIONS
    # --------------------------------------------------------

    st.subheader("🏷️ Brand Filter")

    st.caption(
        "Optional: leave empty to show products from all brands."
    )

    # General brand list
    brand_options = [
        "HP",
        "Lenovo",
        "Acer",
        "ASUS",
        "Dell",
        "Apple",
        "MSI",
        "Samsung",
        "LG",
        "Sony",
        "OnePlus",
        "Xiaomi",
        "Realme",
        "Oppo",
        "Vivo",
        "Motorola",
        "Google",
        "Nothing",
        "Boat",
        "JBL",
        "Canon",
        "Nikon",
        "Logitech"
    ]

    selected_brands = st.multiselect(
        "Select brand(s) — optional",
        brand_options,
        default=[],
        key="brand_filter",
        placeholder="All brands"
    )

    # --------------------------------------------------------
    # BRAND INFORMATION
    # --------------------------------------------------------

    if selected_brands:

        st.success(
            "Only these brands will be shown: "
            + ", ".join(selected_brands)
        )

    else:

        st.info(
            "No brand selected → products from all brands "
            "can be shown."
        )

    # --------------------------------------------------------
    # PREFERENCES
    # --------------------------------------------------------

    preferences = st.text_input(
        "Additional preferences",
        placeholder="Gaming, lightweight, long battery, 16GB RAM...",
        key="preferences_input"
    )

    # --------------------------------------------------------
    # PRODUCTS PER CATEGORY
    # --------------------------------------------------------

    products_per_category = st.number_input(
        "Products per category",
        min_value=1,
        max_value=20,
        value=4,
        step=1,
        key="products_per_category_input"
    )

    st.caption(
        f"Maximum {products_per_category} products will be displayed for each category."
    )

    # --------------------------------------------------------
    # SEARCH BUTTON
    # --------------------------------------------------------

    if st.button(
        "🔎 Search Shopping Websites",
        type="primary",
        use_container_width=True
    ):

        if not categories:

            st.warning(
                "Please enter at least one product category."
            )

            st.stop()

        # Clear previous products
        st.session_state.products = []

        st.session_state.selected_ids = []

        all_products = []

        progress = st.progress(0)

        for i, category in enumerate(categories):

            # ------------------------------------------------
            # Request more results from API
            # ------------------------------------------------

            # We request more than needed because some
            # products will be removed by price/brand filters.

            requested_results = max(
                products_per_category * 4,
                20
            )

            results = search_shopping(
                query=category,
                min_price=min_price,
                max_price=max_price,
                brands=selected_brands,
                max_results=requested_results
            )

            # ------------------------------------------------
            # Store category
            # ------------------------------------------------

            for p in results:

                p["category"] = get_category_from_query(
                    category
                )

            all_products.extend(results)

            progress.progress(
                (i + 1) / len(categories)
            )

        # ----------------------------------------------------
        # STRICT FILTER
        # ----------------------------------------------------

        final_products = filter_products(
            all_products,
            min_price,
            max_price,
            selected_brands,
            products_per_category
        )

        # ----------------------------------------------------
        # SAVE SEARCH RESULTS
        # ----------------------------------------------------

        st.session_state.products = final_products

        st.session_state.min_price = min_price

        st.session_state.max_price = max_price

        st.session_state.preferences = preferences

        st.session_state.categories = categories

        st.session_state.search_history.append(
            {
                "categories": categories,
                "min_price": min_price,
                "max_price": max_price,
                "brands": selected_brands
            }
        )

        if final_products:

            st.success(
                f"Found {len(final_products)} products "
                f"within ₹{min_price:,.0f} - ₹{max_price:,.0f}"
            )

        else:

            st.warning(
                "No products matched your selected "
                "price range and brand filter."
            )

    # --------------------------------------------------------
    # DISPLAY PRODUCTS
    # --------------------------------------------------------

    if st.session_state.products:

        st.divider()

        st.subheader(
            "🛒 Shopping Results"
        )

        # IMPORTANT:
        # Re-filter AGAIN before displaying.
        # This guarantees old products cannot appear
        # outside the currently selected range.

        display_products = filter_products(
            st.session_state.products,
            st.session_state.min_price,
            st.session_state.max_price,
            selected_brands,
            products_per_category
        )

        # ----------------------------------------------------
        # FINAL SAFETY FILTER
        # ----------------------------------------------------

        display_products = [

            p for p in display_products

            if p.get("price") is not None

            and p["price"] >= st.session_state.min_price

            and p["price"] <= st.session_state.max_price
        ]

        # ----------------------------------------------------
        # BRAND FINAL SAFETY FILTER
        # ----------------------------------------------------

        if selected_brands:

            normalized_selected = [
                normalize_brand(x)
                for x in selected_brands
            ]

            strict_brand_products = []

            for p in display_products:

                title = p.get(
                    "title",
                    ""
                ).lower()

                brand = normalize_brand(
                    p.get("brand", "")
                )

                matched = False

                for selected in normalized_selected:

                    if brand == selected:

                        matched = True
                        break

                    if selected in title:

                        matched = True
                        break

                if matched:

                    strict_brand_products.append(p)

            display_products = strict_brand_products

        # ----------------------------------------------------
        # DISPLAY GROUPED BY CATEGORY
        # ----------------------------------------------------

        grouped = {}

        for p in display_products:

            category = p.get(
                "category",
                "Other"
            )

            if category not in grouped:

                grouped[category] = []

            grouped[category].append(p)

        for category, items in grouped.items():

            st.markdown(
                f"### 📦 {category} "
                f"({len(items)} products)"
            )

            # FINAL HARD LIMIT
            items = items[
                :products_per_category
            ]

            for index, product in enumerate(items):

                render_product_card(
                    product,
                    f"research_{category}_{index}"
                )


# ============================================================
# COMPARE PRODUCTS
# ============================================================

elif page == "⚖️ Compare Products":

    page_header(
        "⚖️ Compare Products",
        "Compare the products you selected"
    )

    selected = []

    for product_id in st.session_state.selected_ids:

        p = get_product_by_id(
            product_id
        )

        if p:

            selected.append(p)

    if not selected:

        st.info(
            "Go to Product Research and select "
            "products using the Compare checkbox."
        )

    else:

        st.subheader(
            f"Selected Products: {len(selected)}"
        )

        for i, p in enumerate(selected):

            render_product_card(
                p,
                f"compare_page_{i}",
                show_compare=False
            )

        st.divider()

        # ----------------------------------------------------
        # COMPARISON TABLE
        # ----------------------------------------------------

        data = []

        for p in selected:

            data.append(
                {
                    "Product": p["title"],
                    "Brand": p.get("brand", "Unknown"),
                    "Price": money(p["price"]),
                    "Rating": p.get("rating", 0),
                    "Reviews": int(
                        safe_float(
                            p.get("reviews"),
                            0
                        )
                    ),
                    "Website": p.get(
                        "source",
                        "Shopping Website"
                    )
                }
            )

        st.dataframe(
            data,
            use_container_width=True
        )


# ============================================================
# AI SHOPPING ADVISOR
# ============================================================

elif page == "🤖 AI Shopping Advisor":

    page_header(
        "🤖 AI Shopping Advisor",
        "Get an AI-based recommendation from your selected products"
    )

    selected = []

    for product_id in st.session_state.selected_ids:

        p = get_product_by_id(
            product_id
        )

        if p:

            selected.append(p)

    if not selected:

        st.warning(
            "Select products from Product Research first."
        )

    else:

        st.write(
            f"Analyzing {len(selected)} selected products..."
        )

        product_data = []

        for p in selected:

            product_data.append(
                {
                    "title": p["title"],
                    "brand": p.get("brand"),
                    "price": p.get("price"),
                    "rating": p.get("rating"),
                    "reviews": p.get("reviews"),
                    "category": p.get("category")
                }
            )

        prompt = f"""
Compare these products:

{json.dumps(product_data, indent=2)}

User preferences:
{st.session_state.preferences}

Price range:
₹{st.session_state.min_price:,.0f}
to
₹{st.session_state.max_price:,.0f}

Give:

1. Best overall
2. Best value
3. Best premium choice
4. Best budget choice
5. Short explanation

Do not invent specifications.
"""

        if st.button(
            "🤖 Analyze Products",
            type="primary"
        ):

            answer = run_ai(
                prompt
            )

            if answer:

                st.markdown(
                    answer
                )

            else:

                st.warning(
                    "Groq API key is not configured."
                )


# ============================================================
# SMART COMBINATION
# ============================================================

elif page == "💰 Smart Combination":

    page_header(
        "🧮 Smart Combination",
        "Find a combination of products inside your selected price range"
    )

    if not st.session_state.products:

        st.info(
            "Search for products first."
        )

    else:

        c1, c2 = st.columns(2)

        with c1:

            min_combo = st.number_input(
                "Minimum total price (₹)",
                min_value=0,
                value=int(
                    st.session_state.min_price
                ),
                step=500
            )

        with c2:

            max_combo = st.number_input(
                "Maximum total price (₹)",
                min_value=0,
                value=int(
                    st.session_state.max_price
                ),
                step=500
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
            "🧮 Find Best Combination",
            type="primary"
        ):

            result = optimize_combination(
                st.session_state.products,
                min_combo,
                max_combo,
                strategy
            )

            if result:

                st.success(
                    f"Combination total: "
                    f"{money(result['total'])}"
                )

                for i, p in enumerate(
                    result["products"]
                ):

                    render_product_card(
                        p,
                        f"combo_{i}",
                        show_compare=False
                    )

            else:

                st.warning(
                    "No valid combination was found "
                    "inside the selected price range."
                )


# ============================================================
# SAVED PRODUCTS
# ============================================================

elif page == "❤️ Saved Products":

    page_header(
        "❤️ Saved Products",
        "Your saved shopping products"
    )

    if not st.session_state.saved_products:

        st.info(
            "No saved products yet."
        )

    else:

        for i, p in enumerate(
            st.session_state.saved_products
        ):

            render_product_card(
                p,
                f"saved_{i}",
                show_compare=False
            )


# ============================================================
# SETTINGS
# ============================================================

elif page == "⚙️ Settings":

    page_header(
        "⚙️ Settings",
        "Configure SmartShop AI"
    )

    st.session_state.settings[
        "max_results"
    ] = st.number_input(
        "API search results",
        min_value=5,
        max_value=50,
        value=int(
            st.session_state.settings[
                "max_results"
            ]
        )
    )

    st.session_state.settings[
        "ai_temperature"
    ] = st.slider(
        "AI Temperature",
        min_value=0.0,
        max_value=1.0,
        value=float(
            st.session_state.settings[
                "ai_temperature"
            ]
        ),
        step=0.1
    )

    st.divider()

    st.subheader(
        "🗑️ Clear Data"
    )

    if st.button(
        "Clear Search Results"
    ):

        st.session_state.products = []

        st.session_state.selected_ids = []

        st.success(
            "Search results cleared."
        )

        st.rerun()

    if st.button(
        "Clear Saved Products"
    ):

        st.session_state.saved_products = []

        st.success(
            "Saved products cleared."
        )

        st.rerun()
