import os
import streamlit as st
import pandas as pd
from openai import OpenAI

# -----------------------------
# Session state
# -----------------------------
if "form_id" not in st.session_state:
    st.session_state["form_id"] = 0

if "last_result" not in st.session_state:
    st.session_state["last_result"] = ""

# -----------------------------
# File paths
# -----------------------------
BASE_DIR = os.path.dirname(__file__)
MANUAL_CSV = os.path.join(BASE_DIR, "data", "manual_library.csv")
SYMPTOM_CSV = os.path.join(BASE_DIR, "data", "symptom_library.csv")

# -----------------------------
# Load CSVs
# -----------------------------
try:
    manual_db = pd.read_csv(MANUAL_CSV).fillna("")
except Exception as e:
    st.error(f"Failed to load manual CSV: {e}")
    manual_db = pd.DataFrame()

try:
    symptom_db = pd.read_csv(SYMPTOM_CSV).fillna("")
except Exception as e:
    st.error(f"Failed to load symptom CSV: {e}")
    symptom_db = pd.DataFrame()

# -----------------------------
# Prompt
# -----------------------------
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

# -----------------------------
# Page UI
# -----------------------------
st.set_page_config(page_title="Maintenance Troubleshooter", page_icon="🔧")
st.title("🔧 Maintenance Troubleshooter")
st.caption("Type a problem. Get a fast troubleshooting plan.")

st.info("""
Best for:
• CNC machine alarms
• Barloader faults
• Chip conveyor problems

How to use:
1. Enter machine/control if known
2. Enter alarm code OR describe the problem
3. Click Troubleshoot
""")

mode = st.radio("Mode", ["Quick", "Deep"], horizontal=True)

# -----------------------------
# Inputs first
# -----------------------------
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

problem = st.text_area(
    "Describe the problem",
    key=f"problem_text_{st.session_state['form_id']}",
    height=140,
    placeholder="Example: Motor trips overload after 15 minutes on a pump. 480V 3-phase."
)

st.divider()

# -----------------------------
# Manual Search
# -----------------------------
st.subheader("Manual Search")

if not manual_db.empty and "category" in manual_db.columns:
    category_options = ["All"] + sorted(manual_db["category"].astype(str).replace("", pd.NA).dropna().unique().tolist())
else:
    category_options = ["All"]

if not manual_db.empty and "manufacturer" in manual_db.columns:
    manufacturer_options = ["All"] + sorted(manual_db["manufacturer"].astype(str).replace("", pd.NA).dropna().unique().tolist())
else:
    manufacturer_options = ["All"]

if not manual_db.empty and "model" in manual_db.columns:
    model_options = ["All"] + sorted(manual_db["model"].astype(str).replace("", pd.NA).dropna().unique().tolist())
else:
    model_options = ["All"]

category = st.selectbox("Category (optional)", category_options, key="filter_category")
manufacturer = st.selectbox("Manufacturer (optional)", manufacturer_options, key="filter_manufacturer")
model = st.selectbox("Model (optional)", model_options, key="filter_model")

filtered = manual_db.copy()

if not filtered.empty and category != "All" and "category" in filtered.columns:
    filtered = filtered[filtered["category"] == category]

if not filtered.empty and manufacturer != "All" and "manufacturer" in filtered.columns:
    filtered = filtered[filtered["manufacturer"] == manufacturer]

if not filtered.empty and model != "All" and "model" in filtered.columns:
    filtered = filtered[filtered["model"] == model]

q = st.text_input(
    "Search manuals (example: SQ5, air pressure, barloader fault)",
    key="manual_search"
)

manual_query = q.strip()
if not manual_query:
    parts = [machine_model.strip(), alarm_code.strip(), problem.strip()]
    manual_query = " ".join([p for p in parts if p])

# Manual matches
manual_hits = pd.DataFrame()
if manual_query and not filtered.empty:
    haystack = filtered.astype(str).agg(" | ".join, axis=1)
    manual_hits = filtered[haystack.str.contains(manual_query, case=False, na=False)].copy()

st.subheader("Manual Matches")
if not manual_hits.empty:
    st.caption(f"Matches: {len(manual_hits)}")
    st.dataframe(manual_hits, use_container_width=True)
else:
    st.info("No manual matches found.")

# Symptom matches
symptom_hits = pd.DataFrame()
if manual_query and not symptom_db.empty:
    symptom_haystack = symptom_db.astype(str).agg(" | ".join, axis=1)
    symptom_hits = symptom_db[symptom_haystack.str.contains(manual_query, case=False, na=False)].copy()

st.subheader("Symptom Matches")
if not symptom_hits.empty:
    st.caption(f"Matches: {len(symptom_hits)}")
    st.dataframe(symptom_hits, use_container_width=True)
else:
    st.info("No symptom matches found.")

st.divider()

# -----------------------------
# Troubleshoot button logic
# -----------------------------
api_key = os.getenv("OPENAI_API_KEY", "")

has_input = any([
    machine_model.strip(),
    alarm_code.strip(),
    problem.strip()
])

col1, col2 = st.columns([1, 1])

with col1:
    troubleshoot_clicked = st.button(
        "Troubleshoot",
        type="primary" if has_input else "secondary",
        disabled=not has_input,
        key=f"troubleshoot_{st.session_state['form_id']}",
    )

with col2:
    reset_clicked = st.button(
        "Reset",
        key=f"reset_{st.session_state['form_id']}",
    )

if reset_clicked:
    st.session_state["last_result"] = ""
    st.session_state["form_id"] += 1
    st.rerun()

if troubleshoot_clicked:
    user_input = ""

    if machine_model.strip():
        user_input += f"Machine/control: {machine_model.strip()}\n"

    if alarm_code.strip():
        user_input += f"Alarm code: {alarm_code.strip()}\n"

    if problem.strip():
        user_input += f"Problem description: {problem.strip()}\n"

    if api_key:
        client = OpenAI(api_key=api_key)

        if not manual_hits.empty:
            user_input += "\nManual library matches:\n"
            user_input += manual_hits.head(5).to_string(index=False)

        if not symptom_hits.empty:
            user_input += "\n\nSymptom library matches:\n"
            user_input += symptom_hits.head(5).to_string(index=False)

        with st.spinner("Thinking like a senior tech..."):
            resp = client.responses.create(
                model="gpt-5-mini",
                input=[
                    {
                        "role": "system",
                        "content": PROMPT_V2 + (DEEP_ADDON if mode == "Deep" else "")
                    },
                    {
                        "role": "user",
                        "content": user_input.strip()
                    },
                ],
            )

        st.session_state["last_result"] = resp.output_text

    else:
        lines = []

        if not manual_hits.empty:
            row = manual_hits.iloc[0]
            lines.append(f"Manual match: {row.get('model', '')} - {row.get('alarm_code', '')}")
            lines.append(f"Symptom: {row.get('symptom', '')}")
            lines.append(f"Likely causes: {row.get('causes', '')}")
            if "fix" in row and str(row.get("fix", "")).strip():
                lines.append(f"Suggested fix: {row.get('fix', '')}")

        if not symptom_hits.empty:
            srow = symptom_hits.iloc[0]
            lines.append(f"Symptom library match: {srow.get('symptom', '')}")
            lines.append(f"Likely alarms: {srow.get('likely_alarms', '')}")

        if not lines:
            lines.append("No matching records found in the manual or symptom libraries.")

        st.session_state["last_result"] = "\n".join(lines)

# -----------------------------
# Show result
# -----------------------------
if st.session_state["last_result"]:
    st.subheader("Result")
    st.write(st.session_state["last_result"])

    st.download_button(
        "Download as text",
        data=st.session_state["last_result"],
        file_name="maintenance_troubleshooting_plan.txt",
        mime="text/plain",
    )
