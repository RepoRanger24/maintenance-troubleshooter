import os
import streamlit as st
import pandas as pd
from openai import OpenAI
import re
from difflib import SequenceMatcher
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
# Search scoring helpers
# -----------------------------
SHOP_SYNONYMS = {
    "stuck": ["jam", "jammed", "binding", "hung"],
    "jam": ["stuck", "jammed", "binding"],
    "feed": ["feeding", "load", "loading", "advance", "pusher"],
    "loader": ["barloader", "bar feeder", "feeder"],
    "bar": ["stock", "material", "blank"],
    "home": ["homing", "reference", "zero return"],
    "alarm": ["fault", "error", "code"],
    "remnant": ["stub bar", "short bar", "end piece"],
    "ready": ["ready signal", "machine ready", "loader ready"],
}

WEIGHTS = {
    "symptom": 3,
    "likely_alarms": 3,
    "alarm_code": 3,
    "machine": 2,
    "manufacturer": 2,
    "model": 2,
    "machine_area": 2,
    "category": 1,
    "keywords": 1,
    "fix": 1,
}

ALARM_EXACT_BOOST = 12
ALARM_PARTIAL_BOOST = 6
PHRASE_MATCH_BOOST = 5
FUZZY_MATCH_THRESHOLD = 0.84


def clean_text(text):
    text = str(text).lower().strip()
    text = re.sub(r"[^a-z0-9\s\-_]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def tokenize(text):
    return clean_text(text).split()


def fuzzy_ratio(a, b):
    return SequenceMatcher(None, a, b).ratio()


def extract_alarm_codes(text):
    text = str(text).upper()
    matches = re.findall(r"\b(?:[A-Z]{1,3}\d{1,4}|\d{3,4})\b", text)
    return list(set(matches))


def expand_query_terms(query):
    query_clean = clean_text(query)
    expanded = set(tokenize(query_clean))

    for key, synonyms in SHOP_SYNONYMS.items():
        if key in query_clean:
            expanded.update(tokenize(key))
            for syn in synonyms:
                expanded.update(tokenize(syn))

    return list(expanded)


def score_field(field_value, query_terms, weight):
    field_text = clean_text(field_value)
    if not field_text:
        return 0

    field_tokens = set(tokenize(field_text))
    score = 0

    for term in query_terms:
        term_clean = clean_text(term)
        if not term_clean:
            continue

        if term_clean in field_tokens:
            score += 1 * weight
            continue

        if len(term_clean.split()) > 1 and term_clean in field_text:
            score += PHRASE_MATCH_BOOST * weight
            continue

        for token in field_tokens:
            if fuzzy_ratio(term_clean, token) >= FUZZY_MATCH_THRESHOLD:
                score += 0.75 * weight
                break

    return score


def calculate_match_score(row, query):
    query_clean = clean_text(query)
    query_terms = expand_query_terms(query)
    alarm_codes = extract_alarm_codes(query)

    total_score = 0

    for field, weight in WEIGHTS.items():
        if field in row.index:
            total_score += score_field(row.get(field, ""), query_terms, weight)

    symptom_text = clean_text(row.get("symptom", ""))
    keywords_text = clean_text(row.get("keywords", ""))
    alarm_text = str(row.get("likely_alarms", "")).upper() + " " + str(row.get("alarm_code", "")).upper()

    if query_clean and query_clean in symptom_text:
        total_score += PHRASE_MATCH_BOOST * 3

    if query_clean and query_clean in keywords_text:
        total_score += PHRASE_MATCH_BOOST * 2

    for code in alarm_codes:
        if code in alarm_text.split():
            total_score += ALARM_EXACT_BOOST
        elif code in alarm_text:
            total_score += ALARM_PARTIAL_BOOST

    return round(total_score, 2)


def confidence_label(score):
    if score >= 18:
        return "High"
    elif score >= 8:
        return "Medium"
    elif score > 0:
        return "Low"
    return "No Match"
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
    machine_model.strip(),
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
filtered_manual = filtered_manual[filtered_manual["model"] == model]


filtered_symptom = symptom_db.copy()

if not filtered_symptom.empty and category != "All" and "category" in filtered_symptom.columns:
    filtered_symptom = filtered_symptom[filtered_symptom["category"] == category]

if not filtered_symptom.empty and manufacturer != "All" and "manufacturer" in filtered_symptom.columns:
    filtered_symptom = filtered_symptom[filtered_symptom["manufacturer"] == manufacturer]

if not filtered_symptom.empty and model != "All" and "model" in filtered_symptom.columns:
    filtered_symptom = filtered_symptom[filtered_symptom["model"] == model]
if not filtered_manual.empty and model != "All" and "model" in filtered_manual.columns:
    filtered_manual = filtered_manual[filtered_manual["model"] == model]

# -----------------------------
# Search libraries
# -----------------------------
manual_hits = pd.DataFrame()
symptom_hits = pd.DataFrame()

if search_query:
    keywords = [word.strip() for word in search_query.lower().split() if word.strip()]

    if not filtered_manual.empty:
        manual_haystack = filtered_manual.astype(str).agg(" | ".join, axis=1).str.lower()
        manual_scores = manual_haystack.apply(
            lambda row: sum(1 for word in keywords if word in row)
        )
        manual_hits = filtered_manual[manual_scores > 0].copy()
        if not manual_hits.empty:
            manual_hits["match_score"] = manual_scores[manual_scores > 0].values
            manual_hits = manual_hits.sort_values(by="match_score", ascending=False)

    if not symptom_db.empty:
        symptom_haystack = symptom_db.astype(str).agg(" | ".join, axis=1).str.lower()
        symptom_scores = symptom_haystack.apply(
            lambda row: sum(1 for word in keywords if word in row)
        )
        symptom_hits = symptom_db[symptom_scores > 0].copy()
        if not symptom_hits.empty:
            symptom_hits["match_score"] = symptom_scores[symptom_scores > 0].values
            symptom_hits = symptom_hits.sort_values(by="match_score", ascending=False)

# -----------------------------
# Buttons
# -----------------------------
api_key = os.getenv("OPENAI_API_KEY", "")

col1, col2 = st.columns([1, 1])

with col1:
    troubleshoot_clicked = st.button(
        "Troubleshoot",
        type="primary",
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

    else:
        lines = []

        if not symptom_hits.empty:
            top_row = symptom_hits.iloc[0]
            top_symptom = top_row.get("symptom", "")
            top_alarms = top_row.get("likely_alarms", "")
            top_score = int(top_row.get("match_score", 0))

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
                score = int(row.get("match_score", 0))
                lines.append(f"{i}. {symptom} — Likely alarms: {alarms} — Score: {score}")

        if not manual_hits.empty:
            lines.append("")
            lines.append("Top manual matches:")

            for i, (_, row) in enumerate(manual_hits.head(3).iterrows(), start=1):
                model_name = row.get("model", "")
                alarm = row.get("alarm_code", "")
                symptom = row.get("symptom", "")
                fix = row.get("fix", "")
                score = int(row.get("match_score", 0))

                lines.append(f"{i}. {model_name} {alarm} — {symptom} — Score: {score}")
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
