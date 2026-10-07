
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

groq_api_key = os.environ.get("GROQ_API_KEY")
serpapi_api_key = os.environ.get("SERPAPI_API_KEY")

if not groq_api_key and "GROQ_API_KEY" in st.secrets:
    groq_api_key = st.secrets["GROQ_API_KEY"]

if not serpapi_api_key and "SERPAPI_API_KEY" in st.secrets:
    serpapi_api_key = st.secrets["SERPAPI_API_KEY"]

groq_client = Groq(api_key=groq_api_key) if groq_api_key else None


# =========================================================
# SESSION STATE
# =========================================================
