import os
import streamlit as st
from openai import OpenAI

# -------- SHORTER PROMPT --------
PROMPT_V2 = """You are a senior industrial maintenance technician with 30+ years of hands-on experience in electrical, mechanical, hydraulic, pneumatic, PLC, and VFD systems.

Your job is to give REALISTIC shop-floor troubleshooting guidance.

Always think like an experienced maintenance tech:
• Start with the fastest isolation checks
• Prioritize the MOST LIKELY cause based on symptoms
• Separate electrical vs mechanical vs process causes
• Avoid vague advice like "check everything"
• Give practical tests a technician can actually perform

Give SHORT, practical answers.

Use this format:

A) Problem restatement (1 sentence)

B) Diagnostic questions (3–5)

C) Most likely cause based on the symptom pattern (1–2 sentences)

D) Fastest isolation test (the single quickest test to narrow the problem)

E) Top 3 likely causes

F) Step-by-step troubleshooting plan (max 6 steps)

G) Stop conditions (when to escalate or stop testing)

H) Safety notes (short)
"""
# -------- PAGE UI --------
st.set_page_config(page_title="Maintenance Troubleshooter", page_icon="🔧")
st.title("🔧 Maintenance Troubleshooter")
st.caption("Type a problem. Get a fast troubleshooting plan.")

# --- Session state (must be BEFORE widgets that use these keys) ---
if "form_id" not in st.session_state:
    st.session_state["form_id"] = 0

if "last_result" not in st.session_state:
    st.session_state["last_result"] = ""

# --- Textbox ---
problem = st.text_area(
    "Describe the problem",
    key=f"problem_text_{st.session_state['form_id']}",
    height=140,
    placeholder="Example: Motor trips overload after 15 minutes on a pump. 480V 3-phase."
)

st.divider()
