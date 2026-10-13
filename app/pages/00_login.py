"""
app/pages/00_login.py
---------------------
Login and Registration UI.
"""

import streamlit as st
from services.auth_service import authenticate_user, register_user

st.title("🔐 Welcome to BizIntel")
st.caption("AI-Powered Business Intelligence & Decision Support System")

st.divider()

# Create tabs for Login and Register
tab_login, tab_register = st.tabs(["Log In", "Create Account"])

with tab_login:
    st.subheader("Log in to your account")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log In", type="primary")
        
        if submitted:
            if not username or not password:
                st.error("Please enter both username and password.")
            else:
                user = authenticate_user(username, password)
                if user:
                    st.session_state["tenant_id"] = user.tenant_id
                    st.session_state["business_name"] = user.business_name
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Invalid username or password.")

with tab_register:
    st.subheader("Create a new account")
    with st.form("register_form"):
        new_biz_name = st.text_input("Business Name")
        new_username = st.text_input("Username")
        new_password = st.text_input("Password", type="password")
        new_submitted = st.form_submit_button("Register", type="primary")
        
        if new_submitted:
            if not new_username or not new_password or not new_biz_name:
                st.error("All fields are required.")
            else:
                success, result = register_user(new_username, new_password, new_biz_name)
                if success:
                    st.success("Account created! You can now log in.")
                else:
                    st.error(result)

st.divider()
st.info(
    "**Demo Mode:** Since this is a local project, you can create any username and password "
    "to act as a unique tenant. Data uploaded by one user will not be visible to others."
)
