"""
main.py
--------
Streamlit application entry point.

Handles startup tasks (DB initialization) and dynamic navigation
based on authentication state (Phase 4).
"""

import streamlit as st

# ── Page configuration (must be the FIRST Streamlit call) ────────────────────
st.set_page_config(
    page_title="BizIntel — Business Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Database initialisation (runs once per server start) ─────────────────────
@st.cache_resource
def _startup() -> bool:
    from db.database import health_check, init_db
    init_db()
    return health_check()

db_ok = _startup()
if not db_ok:
    st.error("⚠️ Cannot connect to the database. Please check your setup.")
    st.stop()

# ── Authentication State ──────────────────────────────────────────────────────
if "tenant_id" not in st.session_state:
    st.session_state["tenant_id"] = None
    st.session_state["business_name"] = None

def logout():
    st.session_state["tenant_id"] = None
    st.session_state["business_name"] = None
    st.rerun()

# ── Dynamic Navigation ───────────────────────────────────────────────────────
if st.session_state["tenant_id"] is None:
    # User is not logged in: only show the Login page
    login_page = st.Page("app/pages/00_login.py", title="Login / Register", icon="🔐", default=True)
    pg = st.navigation([login_page])
else:
    # User is logged in: show the main app pages
    st.sidebar.markdown(f"**🏢 {st.session_state['business_name']}**")
    if st.sidebar.button("Log out"):
        logout()
        
    pages = [
        st.Page("app/pages/01_upload.py", title="Upload Data", icon="📤", default=True),
        st.Page("app/pages/02_dashboard.py", title="Dashboard", icon="📊"),
        st.Page("app/pages/03_ask.py", title="Ask AI", icon="🤖"),
    ]
    pg = st.navigation(pages)

pg.run()
