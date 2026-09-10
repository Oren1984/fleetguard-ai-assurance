"""FleetGuard AI - Streamlit dashboard.

Minimal operational UI: fleet risk overview, per-truck drill-down with the
evidence/SOP/explanation behind each recommendation, the human approval
queue, the audit trail, and the kill switch.
"""
import os
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="FleetGuard AI", page_icon="🚛", layout="wide")

RISK_COLORS = {"HIGH": "#e03131", "MEDIUM": "#f08c00", "LOW": "#2f9e44", "INSUFFICIENT_DATA": "#868e96"}


def api_get(path, params=None):
    try:
        resp = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        st.error(f"API request failed: {exc}")
        return None


def api_post(path, json=None, params=None):
    try:
        resp = requests.post(f"{API_BASE_URL}{path}", json=json, params=params, timeout=15)
        if resp.status_code >= 400:
            st.error(f"Request failed ({resp.status_code}): {resp.json().get('detail', resp.text)}")
            return None
        return resp.json()
    except requests.RequestException as exc:
        st.error(f"API request failed: {exc}")
        return None


def risk_badge(level: str) -> str:
    color = RISK_COLORS.get(level, "#868e96")
    return f'<span style="background-color:{color};color:white;padding:2px 10px;border-radius:10px;font-weight:600;font-size:0.85em">{level}</span>'


# --- Sidebar: system status + kill switch -----------------------------
st.sidebar.title("🚛 FleetGuard AI")
st.sidebar.caption("AI-Assisted Cold-Chain Risk & Incident Response")

health = api_get("/health")
if health:
    status_icon = "🟢" if health["status"] == "ok" else "🔴"
    st.sidebar.markdown(f"**System status:** {status_icon} {health['status'].upper()}")
    st.sidebar.markdown(f"**LLM provider:** `{health['llm_provider']}`")
    st.sidebar.markdown(f"**Fleet size:** {health['truck_count']} trucks")

st.sidebar.divider()
st.sidebar.subheader("⚠️ Kill Switch")
ks = api_get("/admin/kill-switch")
if ks:
    engaged = ks["kill_switch_engaged"]
    if engaged:
        st.sidebar.error("KILL SWITCH ENGAGED — all agent operations are halted.")
    else:
        st.sidebar.success("Agent operations active.")

    actor = st.sidebar.text_input("Your name (for audit)", value="ops_admin", key="ks_actor")
    col_a, col_b = st.sidebar.columns(2)
    if col_a.button("🛑 Engage", disabled=engaged, use_container_width=True):
        api_post("/admin/kill-switch", json={"engaged": True, "actor": actor, "reason": "Manual stop from dashboard"})
        st.rerun()
    if col_b.button("✅ Resume", disabled=not engaged, use_container_width=True):
        api_post("/admin/kill-switch", json={"engaged": False, "actor": actor, "reason": "Manual resume from dashboard"})
        st.rerun()

st.sidebar.divider()
if st.sidebar.button("🔄 Refresh data", use_container_width=True):
    st.rerun()
if st.sidebar.button("▶️ Run assessment for all trucks", use_container_width=True):
    api_post("/risk/assessments/run-all")
    st.rerun()

# --- Main content --------------------------------------------------------
tab_overview, tab_detail, tab_approvals, tab_audit = st.tabs(
    ["📊 Fleet Overview", "🔍 Truck Detail", "✅ Approval Queue", "📜 Audit Trail"]
)

with tab_overview:
    st.header("Fleet Risk Overview")
    assessments = api_get("/risk/assessments", params={"latest_only": True}) or []

    if assessments:
        counts = pd.Series([a["risk_level"] for a in assessments]).value_counts()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🔴 High Risk", int(counts.get("HIGH", 0)))
        c2.metric("🟠 Medium Risk", int(counts.get("MEDIUM", 0)))
        c3.metric("🟢 Low Risk", int(counts.get("LOW", 0)))
        pending = [a for a in assessments if a.get("approval_status") == "PENDING"]
        c4.metric("⏳ Pending Approvals", len(pending))

        st.divider()
        rows = []
        for a in sorted(assessments, key=lambda x: x["risk_score"], reverse=True):
            rows.append(
                {
                    "Truck": a["truck_id"],
                    "Risk Level": a["risk_level"],
                    "Risk Score": a["risk_score"],
                    "Recommended Action": a["recommended_action"].replace("_", " ").title(),
                    "Approval": a.get("approval_status") or "—",
                    "Grounded": "✅" if a["grounded"] else "⚠️",
                }
            )
        df = pd.DataFrame(rows)

        def _style_risk(val):
            color = RISK_COLORS.get(val, "#868e96")
            return f"background-color:{color};color:white;font-weight:600"

        st.dataframe(
            df.style.map(_style_risk, subset=["Risk Level"]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No risk assessments yet. Click 'Run assessment for all trucks' in the sidebar.")

with tab_detail:
    st.header("Truck Detail")
    trucks = api_get("/trucks") or []
    if trucks:
        truck_ids = [t["id"] for t in trucks]
        demo_default = next((t["id"] for t in trucks if t.get("is_demo_scenario")), truck_ids[0])
        selected = st.selectbox("Select a truck", truck_ids, index=truck_ids.index(demo_default))

        truck = next(t for t in trucks if t["id"] == selected)
        col1, col2, col3 = st.columns(3)
        col1.markdown(f"**Driver:** {truck['driver_name']}")
        col1.markdown(f"**Cargo:** {truck['cargo_type']}")
        col2.markdown(f"**Route:** {truck['route_name']}")
        col2.markdown(f"**Setpoint:** {truck['temp_setpoint_c']}°C")
        col3.markdown(f"**Region:** {truck['region']}")
        if truck.get("is_demo_scenario"):
            col3.markdown("🎬 **Primary demo scenario truck**")

        telemetry = api_get(f"/trucks/{selected}/telemetry") or []
        if telemetry:
            tdf = pd.DataFrame(telemetry)
            tdf["timestamp"] = pd.to_datetime(tdf["timestamp"])
            st.subheader("Cargo & External Temperature Over Time")
            chart_df = tdf.set_index("timestamp")[["cargo_temp_c", "external_temp_c"]]
            chart_df.columns = ["Cargo Temp (°C)", "External Temp (°C)"]
            st.line_chart(chart_df)

        st.subheader("Latest Risk Assessment")
        try:
            resp = requests.get(f"{API_BASE_URL}/trucks/{selected}/latest-assessment", timeout=10)
            assessment = resp.json() if resp.status_code == 200 else None
        except requests.RequestException:
            assessment = None

        if not assessment:
            st.info("No assessment yet for this truck.")
        else:
            st.markdown(risk_badge(assessment["risk_level"]) + f"  &nbsp; Score: **{assessment['risk_score']}**/100", unsafe_allow_html=True)
            st.markdown(f"**Recommended action:** {assessment['recommended_action'].replace('_', ' ').title()}")

            st.markdown("**Why this decision was made (evidence):**")
            for r in assessment["reasons"]:
                st.markdown(f"- **{r['factor'].replace('_', ' ').title()}**: {r['detail']} _(+{r['score_contribution']} pts)_")

            st.markdown("**AI Explanation:**")
            if assessment["grounded"]:
                st.success(assessment["explanation"])
            else:
                st.warning(assessment["explanation"])

            st.markdown("**Retrieved SOP source(s):**")
            if assessment["sop_sources"]:
                for s in assessment["sop_sources"]:
                    with st.expander(f"{s['doc']} — {s['section']} (similarity {s['similarity']:.2f})"):
                        st.text(s["excerpt"])
            else:
                st.caption("No SOP section met the retrieval confidence threshold.")

            if assessment.get("evidence_snapshot", {}).get("recommended_facility"):
                fac = assessment["evidence_snapshot"]["recommended_facility"]
                st.info(f"📍 Recommended diversion facility: **{fac['name']}** ({fac['id']}, {fac['region']} region)")

            if assessment["approval_status"]:
                st.markdown(f"**Approval status:** {assessment['approval_status']}")
    else:
        st.info("No trucks found. The backend seeds synthetic data automatically on startup.")

with tab_approvals:
    st.header("Human Approval Queue")
    st.caption("Significant actions (route change / diversion) require explicit approval before execution.")
    pending = api_get("/approvals", params={"status": "PENDING"}) or []

    if not pending:
        st.success("No approvals pending.")
    else:
        assessments_by_id = {a["id"]: a for a in (api_get("/risk/assessments", params={"latest_only": False}) or [])}
        for ap in pending:
            assessment = assessments_by_id.get(ap["risk_assessment_id"])
            with st.container(border=True):
                if assessment:
                    st.markdown(
                        risk_badge(assessment["risk_level"])
                        + f"&nbsp; **Truck {assessment['truck_id']}** — {assessment['recommended_action'].replace('_', ' ').title()}",
                        unsafe_allow_html=True,
                    )
                    st.caption(assessment["explanation"])
                else:
                    st.markdown(f"**Approval #{ap['id']}**")

                actor = st.text_input("Approver name", value="fleet_manager", key=f"actor_{ap['id']}")
                comments = st.text_input("Comments (optional)", key=f"comments_{ap['id']}")
                c1, c2 = st.columns(2)
                if c1.button("✅ Approve", key=f"approve_{ap['id']}", use_container_width=True):
                    api_post(f"/approvals/{ap['id']}/decision", json={"decision": "approve", "actor": actor, "comments": comments})
                    st.rerun()
                if c2.button("❌ Reject", key=f"reject_{ap['id']}", use_container_width=True):
                    api_post(f"/approvals/{ap['id']}/decision", json={"decision": "reject", "actor": actor, "comments": comments})
                    st.rerun()

    st.divider()
    st.subheader("Recently decided")
    decided = [a for a in (api_get("/approvals") or []) if a["status"] != "PENDING"][:10]
    if decided:
        ddf = pd.DataFrame(decided)[["id", "status", "decided_by", "decided_at", "comments"]]
        st.dataframe(ddf, use_container_width=True, hide_index=True)

        st.subheader("Execute an approved action")
        approved_ids = [a["id"] for a in decided if a["status"] == "APPROVED"]
        if approved_ids:
            exec_id = st.selectbox("Approval ID", approved_ids)
            exec_actor = st.text_input("Executed by", value="ops_operator")
            if st.button("▶️ Execute action"):
                result = api_post(f"/approvals/{exec_id}/execute", params={"actor": exec_actor})
                if result:
                    st.success(f"Executed: {result['notes']}")

with tab_audit:
    st.header("Audit Trail")
    entries = api_get("/audit", params={"limit": 300}) or []
    if entries:
        adf = pd.DataFrame(entries)
        adf["timestamp"] = pd.to_datetime(adf["timestamp"])
        adf = adf.sort_values("timestamp", ascending=False)
        st.dataframe(adf[["timestamp", "event_type", "actor", "truck_id", "details"]], use_container_width=True, hide_index=True)
    else:
        st.info("No audit entries yet.")

st.sidebar.divider()
st.sidebar.caption(f"Last refreshed: {datetime.now().strftime('%H:%M:%S')}")
