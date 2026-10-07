"""
Streamlit curator dashboard.
Run: streamlit run ui/curator.py
Expects API at http://127.0.0.1:8000
"""
from __future__ import annotations

import os

import httpx
import streamlit as st

API = os.getenv("CHRONICLE_API", "http://127.0.0.1:8000/api")

st.set_page_config(page_title="Chronicle Curator", layout="wide")
st.title("Verified Local Chronicle — Curator")
st.caption("Human-in-the-loop · R/E/M scores · Solana checkpoint after Approve")

tab_ingest, tab_queues, tab_timeline = st.tabs(["Ingest", "Review queues", "Public timeline"])

with tab_ingest:
    st.subheader("Add material")
    url = st.text_input("URL (optional)")
    text = st.text_area("Or paste raw text", height=160)
    if st.button("Process", type="primary"):
        payload = {}
        if url.strip():
            payload["url"] = url.strip()
        if text.strip():
            payload["raw_text"] = text.strip()
        if not payload:
            st.error("Provide URL or text")
        else:
            try:
                r = httpx.post(f"{API}/ingest", json=payload, timeout=300.0)
                r.raise_for_status()
                data = r.json()
                st.success(f"Queue: **{data.get('queue')}** · Event `{data.get('event_id')}`")
                st.json(data)
            except Exception as e:
                st.error(str(e))

with tab_queues:
    queue = st.selectbox(
        "Queue",
        ["DEEP_REVIEW", "FULL_REVIEW", "QUICK_REVIEW", "OUT_OF_SCOPE"],
    )
    if st.button("Refresh queue"):
        st.session_state["queue_data"] = httpx.get(f"{API}/queue/{queue}", timeout=30).json()

    items = st.session_state.get("queue_data") or []
    if not items:
        st.info("No items or not loaded — press Refresh")
    for item in items:
        with st.expander(f"{item.get('title', '?')} · E={item.get('E')} M={item.get('M')}"):
            st.write(item)
            eid = item["id"]
            detail = httpx.get(f"{API}/events/{eid}", timeout=30).json()
            st.markdown("**Claims**")
            for c in detail.get("claims") or []:
                score = c.get("score") or {}
                st.write(f"- {c.get('text', '')[:200]}… | R={score.get('R')} E={score.get('E')} M={score.get('M')}")
            reason = st.text_input(f"Reason for {eid}", key=f"reason_{eid}")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Approve", key=f"ok_{eid}"):
                    if len(reason.strip()) < 3:
                        st.warning("Reason required")
                    else:
                        resp = httpx.post(
                            f"{API}/events/{eid}/review",
                            json={"decision": "approve", "reason": reason, "operator_id": "op_demo"},
                            timeout=60,
                        )
                        st.json(resp.json())
            with col2:
                if st.button("Reject", key=f"no_{eid}"):
                    if len(reason.strip()) < 3:
                        st.warning("Reason required")
                    else:
                        resp = httpx.post(
                            f"{API}/events/{eid}/review",
                            json={"decision": "reject", "reason": reason, "operator_id": "op_demo"},
                            timeout=60,
                        )
                        st.json(resp.json())
            cp = detail.get("checkpoint")
            if cp:
                st.markdown(f"**Checkpoint:** `{cp.get('status')}` hash=`{cp.get('manifest_hash', '')[:16]}…`")
                if cp.get("explorer_url"):
                    st.markdown(f"[Solscan]({cp['explorer_url']})")

with tab_timeline:
    if st.button("Load published"):
        st.session_state["timeline"] = httpx.get(f"{API}/timeline", timeout=30).json()
    for ev in st.session_state.get("timeline") or []:
        st.markdown(f"### {ev.get('title')}")
        st.write(f"Places: {ev.get('places')} · v{ev.get('version')}")
        if ev.get("manifest_hash"):
            st.code(ev["manifest_hash"][:32] + "…")
        if ev.get("solana_explorer"):
            st.markdown(f"[On-chain checkpoint]({ev['solana_explorer']})")
        st.divider()
