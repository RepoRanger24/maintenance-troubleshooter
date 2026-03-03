import os
import streamlit as st
from openai import OpenAI

# -------- SHORTER PROMPT --------
PROMPT_V2 = """You are an industrial maintenance troubleshooting assistant for shop-floor technicians.
Your job is to produce fast, practical isolation steps and likely causes.

Global rules:
- Be concise and specific. No fluff. No long paragraphs.
- Never include a “Diagnostic questions” section.
- Never include safety notes unless explicitly requested by the user.
- If key info is missing, make ONE reasonable assumption and proceed.
- Prefer checks that are quick and realistic (visual, gauge, isolate section, swap known-good, verify signals).

If an alarm code is provided, use ONLY this format:

Alarm: <code> – <short title>
Meaning: <1 line>
Likely causes:
- <cause> (High/Med/Low)
- <cause> (High/Med/Low)
Fast checks:
1) <1 line>
2) <1 line>
Fix: <1 line>

If no alarm code is provided, default to QUICK MODE using ONLY this format:
Meaning: <exactly 1 line>
Likely causes:
- <cause> (High/Med/Low)
- <cause> (High/Med/Low)
- <cause> (High/Med/Low)
Fast checks:
1) <1 line>
2) <1 line>
3) <1 line>
4) <1 line>

Hard limits for QUICK MODE:
- Total output must be 12 lines or fewer.
- Causes must be 1 to 3 bullets (ranked).
- Fast checks must be 2 to 4 steps.
"""
"""
# <-- this closes PROMPT_V2


DEEP_ADDON = """
DEEP MODE (only when selected):
Use this format:

Meaning: <1-2 lines>
Likely causes:
- <cause> (High/Med/Low)
- <cause> (High/Med/Low)
- <cause> (High/Med/Low)
Fast checks:
1) <1 line>
2) <1 line>
3) <1 line>
4) <1 line>
Isolation tree:
IF <condition> -> THEN <action>
IF <condition> -> THEN <action>
Common traps:
- <short trap>
- <short trap>

Rules:
- Keep it structured and concise.
- Do not add diagnostic questions.
- No safety notes unless requested.
"""
# -------- PAGE UI --------
st.set_page_config(page_title="Maintenance Troubleshooter", page_icon="🔧")
st.title("🔧 Maintenance Troubleshooter")
st.caption("Type a problem. Get a fast troubleshooting plan.")
mode = st.radio("Mode", ["Quick", "Deep"], horizontal=True)
# --- Session state (must be BEFORE widgets that use these keys) ---
if "form_id" not in st.session_state:
    st.session_state["form_id"] = 0

if "last_result" not in st.session_state:
    st.session_state["last_result"] = ""
# --- Alarm code (optional) ---
machine_model = st.text_input(
    "Machine / Control Model (optional)",
    key=f"machine_model_{st.session_state['form_id']}",
    placeholder="Example: Fanuc 31i, Haas VF2, Okuma OSP, Siemens 840D..."
)
alarm_code = st.text_input(
    "Alarm code (optional)",
    key=f"alarm_code_{st.session_state['form_id']}",
    placeholder="Example: FANUC 401, SV0407, DTERR, OC, etc."
)
# --- Textbox ---
problem = st.text_area(
    "Describe the problem",
    key=f"problem_text_{st.session_state['form_id']}",
    height=140,
    placeholder="Example: Motor trips overload after 15 minutes on a pump. 480V 3-phase."
)

# <-- add this line right here
has_input = bool(machine_model.strip() or alarm_code.strip() or problem.strip())
st.divider()

# -------- API KEY --------
api_key = os.getenv("OPENAI_API_KEY", "")

col1, col2 = st.columns([1, 1])

with col1:
    troubleshoot_clicked = st.button(
        "Troubleshoot",
        type="primary",
        disabled=(not has_input)
    )

with col2:
    reset_clicked = st.button("Reset")

# --- Reset behavior ---
if reset_clicked:
    st.session_state["last_result"] = ""
    st.session_state["form_id"] += 1
    st.rerun()
  # --- Run troubleshooting only when clicked ---
if troubleshoot_clicked:
    if not api_key:
        st.error("Missing OPENAI_API_KEY in Streamlit Secrets.")
        st.stop()

    client = OpenAI(api_key=api_key)

    # --- Combine ALL user inputs ---
    user_input = ""

    if machine_model.strip():
        user_input += f"Machine/control: {machine_model.strip()}\n"

    if alarm_code.strip():
        user_input += f"Alarm code: {alarm_code.strip()}\n"

    if problem.strip():
        user_input += f"Problem description: {problem.strip()}\n"

    if not user_input.strip():
        st.warning("Enter a machine model, alarm code, or problem description.")
        st.stop()

    with st.spinner("Thinking like a senior tech..."):
        resp = client.responses.create(
            model="gpt-5-mini",
            input=[
             {"role": "system", "content": PROMPT_V2 + (DEEP_ADDON if mode == "Deep" else "")},  
                {"role": "user", "content": user_input.strip()},
            ],
        )

    # Save result to session memory
    st.session_state["last_result"] = resp.output_text

    
# --- Display result if we have one ---
if st.session_state["last_result"]:
    st.subheader("Result")
    st.write(st.session_state["last_result"])

    st.download_button(
        "Download as text",
        data=st.session_state["last_result"],
        file_name="maintenance_troubleshooting_plan.txt",
        mime="text/plain",
    )
