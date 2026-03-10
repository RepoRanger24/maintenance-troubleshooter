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
- Prefer checks that are quick and realistic.

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
"""

DEEP_ADDON = """
DEEP MODE:
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
"""

# -----------------------------
# Page UI
# -----------------------------
st.set_page_config(page_title="Maintenance Troubleshooter", page_icon="🔧")
st.title("🔧 Maintenance Troubleshooter")
st.caption("Type a machine problem. Get a fast troubleshooting plan.")

mode = st.radio("Mode", ["Quick", "Deep"], horizontal=True)

problem = st.text_area(
    "Describe the problem",
    key=f"problem_text_{st.session_state['form_id']}",
    height=120,
    placeholder="Examples: pusher stuck, remnant jam, SQ2 sensor, AL010, bar feeder won't start"
)

alarm_code = st.text_input(
    "Alarm code (optional)",
    key=f"alarm_code_{st.session_state['form_id']}",
    placeholder="Example: AL05, SQ3, FANUC 401"
)

machine_model = st.text_input(
    "Machine / Control Model (optional)",
    key=f"machine_model_{st.session_state['form_id']}",
    placeholder="Example: GT 326-E, Fanuc 31i, Haas VF2"
)

with st.expander("Advanced filters (optional)"):
    category_options = ["All"]
    manufacturer_options = ["All"]
    model_options = ["All"]

    if not manual_db.empty and "category" in manual_db.columns:
        category_options += sorted(
            manual_db["category"].astype(str).replace("", pd.NA).dropna().unique().tolist()
        )

    if not manual_db.empty and "manufacturer" in manual_db.columns:
        manufacturer_options += sorted(
            manual_db["manufacturer"].astype(str).replace("", pd.NA).dropna().unique().tolist()
        )

    if not manual_db.empty and "model" in manual_db.columns:
        model_options += sorted(
            manual_db["model"].astype(str).replace("", pd.NA).dropna().unique().tolist()
        )

    category = st.selectbox("Category", category_options, key="filter_category")
    manufacturer = st.selectbox("Manufacturer", manufacturer_options, key="filter_manufacturer")
    model = st.selectbox("Model", model_options, key="filter_model")

st.divider()

# -----------------------------
# Build one query
# -----------------------------
query_parts = [
    problem.strip(),
    alarm_code.strip(),
    machine_model.strip()
]
search_query = " ".join([p for p in query_parts if p]).strip()

# -----------------------------
# Apply filters
# -----------------------------
filtered_manual = manual_db.copy()

if not filtered_manual.empty and category != "All" and "category" in filtered_manual.columns:
    filtered_manual = filtered_manual[filtered_manual["category"] == category]

if not filtered_manual.empty and manufacturer != "All" and "manufacturer" in filtered_manual.columns:
    filtered_manual = filtered_manual[filtered_manual["manufacturer"] == manufacturer]

if not filtered_manual.empty and model != "All" and "model" in filtered_manual.columns:
    filtered_manual = filtered_manual[filtered_manual["model"] == model]

# -----------------------------
# Search libraries
# ----------------------------- 
# -----------------------------
# Search libraries
# -----------------------------
manual_hits = pd.DataFrame()
symptom_hits = pd.DataFrame()

if search_query:
    keywords = [word.strip() for word in search_query.lower().split() if word.strip()]

    if not filtered_manual.empty:
        manual_haystack = filtered_manual.astype(str).agg(" | ".join, axis=1).str.lower()
        manual_scores = manual_haystack.apply(lambda row: sum(word in row for word in keywords))
        manual_hits = filtered_manual[manual_scores > 0].copy()
        manual_hits["match_score"] = manual_scores[manual_scores > 0].values
        manual_hits = manual_hits.sort_values(by="match_score", ascending=False)

    if not symptom_db.empty:
        symptom_haystack = symptom_db.astype(str).agg(" | ".join, axis=1).str.lower()
        symptom_scores = symptom_haystack.apply(lambda row: sum(word in row for word in keywords))
        symptom_hits = symptom_db[symptom_scores > 0].copy()
        symptom_hits["match_score"] = symptom_scores[symptom_scores > 0].values
        symptom_hits = symptom_hits.sort_values(by="match_score", ascending=False)        
# -----------------------------
# Buttons
# -----------------------------
has_input = bool(search_query)
api_key = os.getenv("OPENAI_API_KEY", "")

col1, col2 = st.columns([1, 1])

with col1:
    troubleshoot_clicked = st.button(
        "Troubleshoot",
        type="primary",
        disabled=False,
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

# -----------------------------
# Troubleshoot
# -----------------------------
if troubleshoot_clicked:
    if not search_query:
        st.warning("Please enter a problem description, alarm code, or machine model.")
        st.stop()
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
          st.session_state["last_result"] = "\n".join(lines)
      else:
        lines = []

        if not symptom_hits.empty:
            top_row = symptom_hits.iloc[0]
            top_symptom = top_row.get("symptom", "")
            top_alarms = top_row.get("likely_alarms", "")
            top_score = top_row.get("match_score", 0)

            if top_score >= 3:
                confidence = "High"
            elif top_score == 2:
                confidence = "Medium"
            else:
                confidence = "Low"

            lines.append(f"Most likely problem: {top_symptom}")
            lines.append(f"Confidence: {confidence}")
            lines.append(f"Likely alarms: {top_alarms}")
            lines.append("")
            lines.append("Top symptom matches:")

            for i, (_, row) in enumerate(symptom_hits.head(3).iterrows(), start=1):
                symptom = row.get("symptom", "")
                alarms = row.get("likely_alarms", "")
                score = row.get("match_score", 0)
                lines.append(f"{i}. {symptom} — Likely alarms: {alarms} — Score: {score}")

        if not manual_hits.empty:
            lines.append("")
            lines.append("Top manual matches:")
            for i, (_, row) in enumerate(manual_hits.head(3).iterrows(), start=1):
                model = row.get("model", "")
                alarm = row.get("alarm_code", "")
                symptom = row.get("symptom", "")
                fix = row.get("fix", "")
                score = row.get("match_score", 0)
                lines.append(f"{i}. {model} {alarm} — {symptom} — Score: {score}")
                if str(fix).strip():
                    lines.append(f"   Fix: {fix}")

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

# -----------------------------
# Optional match view
# -----------------------------
if search_query:
    with st.expander("Show search matches", expanded=True):
        st.subheader("Manual Matches")
        if not manual_hits.empty:
            st.dataframe(manual_hits, use_container_width=True)
        else:
            st.info("No manual matches found.")

        st.subheader("Symptom Matches")
        if not symptom_hits.empty:
            st.dataframe(symptom_hits, use_container_width=True)
        else:
            st.info("No symptom matches found.")
