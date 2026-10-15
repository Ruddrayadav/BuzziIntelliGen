"""
app/pages/03_ask.py
-------------------
Ask AI Business Analyst UI page (Phase 5 Enhanced).

UI RULE:
  This file ONLY manages the chat state and renders the UI.
  All routing, LLM calls, and SQL queries happen in ai_service.py.
"""

import streamlit as st
import pandas as pd
from services.ai_service import ask_question, Answer

# Get the logged-in user's tenant ID and business name
TENANT_ID = st.session_state.get("tenant_id", "demo_user")
BUSINESS_NAME = st.session_state.get("business_name", "Your Business")

st.title("🤖 Ask AI Business Analyst")
st.caption(f"Ask questions about **{BUSINESS_NAME}** in plain English. Answers are calculated directly from your real database records.")

# Sidebar helper / Clear Chat
with st.sidebar:
    st.markdown("### 💡 Quick Capabilities")
    st.markdown("- **Top Products:** Best-selling items and menu leaders")
    st.markdown("- **Revenue & Profit:** Total sales, expenses, and net margin")
    st.markdown("- **Period Comparison:** MoM growth, product shifts, and cost changes")
    st.markdown("- **Anomaly Radar:** Statistical spikes, sudden drops, and outliers")
    st.markdown("- **Profit Diagnostics:** Root-cause explanation for margin drops")
    
    if st.button("🧹 Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Initialize Chat History
# ─────────────────────────────────────────────────────────────────────────────
if "messages" not in st.session_state or not st.session_state.messages:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": f"Hello! I am your AI Business Analyst for **{BUSINESS_NAME}**. How can I help you today?\n\nYou can ask about your top products, revenue, month-over-month comparisons, anomaly detection, or root-cause profit diagnostics."
        }
    ]

# ─────────────────────────────────────────────────────────────────────────────
# Suggestion Chips
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("**Suggested Quick Prompts:**")
suggested_prompts = [
    "Compare this month with last month",
    "Are there any anomalies or sudden spikes?",
    "Why did profit change between periods?",
    "What are my top 5 products?",
    "What is my net profit?"
]

cols = st.columns(len(suggested_prompts))
clicked_prompt = None
for idx, p_text in enumerate(suggested_prompts):
    if cols[idx].button(p_text, key=f"chip_{idx}", use_container_width=True):
        clicked_prompt = p_text

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Render Chat History
# ─────────────────────────────────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        
        # If the assistant replied with data, render the table below the text
        if "data" in msg and msg["data"] is not None and not msg["data"].empty:
            with st.expander("📊 View Source Data & Verification"):
                st.dataframe(msg["data"], use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# Chat Input & Processing
# ─────────────────────────────────────────────────────────────────────────────
active_input = st.chat_input("Ask a question about your business...")
prompt_to_process = clicked_prompt or active_input

if prompt_to_process:
    # 1. Display user message immediately
    st.session_state.messages.append({"role": "user", "content": prompt_to_process})
    with st.chat_message("user"):
        st.markdown(prompt_to_process)

    # 2. Get answer from AI Service
    with st.chat_message("assistant"):
        with st.spinner("Analyzing your data and computing analytics..."):
            answer: Answer = ask_question(prompt_to_process, TENANT_ID)
            
            # Display the text response
            st.markdown(answer.text)
            
            # Display the data table if present
            if answer.data is not None and not answer.data.empty:
                with st.expander("📊 View Source Data & Verification"):
                    st.dataframe(answer.data, use_container_width=True)
            
            # Save to history so it persists on next render
            st.session_state.messages.append({
                "role": "assistant", 
                "content": answer.text, 
                "data": answer.data
            })
