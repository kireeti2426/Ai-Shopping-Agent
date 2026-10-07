import streamlit as st
import os
import json
import requests
from groq import Groq


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="AI Shopping Research Agent",
    page_icon="🛍️",
    layout="wide"
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
    """
    <style>

    .main-title {
        font-size: 42px;
        font-weight: 800;
        margin-bottom: 5px;
    }

    .subtitle {
        font-size: 18px;
        color: #666;
        margin-bottom: 25px;
    }

    .product-card {
        padding: 20px;
        border-radius: 15px;
        border: 1px solid #ddd;
        margin-bottom: 20px;
        background: white;
    }

    .product-title {
        font-size: 22px;
        font-weight: 700;
    }

    .brand-badge {
        background: #eee;
        padding: 5px 10px;
        border-radius: 10px;
        font-size: 13px;
    }

    .score {
        font-size: 18px;
        font-weight: bold;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# TITLE
# ============================================================

st.markdown(
    '<div class="main-title">🛍️ AI Shopping Research Agent</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">'
    'Find, compare and evaluate products using AI.'
    '</div>',
    unsafe_allow_html=True
)


# ============================================================
# GROQ API
# ============================================================

api_key = os.environ.get("GROQ_API_KEY")

if not api_key:
    try:
        api_key = st.secrets["GROQ_API_KEY"]
    except Exception:
        api_key = None


if not api_key:

    st.warning(
        "⚠️ GROQ_API_KEY is not configured. "
        "Product research will still work, but AI analysis will be unavailable."
    )

    client = None

else:

    client = Groq(api_key=api_key)


# ============================================================
# SESSION STATE
# ============================================================

if "preferences" not in st.session_state:
    st.session_state.preferences = []

if "products" not in st.session_state:
    st.session_state.products = []


# ============================================================
# PRODUCT DATABASE
# ============================================================

PRODUCTS = [

    {
        "title": "Samsung Galaxy S25",
        "brand": "Samsung",
        "category": "Smartphone",
        "price": 74999,
        "rating": 4.6,
        "description": "Premium Android smartphone with powerful processor, excellent camera and AMOLED display.",
        "features": [
            "AMOLED display",
            "5G",
            "Excellent camera",
            "Fast processor"
        ]
    },

    {
        "title": "Apple iPhone 16",
        "brand": "Apple",
        "category": "Smartphone",
        "price": 69999,
        "rating": 4.7,
        "description": "Powerful smartphone with excellent camera, strong performance and long software support.",
        "features": [
            "iOS",
            "Excellent camera",
            "5G",
            "Long software support"
        ]
    },

    {
        "title": "OnePlus 13",
        "brand": "OnePlus",
        "category": "Smartphone",
        "price": 64999,
        "rating": 4.5,
        "description": "High performance Android smartphone with fast charging, powerful processor and premium display.",
        "features": [
            "Fast charging",
            "High performance",
            "AMOLED display",
            "5G"
        ]
    },

    {
        "title": "Google Pixel 9",
        "brand": "Google",
        "category": "Smartphone",
        "price": 79999,
        "rating": 4.6,
        "description": "AI-powered smartphone with excellent computational photography and clean Android experience.",
        "features": [
            "AI features",
            "Excellent camera",
            "Clean Android",
            "5G"
        ]
    },

    {
        "title": "Sony WH-1000XM5",
        "brand": "Sony",
        "category": "Headphones",
        "price": 29990,
        "rating": 4.7,
        "description": "Premium wireless headphones with industry-leading noise cancellation and excellent sound.",
        "features": [
            "Noise cancellation",
            "Wireless",
            "Premium audio",
            "Long battery"
        ]
    },

    {
        "title": "Apple AirPods Pro",
        "brand": "Apple",
        "category": "Headphones",
        "price": 24900,
        "rating": 4.6,
        "description": "Premium wireless earbuds with active noise cancellation and excellent Apple ecosystem integration.",
        "features": [
            "Noise cancellation",
            "Wireless",
            "Spatial audio",
            "Apple ecosystem"
        ]
    },

    {
        "title": "Dell Inspiron 14",
        "brand": "Dell",
        "category": "Laptop",
        "price": 59999,
        "rating": 4.4,
        "description": "Reliable laptop suitable for students, office work, programming and everyday productivity.",
        "features": [
            "Intel processor",
            "SSD",
            "14 inch display",
            "Student friendly"
        ]
    },

    {
        "title": "HP Pavilion 15",
        "brand": "HP",
        "category": "Laptop",
        "price": 64999,
        "rating": 4.5,
        "description": "Versatile laptop for students and professionals with good performance and modern design.",
        "features": [
            "Intel processor",
            "SSD",
            "15 inch display",
            "Good performance"
        ]
    }

]


# ============================================================
# PREFERENCE RELEVANCE FUNCTION
# ============================================================

def preference_relevance(product, preferences):

    """
    Calculate how relevant a product is based on
    user preferences.

    Returns a score from 0 to 100.
    """

    if not preferences:
        return 0

    product_text = " ".join(
        [
            str(product.get("title", "")),
            str(product.get("brand", "")),
            str(product.get("description", "")),
            str(product.get("category", "")),
            " ".join(product.get("features", []))
        ]
    ).lower()

    score = 0

    if isinstance(preferences, list):

        for preference in preferences:

            preference = str(preference).strip().lower()

            if preference and preference in product_text:
                score += 20

    elif isinstance(preferences, dict):

        for key, value in preferences.items():

            if value:

                search_text = str(value).lower()

                if search_text in product_text:
                    score += 20

    return min(score, 100)


# ============================================================
# PRODUCT SEARCH
# ============================================================

def search_products(query, max_price=None):

    query = query.lower().strip()

    results = []

    for product in PRODUCTS:

        searchable_text = " ".join(
            [
                product["title"],
                product["brand"],
                product["category"],
                product["description"],
                " ".join(product["features"])
            ]
        ).lower()

        if query in searchable_text:

            if max_price is None or product["price"] <= max_price:
                results.append(product)

    return results


# ============================================================
# PRODUCT SCORING
# ============================================================

def calculate_product_score(product, preferences):

    relevance = preference_relevance(
        product,
        preferences
    )

    rating_score = (product["rating"] / 5) * 100

    final_score = (
        relevance * 0.6 +
        rating_score * 0.4
    )

    return round(final_score, 2)


# ============================================================
# AI ANALYSIS
# ============================================================

def generate_ai_analysis(products, user_request):

    if not client:
        return (
            "AI analysis is unavailable because "
            "GROQ_API_KEY is not configured."
        )

    product_data = json.dumps(
        products,
        indent=2
    )

    prompt = f"""
You are an AI shopping research assistant.

User request:
{user_request}

Products:
{product_data}

Analyze these products and provide:

1. Best overall choice
2. Best value for money
3. Best premium option
4. Main advantages and disadvantages
5. Final recommendation

Keep the answer clear and practical.
Do not invent specifications that are not present
in the product data.
"""

    try:

        response = client.chat.completions.create(

            model="llama-3.3-70b-versatile",

            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful shopping research assistant."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],

            temperature=0.3
        )

        return response.choices[0].message.content

    except Exception as e:

        return f"AI analysis failed: {str(e)}"


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("🎯 Shopping Preferences")

    category = st.selectbox(
        "Category",
        [
            "Smartphone",
            "Laptop",
            "Headphones"
        ]
    )

    budget = st.number_input(
        "Maximum Budget (₹)",
        min_value=0,
        value=70000,
        step=5000
    )

    preference_text = st.text_input(
        "What features do you prefer?",
        placeholder="camera, battery, performance..."
    )

    if st.button("Save Preferences"):

        preferences = []

        if preference_text:

            preferences = [
                item.strip()
                for item in preference_text.split(",")
                if item.strip()
            ]

        st.session_state.preferences = preferences

        st.success("Preferences saved!")


# ============================================================
# MAIN SEARCH AREA
# ============================================================

st.header("🔎 Find Products")

query = st.text_input(
    "What are you looking for?",
    placeholder="Example: smartphone"
)


if st.button("🔍 Search Products"):

    if not query:

        st.warning("Please enter a product to search.")

    else:

        products = search_products(
            query,
            budget
        )

        # Filter by category
        products = [
            p for p in products
            if p["category"].lower() == category.lower()
        ]

        # Calculate scores
        for product in products:

            product["relevance"] = preference_relevance(
                product,
                st.session_state.preferences
            )

            product["score"] = calculate_product_score(
                product,
                st.session_state.preferences
            )

        products.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        st.session_state.products = products


# ============================================================
# DISPLAY PRODUCTS
# ============================================================

if st.session_state.products:

    st.header("🛍️ Recommended Products")

    for product in st.session_state.products:

        relevance = preference_relevance(
            product,
            st.session_state.preferences
        )

        col1, col2 = st.columns([1, 3])

        with col1:

            st.markdown(
                f"""
                <div style="
                    font-size:70px;
                    text-align:center;
                    padding-top:20px;
                ">
                    🛍️
                </div>
                """,
                unsafe_allow_html=True
            )

        with col2:

            st.markdown(
                f"""
                <div class="product-card">

                    <div class="product-title">
                        {product.get("title", "Product")}
                    </div>

                    <br>

                    <span class="brand-badge">
                        {product.get("brand", "")}
                    </span>

                    <br><br>

                    <b>Category:</b>
                    {product.get("category", "")}

                    <br><br>

                    <b>Price:</b>
                    ₹{product.get("price", 0):,}

                    <br><br>

                    <b>Rating:</b>
                    ⭐ {product.get("rating", 0)}/5

                    <br><br>

                    <b>🎯 Preference Match:</b>
                    {relevance}%

                    <br><br>

                    <b>Description:</b>
                    {product.get("description", "")}

                </div>
                """,
                unsafe_allow_html=True
            )

            st.write("**Features:**")

            for feature in product.get("features", []):

                st.write(
                    f"• {feature}"
                )


# ============================================================
# AI SHOPPING ANALYSIS
# ============================================================

if st.session_state.products:

    st.divider()

    st.header("🤖 AI Shopping Analysis")

    if st.button("✨ Analyze Products with AI"):

        user_request = (
            f"Find the best {category} "
            f"under ₹{budget}. "
            f"User preferences: "
            f"{', '.join(st.session_state.preferences)}"
        )

        with st.spinner("AI is analyzing the products..."):

            analysis = generate_ai_analysis(
                st.session_state.products,
                user_request
            )

        st.markdown(analysis)


# ============================================================
# COMPARISON TABLE
# ============================================================

if len(st.session_state.products) >= 2:

    st.divider()

    st.header("📊 Product Comparison")

    comparison_data = []

    for product in st.session_state.products:

        comparison_data.append(
            {
                "Product": product["title"],
                "Brand": product["brand"],
                "Price": f"₹{product['price']:,}",
                "Rating": product["rating"],
                "Preference Match": f"{product['relevance']}%",
                "Score": product["score"]
            }
        )

    st.dataframe(
        comparison_data,
        use_container_width=True
    )


# ============================================================
# NO RESULTS
# ============================================================

if query and not st.session_state.products:

    st.info(
        "No products found. "
        "Try another search or increase your budget."
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "🛍️ AI Shopping Research Agent • "
    "Built with Streamlit + Groq + Llama"
)
