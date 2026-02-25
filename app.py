import os
import streamlit as st
from openai import OpenAI

# -------- SHORTER PROMPT --------
PROMPT_V2 = """You are a senior industrial maintenance troubleshooter.

Give SHORT, practical answers.

Use this format:
A) Problem restatement (1 sentence)
B) 3–5 Diagnostic questions
C) Top 3 likely causes
D) Step-by-step troubleshooting plan (max 6 steps)
E) Safety notes (short)
"""

# -------- PAGE UI --------
st.set_page_config(page_title="Maintenance Troubleshooter", page_icon="🔧")
st.title("🔧 Maintenance Troubleshooter")
st.caption("Type a problem. Get a fast troubleshooting plan.")
# Session state for textbox
if "problem_text" not in st.session_state:
    st.session_state.problem_text = ""
problem = st.text_area(
    "Describe the problem",
    key="problem_text",
    height=140,
    placeholder="Example: Motor trips overload after 15 minutes on a pump. 480V 3-phase."
)

st.divider()

# -------- API KEY --------
api_key = os.getenv("OPENAI_API_KEY", "")
col1, col2 = st.columns(2)

with col1:
    troubleshoot_clicked = st.button(
        "Troubleshoot",
        type="primary",
        disabled=(not problem.strip())
    )

with col2:
    reset_clicked = st.button("Reset")

# --- Reset behavior ---
if reset_clicked:
    st.session_state.problem_text = ""
    st.rerun()

# --- Run troubleshooting only when clicked ---
if troubleshoot_clicked:
    if not api_key:
        st.error("Missing OPENAI_API_KEY in Streamlit Secrets.")
        st.stop()

    client = OpenAI(api_key=api_key)

    with st.spinner("Thinking like a senior tech..."):
        resp = client.responses.create(
            model="gpt-5-mini",
            input=[
                {"role": "system", "content": PROMPT_V2},
                {"role": "user", "content": problem.strip()},
            ],
        )

    st.subheader("Result")
    st.write(resp.output_text)
