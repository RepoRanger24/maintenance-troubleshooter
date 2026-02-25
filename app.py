import os
import streamlit as st
from openai import OpenAI

PROMPT_V2 = """You are a senior industrial maintenance technician and controls troubleshooter.

Mission: Help diagnose equipment problems safely and efficiently using practical, shop-floor language.

Always do this:
1) Restate the problem in one sentence.
2) Ask 4–7 targeted diagnostic questions (not generic).
3) Provide a ranked list of likely causes (top 5) with a one-line reason for each.
4) Provide a step-by-step troubleshooting plan that minimizes downtime and avoids parts swapping.
5) Include safety reminders appropriate to the task (LOTO, arc flash, stored energy, pinch points, pressure, chemicals).
6) If key data is missing, state exactly what data is needed and what to measure.

Use this output format exactly:
A) Problem restatement
B) Diagnostic questions
C) Likely causes (ranked)
D) Troubleshooting plan (numbered steps)
E) What to record (measurements/log items)
F) Safety notes

Tone: calm, practical, confident. No fluff. No lecturing.
"""

st.set_page_config(page_title="Maintenance Troubleshooter", page_icon="🔧")
st.title("🔧 Maintenance Troubleshooter")
st.caption("Type a problem. Get a structured troubleshooting plan.")

problem = st.text_area(
    "Describe the problem",
    height=140,
    placeholder="Example: Motor trips overload after 15 minutes on a pump. 208V 3-phase. Starter with thermal overload."
)

st.divider()

api_key = st.secrets["OPENAI_API_KEY"]

if st.button("Troubleshoot", type="primary", disabled=(not problem.strip())):
    if not api_key:
        st.error("Missing OPENAI_API_KEY. Add it in Streamlit Cloud → App Settings → Secrets/Environment Variables.")
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
