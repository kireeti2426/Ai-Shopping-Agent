import streamlit as st
import os
import time
import json
import requests
from groq import Groq


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="AI Smart Shopping Agent",
    page_icon="🛍️",
    layout="wide"
)

st.title("🛍️ AI Smart Shopping Comparison & Optimization Agent")

st.write(
    "Multi-Agent Shopping Intelligence: Research products from shopping sources, "
    "compare prices and features, and select the best product combination "
    "within your budget."
)


# =========================================================
# API SETUP
# =========================================================

groq_api_key = os.environ.get("GROQ_API_KEY")
serpapi_api_key = os.environ.get("SERPAPI_API_KEY")


if not groq_api_key and "GROQ_API_KEY" in st.secrets:
    groq_api_key = st.secrets["GROQ_API_KEY"]

if not serpapi_api_key and "SERPAPI_API_KEY" in st.secrets:
    serpapi_api_key = st.secrets["SERPAPI_API_KEY"]


if not groq_api_key:
    st.error(
        "Groq API Key missing. Please configure GROQ_API_KEY "
        "in Streamlit Secrets."
    )
    st.stop()


if not serpapi_api_key:
    st.error(
        "SerpAPI Key missing. Please configure SERPAPI_API_KEY "
        "in Streamlit Secrets."
    )
    st.stop()


client = Groq(api_key=groq_api_key)


# =========================================================
# SHARED AGENT RUNNER
# =========================================================

def run_agent(persona, prompt_input, json_mode=False):

    start_time = time.time()

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": persona
            },
            {
                "role": "user",
                "content": prompt_input
            }
        ],
        temperature=0.1,
        response_format=(
            {"type": "json_object"}
            if json_mode
            else {"type": "text"}
        )
    )

    latency = round(time.time() - start_time, 2)

    return response.choices[0].message.content, latency


# =========================================================
# SHOPPING SEARCH FUNCTION
# =========================================================

def search_shopping(query, max_results=10):

    url = "https://serpapi.com/search.json"

    params = {
        "engine": "google_shopping",
        "q": query,
        "api_key": serpapi_api_key,
        "num": max_results
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        products = []

        for item in data.get("shopping_results", []):

            products.append(
                {
                    "title": item.get("title", "Unknown Product"),
                    "price": item.get("price", "Not available"),
                    "source": item.get("source", "Unknown"),
                    "rating": item.get("rating", "N/A"),
                    "reviews": item.get("reviews", "N/A"),
                    "link": item.get("link", ""),
                    "thumbnail": item.get("thumbnail", ""),
                    "snippet": item.get("snippet", ""),
                    "delivery": item.get("delivery", "")
                }
            )

        return products

    except Exception as e:

        st.error(f"Shopping search failed: {str(e)}")

        return []


# =========================================================
# PRODUCT DATA CLEANING
# =========================================================

def clean_price(price):

    if not price:
        return None

    try:

        price_string = (
            str(price)
            .replace("₹", "")
            .replace("$", "")
            .replace(",", "")
            .strip()
        )

        return float(
            "".join(
                c for c in price_string
                if c.isdigit() or c == "."
            )
        )

    except Exception:

        return None


def prepare_products(products):

    cleaned = []

    for index, product in enumerate(products):

        cleaned.append(
            {
                "id": index + 1,
                "name": product.get("title"),
                "price": clean_price(product.get("price")),
                "display_price": product.get("price"),
                "source": product.get("source"),
                "rating": product.get("rating"),
                "reviews": product.get("reviews"),
                "link": product.get("link"),
                "description": product.get("snippet"),
                "delivery": product.get("delivery")
            }
        )

    return cleaned


# =========================================================
# INPUT SECTION
# =========================================================

st.subheader("1. Shopping Requirements")


col1, col2, col3 = st.columns(3)


with col1:

    budget = st.number_input(
        "Total Budget (₹)",
        min_value=500,
        value=20000,
        step=500
    )


with col2:

    selection_mode = st.selectbox(
        "Selection Mode",
        [
            "Automatic Selection",
            "Manual Selection"
        ]
    )


with col3:

    max_products = st.number_input(
        "Products per Category",
        min_value=3,
        max_value=15,
        value=8,
        step=1
    )


categories_text = st.text_input(
    "Products You Want",
    placeholder="Example: headphones, shoes, backpack"
)


preferences = st.text_area(
    "Your Preferences",
    placeholder=(
        "Example: I prefer good quality, high ratings, "
        "comfortable products and value for money. "
        "Brand is less important than quality."
    )
)


priority = st.multiselect(
    "What matters most?",
    [
        "Low Price",
        "High Rating",
        "Quality",
        "Features",
        "Customer Reviews",
        "Brand",
        "Value for Money"
    ],
    default=[
        "Quality",
        "High Rating",
        "Value for Money"
    ]
)


# =========================================================
# MANUAL PRODUCT SELECTION STATE
# =========================================================

if "shopping_products" not in st.session_state:
    st.session_state.shopping_products = []

if "selected_products" not in st.session_state:
    st.session_state.selected_products = []


# =========================================================
# RESEARCH BUTTON
# =========================================================

if st.button(
    "🔎 Research Products",
    type="primary"
):

    if not categories_text.strip():

        st.warning(
            "Please enter at least one product category."
        )

    else:

        categories = [
            x.strip()
            for x in categories_text.split(",")
            if x.strip()
        ]

        all_products = []

        with st.status(
            "Researching shopping websites...",
            expanded=True
        ) as status:

            for category in categories:

                st.write(
                    f"🛒 Searching shopping sources for **{category}**..."
                )

                query = category

                if preferences:
                    query += f" {preferences}"

                products = search_shopping(
                    query,
                    int(max_products)
                )

                for product in products:

                    product["category"] = category

                all_products.extend(products)

            st.session_state.shopping_products = prepare_products(
                all_products
            )

            status.update(
                label=(
                    f"Shopping research completed — "
                    f"{len(all_products)} products found."
                ),
                state="complete",
                expanded=False
            )


# =========================================================
# DISPLAY PRODUCTS
# =========================================================

if st.session_state.shopping_products:

    st.subheader("2. Products Found")

    products = st.session_state.shopping_products

    for product in products:

        with st.container(border=True):

            col1, col2, col3, col4 = st.columns(
                [4, 2, 2, 2]
            )

            with col1:

                st.markdown(
                    f"### {product['name']}"
                )

                st.write(
                    f"**Category:** {product.get('category', 'Unknown')}"
                )

                st.write(
                    f"**Source:** {product['source']}"
                )

            with col2:

                st.metric(
                    "Price",
                    product["display_price"] or "N/A"
                )

            with col3:

                st.metric(
                    "Rating",
                    str(product["rating"])
                )

                st.write(
                    f"Reviews: {product['reviews']}"
                )

            with col4:

                if product["link"]:

                    st.link_button(
                        "View Product",
                        product["link"]
                    )


# =========================================================
# MANUAL SELECTION
# =========================================================

if (
    st.session_state.shopping_products
    and selection_mode == "Manual Selection"
):

    st.subheader("3. Manual Product Selection")

    st.info(
        "Select the products you want the AI to compare. "
        "You can select products from different categories."
    )

    selected_ids = []

    for product in st.session_state.shopping_products:

        label = (
            f"{product['name']} | "
            f"{product['display_price']} | "
            f"{product['source']}"
        )

        selected = st.checkbox(
            label,
            key=f"select_{product['id']}"
        )

        if selected:

            selected_ids.append(
                product["id"]
            )

    st.session_state.selected_products = [
        p for p in st.session_state.shopping_products
        if p["id"] in selected_ids
    ]

    st.write(
        f"Selected products: "
        f"**{len(st.session_state.selected_products)}**"
    )


# =========================================================
# MULTI-AGENT PIPELINE
# =========================================================

if st.session_state.shopping_products:

    st.subheader("4. AI Shopping Analysis")

    if st.button(
        "🚀 Start AI Shopping Analysis",
        type="primary"
    ):

        total_latency = 0

        # -------------------------------------------------
        # Determine products for analysis
        # -------------------------------------------------

        if selection_mode == "Manual Selection":

            analysis_products = (
                st.session_state.selected_products
            )

            if not analysis_products:

                st.warning(
                    "Please manually select at least one product."
                )

                st.stop()

        else:

            analysis_products = (
                st.session_state.shopping_products
            )

        product_data = json.dumps(
            analysis_products,
            indent=2
        )

        # =================================================
        # AGENT 1
        # SHOPPING RESEARCH AGENT
        # =================================================

        with st.status(
            "Orchestrating Shopping Intelligence Team...",
            expanded=True
        ) as status:

            st.write(
                "🛒 **Agent 1 — Shopping Research Agent:** "
                "Analyzing collected product information..."
            )

            research_prompt = """
You are a Shopping Research Agent.

Your task is to analyze product information collected
from shopping search results.

Do not invent information.

Analyze:

1. Price
2. Rating
3. Review count
4. Product source
5. Available descriptions
6. Delivery information
7. Important product differences

Identify:

- Premium options
- Budget options
- High-rated options
- Best-value candidates
- Products with insufficient information

Return valid JSON:

{
    "product_observations": [
        {
            "product_id": 0,
            "strengths": ["string"],
            "weaknesses": ["string"],
            "value_category": "Budget | Balanced | Premium | Unknown"
        }
    ],
    "important_comparison_points": ["string"],
    "data_quality_issues": ["string"]
}
"""

            research_raw, lat = run_agent(
                research_prompt,
                (
                    "PRODUCT DATA:\n"
                    + product_data
                    + "\n\nUSER BUDGET:\n"
                    + str(budget)
                    + "\n\nUSER PREFERENCES:\n"
                    + preferences
                ),
                json_mode=True
            )

            total_latency += lat

            try:

                research = json.loads(
                    research_raw
                )

            except Exception:

                research = {
                    "raw_research": research_raw
                }

            with st.expander(
                f"Shopping Research ({lat}s)"
            ):

                st.json(research)


            # =================================================
            # AGENT 2
            # PRODUCT COMPARISON AGENT
            # =================================================

            st.write(
                "📊 **Agent 2 — Product Comparison Agent:** "
                "Scoring products based on user priorities..."
            )

            comparison_prompt = """
You are a Product Comparison Data Science Agent.

Compare the supplied products using:

- Price
- Rating
- Review count
- Features available in the supplied data
- User preferences
- User priorities
- Value for money

Create a score from 0 to 100.

IMPORTANT:

Do not invent specifications.

If a feature is missing, say "Not available".

Return valid JSON:

{
    "product_scores": [
        {
            "product_id": 0,
            "product_score": 0,
            "price_score": 0,
            "rating_score": 0,
            "review_score": 0,
            "preference_match_score": 0,
            "value_score": 0,
            "reason": "string"
        }
    ],
    "top_products": [0, 0, 0]
}
"""

            comparison_raw, lat = run_agent(
                comparison_prompt,
                (
                    "PRODUCT DATA:\n"
                    + product_data
                    + "\n\nRESEARCH ANALYSIS:\n"
                    + json.dumps(
                        research,
                        indent=2
                    )
                    + "\n\nUSER PRIORITIES:\n"
                    + json.dumps(priority)
                    + "\n\nUSER PREFERENCES:\n"
                    + preferences
                ),
                json_mode=True
            )

            total_latency += lat

            try:

                comparison = json.loads(
                    comparison_raw
                )

            except Exception:

                comparison = {
                    "raw_comparison": comparison_raw
                }

            with st.expander(
                f"Product Comparison ({lat}s)"
            ):

                st.json(comparison)


            # =================================================
            # AGENT 3
            # SELECTION & OPTIMIZATION AGENT
            # =================================================

            st.write(
                "🎯 **Agent 3 — Selection & Optimization Agent:** "
                "Finding the best product combination..."
            )

            optimization_prompt = """
You are a Shopping Optimization Agent.

Your task is to select the best combination of products
within the user's total budget.

Requirements:

1. Consider product scores.
2. Consider user priorities.
3. Consider product categories.
4. Try to select one strong product from each required category.
5. Keep total price within the budget.
6. If the best combination cannot fit the budget,
   explain the trade-off.
7. Provide multiple combinations when possible.

The selection can be:

- Automatic
- Manual

For AUTOMATIC mode:
Choose the best overall combination.

For MANUAL mode:
Analyze only the products supplied by the user.

Return valid JSON:

{
    "best_combination": [
        {
            "product_id": 0,
            "category": "string",
            "reason": "string"
        }
    ],
    "total_cost": 0,
    "remaining_budget": 0,
    "overall_score": 0,
    "alternative_combinations": [
        {
            "name": "Budget Option",
            "product_ids": [0, 0],
            "total_cost": 0,
            "score": 0,
            "reason": "string"
        }
    ],
    "budget_status": "Within Budget | Over Budget",
    "optimization_explanation": "string"
}
"""

            optimization_raw, lat = run_agent(
                optimization_prompt,
                (
                    "PRODUCT DATA:\n"
                    + product_data
                    + "\n\nPRODUCT COMPARISON:\n"
                    + json.dumps(
                        comparison,
                        indent=2
                    )
                    + "\n\nBUDGET:\n"
                    + str(budget)
                    + "\n\nSELECTION MODE:\n"
                    + selection_mode
                    + "\n\nUSER PREFERENCES:\n"
                    + preferences
                ),
                json_mode=True
            )

            total_latency += lat

            try:

                optimization = json.loads(
                    optimization_raw
                )

            except Exception:

                optimization = {
                    "raw_optimization": optimization_raw
                }

            with st.expander(
                f"Optimization Analysis ({lat}s)"
            ):

                st.json(optimization)


            # =================================================
            # AGENT 4
            # FINAL SHOPPING ADVISOR
            # =================================================

            st.write(
                "🧠 **Agent 4 — Final Shopping Advisor:** "
                "Preparing final recommendation..."
            )

            final_prompt = """
You are the Lead AI Shopping Advisor.

Create a clear final shopping recommendation using:

1. Product research
2. Product comparison
3. Optimization results
4. User budget
5. User preferences

Do not invent product specifications.

Clearly explain:

- Selected products
- Why each product was selected
- Total cost
- Remaining budget
- Overall score
- Alternative combinations
- Important trade-offs
- Products that were rejected and why

Return valid JSON:

{
    "shopping_mode": "Manual | Automatic",
    "recommendation": "string",
    "selected_products": [
        {
            "product_id": 0,
            "product_name": "string",
            "category": "string",
            "price": 0,
            "reason": "string"
        }
    ],
    "total_cost": 0,
    "remaining_budget": 0,
    "overall_score": 0,
    "best_alternative": "string",
    "important_tradeoffs": ["string"],
    "final_summary": "string"
}
"""

            final_raw, lat = run_agent(
                final_prompt,
                (
                    "PRODUCT DATA:\n"
                    + product_data
                    + "\n\nCOMPARISON:\n"
                    + json.dumps(
                        comparison,
                        indent=2
                    )
                    + "\n\nOPTIMIZATION:\n"
                    + json.dumps(
                        optimization,
                        indent=2
                    )
                    + "\n\nBUDGET:\n"
                    + str(budget)
                    + "\n\nSELECTION MODE:\n"
                    + selection_mode
                ),
                json_mode=True
            )

            total_latency += lat

            try:

                final_data = json.loads(
                    final_raw
                )

            except Exception:

                final_data = {
                    "final_summary": final_raw
                }

            status.update(
                label=(
                    "Shopping Analysis Complete! "
                    f"Total Latency: "
                    f"{round(total_latency, 2)}s"
                ),
                state="complete",
                expanded=False
            )


        # =================================================
        # FINAL OUTPUT
        # =================================================

        st.subheader(
            "🛍️ Final Shopping Recommendation"
        )

        metric1, metric2, metric3, metric4 = st.columns(4)


        with metric1:

            st.metric(
                "Budget",
                f"₹{budget:,.0f}"
            )


        with metric2:

            st.metric(
                "Total Cost",
                f"₹{final_data.get('total_cost', 0):,.0f}"
            )


        with metric3:

            st.metric(
                "Remaining",
                f"₹{final_data.get('remaining_budget', 0):,.0f}"
            )


        with metric4:

            st.metric(
                "Overall Score",
                f"{final_data.get('overall_score', 0)}/100"
            )


        # =================================================
        # SELECTED PRODUCTS
        # =================================================

        st.markdown("### 🏆 Selected Products")

        selected_products = final_data.get(
            "selected_products",
            []
        )

        for product in selected_products:

            with st.container(border=True):

                col1, col2, col3 = st.columns(
                    [4, 2, 4]
                )

                with col1:

                    st.markdown(
                        f"### {product.get('product_name', 'Product')}"
                    )

                    st.write(
                        f"Category: "
                        f"{product.get('category', 'N/A')}"
                    )

                with col2:

                    st.metric(
                        "Price",
                        f"₹{product.get('price', 0):,.0f}"
                    )

                with col3:

                    st.write(
                        f"**Why selected:** "
                        f"{product.get('reason', 'N/A')}"
                    )


        # =================================================
        # ALTERNATIVES
        # =================================================

        st.markdown(
            "### 🔄 Alternative Shopping Options"
        )

        alternatives = optimization.get(
            "alternative_combinations",
            []
        )

        for option in alternatives:

            with st.container(border=True):

                st.markdown(
                    f"**{option.get('name', 'Alternative')}**"
                )

                st.write(
                    f"Total: ₹"
                    f"{option.get('total_cost', 0):,.0f}"
                )

                st.write(
                    f"Score: "
                    f"{option.get('score', 0)}/100"
                )

                st.write(
                    option.get(
                        "reason",
                        ""
                    )
                )


        # =================================================
        # TRADE-OFFS
        # =================================================

        st.markdown(
            "### ⚖️ Important Trade-offs"
        )

        for item in final_data.get(
            "important_tradeoffs",
            []
        ):

            st.markdown(
                f"• {item}"
            )


        # =================================================
        # FINAL SUMMARY
        # =================================================

        st.info(
            "**AI Shopping Summary:** "
            + final_data.get(
                "final_summary",
                ""
            )
        )


        # =================================================
        # VIEW DATA
        # =================================================

        with st.expander(
            "View Product Comparison Data"
        ):

            st.json(comparison)


        with st.expander(
            "View Optimization Data"
        ):

            st.json(optimization)


        with st.expander(
            "View Final JSON"
        ):

            st.json(final_data)
