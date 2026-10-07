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
