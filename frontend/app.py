"""LeadFlow AI - Streamlit frontend.

Four sections: Upload Leads, Lead Dashboard, Lead Explorer, AI Lead Brief.
Talks to the FastAPI backend over HTTP - no business logic lives here.
"""
import os

import pandas as pd
import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="LeadFlow AI", page_icon="📊", layout="wide")


def api_get(path: str, params: dict = None):
    try:
        resp = requests.get(f"{BACKEND_URL}{path}", params=params, timeout=15)
        return resp
    except requests.exceptions.ConnectionError:
        st.error(
            "Could not reach the backend API. Is it running at "
            f"{BACKEND_URL}? Start it with `uvicorn backend.main:app --reload`."
        )
        st.stop()


def api_post(path: str, **kwargs):
    try:
        resp = requests.post(f"{BACKEND_URL}{path}", timeout=30, **kwargs)
        return resp
    except requests.exceptions.ConnectionError:
        st.error(
            "Could not reach the backend API. Is it running at "
            f"{BACKEND_URL}? Start it with `uvicorn backend.main:app --reload`."
        )
        st.stop()


st.title("📊 LeadFlow AI")
st.caption("Smart Lead Prioritization Assistant")

tab_upload, tab_dashboard, tab_explorer, tab_brief = st.tabs(
    ["📤 Upload Leads", "📈 Lead Dashboard", "🔍 Lead Explorer", "🤖 AI Lead Brief"]
)

# ---------------------------------------------------------------------------
# 1. Upload Leads
# ---------------------------------------------------------------------------
with tab_upload:
    st.header("Upload Leads")
    st.write("Upload a CSV of sales leads to clean, deduplicate, and score them.")

    uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"])

    if uploaded_file is not None and st.button("Process Leads", type="primary"):
        with st.spinner("Cleaning, deduplicating, and scoring leads..."):
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "text/csv")}
            resp = api_post("/upload", files=files)

        if resp.status_code == 200:
            summary = resp.json()
            st.success("Leads processed successfully.")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Rows received", summary["total_rows_received"])
            c2.metric("Rows stored", summary["rows_stored"])
            c3.metric("Rows rejected", summary["rows_rejected"])
            c4.metric("Duplicates found", summary["duplicate_count"])

            c5, c6, c7 = st.columns(3)
            c5.metric("High priority", summary["high_priority_count"])
            c6.metric("Medium priority", summary["medium_priority_count"])
            c7.metric("Low priority", summary["low_priority_count"])

            if summary["validation_errors"]:
                with st.expander(f"⚠️ {len(summary['validation_errors'])} validation issue(s)"):
                    for err in summary["validation_errors"]:
                        st.write(f"- {err}")
        else:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            st.error(f"Upload failed: {detail}")

    st.divider()
    st.caption(
        "Tip: a ready-to-use sample file is at `data/sample_leads.csv` in "
        "this repository."
    )

# ---------------------------------------------------------------------------
# 2. Lead Dashboard
# ---------------------------------------------------------------------------
with tab_dashboard:
    st.header("Lead Dashboard")

    resp = api_get("/dashboard")
    if resp.status_code == 200:
        d = resp.json()

        if d["total_leads"] == 0:
            st.info("No leads yet. Upload a CSV in the 'Upload Leads' tab first.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Leads", d["total_leads"])
            col2.metric("Duplicate Leads", d["duplicate_count"])
            col3.metric("Average Score", d["average_score"])
            col4.metric("Est. Time Saved (min)", d["estimated_time_saved_minutes"])

            col5, col6, col7 = st.columns(3)
            col5.metric("🟢 High Priority", d["high_priority_count"])
            col6.metric("🟡 Medium Priority", d["medium_priority_count"])
            col7.metric("🔴 Low Priority", d["low_priority_count"])

            st.subheader("Priority Distribution")
            dist_df = pd.DataFrame(
                {
                    "Priority": ["High", "Medium", "Low"],
                    "Count": [
                        d["high_priority_count"],
                        d["medium_priority_count"],
                        d["low_priority_count"],
                    ],
                }
            ).set_index("Priority")
            st.bar_chart(dist_df)

            st.info(f"⏱️ {d['estimated_time_saved_note']}")
    else:
        st.warning("Could not load dashboard data.")

# ---------------------------------------------------------------------------
# 3. Lead Explorer
# ---------------------------------------------------------------------------
with tab_explorer:
    st.header("Lead Explorer")

    all_leads_resp = api_get("/leads")
    all_leads = all_leads_resp.json() if all_leads_resp.status_code == 200 else []

    if not all_leads:
        st.info("No leads yet. Upload a CSV in the 'Upload Leads' tab first.")
    else:
        sources = sorted({l["source"] for l in all_leads if l.get("source")})

        colf1, colf2 = st.columns(2)
        priority_filter = colf1.selectbox("Priority filter", ["All", "High", "Medium", "Low"])
        source_filter = colf2.selectbox("Source filter", ["All"] + sources)

        params = {}
        if priority_filter != "All":
            params["priority"] = priority_filter
        if source_filter != "All":
            params["source"] = source_filter

        filtered_resp = api_get("/leads", params=params)
        filtered_leads = filtered_resp.json() if filtered_resp.status_code == 200 else []

        if not filtered_leads:
            st.info("No leads match the current filters.")
        else:
            df = pd.DataFrame(filtered_leads)
            display_cols = [
                "id", "name", "company", "job_title", "seniority", "industry",
                "score", "priority", "is_duplicate", "duplicate_reason", "source",
            ]
            display_cols = [c for c in display_cols if c in df.columns]
            st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

            def _label(lead_id: int) -> str:
                match = next(l for l in filtered_leads if l["id"] == lead_id)
                return f"#{lead_id} — {match.get('name') or 'Unnamed lead'} ({match.get('company') or 'Unknown company'})"

            selected_id = st.selectbox(
                "Select a lead to inspect", df["id"].tolist(), format_func=_label
            )
            selected = next(l for l in filtered_leads if l["id"] == selected_id)

            st.subheader(f"Score Breakdown — {selected.get('name') or 'Unnamed lead'}")
            colA, colB = st.columns(2)
            colA.metric("Total Score", selected["score"])
            colB.metric("Priority", selected["priority"])

            if selected.get("score_breakdown"):
                breakdown_df = pd.DataFrame(
                    list(selected["score_breakdown"].items()), columns=["Category", "Points"]
                )
                st.table(breakdown_df)

            col_pos, col_neg = st.columns(2)
            with col_pos:
                st.markdown("**✅ Positive factors**")
                for r in selected.get("positive_reasons") or []:
                    st.write(f"- {r}")
            with col_neg:
                st.markdown("**⚠️ Limiting factors**")
                for r in selected.get("negative_reasons") or []:
                    st.write(f"- {r}")

            if selected.get("is_duplicate"):
                st.warning(
                    f"Possible duplicate (group {selected.get('duplicate_group')}): "
                    f"{selected.get('duplicate_reason')}"
                )

# ---------------------------------------------------------------------------
# 4. AI Lead Brief
# ---------------------------------------------------------------------------
with tab_brief:
    st.header("AI Lead Brief")

    leads_resp = api_get("/leads")
    leads = leads_resp.json() if leads_resp.status_code == 200 else []

    if not leads:
        st.info("No leads yet. Upload a CSV in the 'Upload Leads' tab first.")
    else:
        def _label(lead_id: int) -> str:
            match = next(l for l in leads if l["id"] == lead_id)
            return f"#{lead_id} — {match.get('name') or 'Unnamed lead'} ({match.get('company') or 'Unknown company'})"

        selected_id = st.selectbox(
            "Choose a lead", [l["id"] for l in leads], format_func=_label, key="brief_select"
        )

        if st.button("Generate AI Summary", type="primary"):
            with st.spinner("Generating AI lead brief..."):
                resp = api_post(f"/leads/{selected_id}/generate-ai-summary")

            if resp.status_code == 200:
                brief = resp.json()
                if brief.get("is_mock"):
                    st.info("ℹ️ Mock AI response (no GROQ_API_KEY configured).")

                st.subheader("Lead Summary")
                st.write(brief["lead_summary"])

                st.subheader("Why This Lead Matters")
                st.write(brief["why_this_lead_matters"])

                st.subheader("Suggested Outreach Angle")
                st.write(brief["suggested_outreach_angle"])

                st.subheader("Discovery Questions")
                for q in brief["discovery_questions"]:
                    st.write(f"- {q}")

                st.divider()
                st.caption(brief["disclaimer"])
            elif resp.status_code == 429:
                st.error("Rate limited by the AI provider. Please wait a moment and try again.")
            elif resp.status_code == 504:
                st.error("The AI request timed out. Please try again.")
            elif resp.status_code == 503:
                st.error("The AI provider is currently unavailable.")
            else:
                try:
                    detail = resp.json().get("detail", resp.text)
                except ValueError:
                    detail = resp.text
                st.error(f"AI summary failed: {detail}")
