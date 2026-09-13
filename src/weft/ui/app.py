"""Weft graph UI (Streamlit).

A thin shell over the tested services: engagement selection/creation, the legal
acceptance gate, seed input and run config, the live graph (pyvis), an entity detail
panel, a confidence filter, and the audit-log viewer. All data logic lives in
``weft.ui.runner``, ``weft.ui.graphview``, and ``weft.storage.meta``.

Run:  streamlit run src/weft/ui/app.py
"""
from __future__ import annotations

from datetime import date

import streamlit as st
import streamlit.components.v1 as components

from weft.compliance.engagement import LEGAL_STATEMENT, ControllerRole, Engagement
from weft.config import load_settings
from weft.core.entity import EntityType
from weft.core.reasoner import OllamaReasoner
from weft.reporting import build_kml, build_report, has_geolocated_ips
from weft.storage.meta import EngagementRepository, MetaStore, SqlAuditStore
from weft.ui.graphview import build_vis_payload, render_html
from weft.ui.runner import execute_run

SEED_TYPES = [
    EntityType.DOMAIN, EntityType.PHONE, EntityType.EMAIL,
    EntityType.USERNAME, EntityType.NAME, EntityType.PERSON,
]


@st.cache_resource
def _stores():
    settings = load_settings()
    meta = MetaStore(settings.database_url)
    return meta, EngagementRepository(meta), SqlAuditStore(meta)


def main() -> None:
    st.set_page_config(page_title="Weft — OSINT recon", layout="wide")
    meta, repo, audit_store = _stores()

    st.title("Weft")
    st.caption("Free-source OSINT reconnaissance. Authorised engagements only.")

    # --- sidebar: engagement selection + creation ---
    with st.sidebar:
        st.header("Engagement")
        engagements = repo.list()
        options = {f"{e.id} — {e.client}": e for e in engagements}
        selected = None
        if options:
            label = st.selectbox("Active engagement", list(options))
            selected = options[label]
        else:
            st.info("No engagements yet. Create one below.")

        with st.expander("New engagement"):
            with st.form("new_engagement"):
                eid = st.text_input("ID", placeholder="ENG-2026-001")
                client = st.text_input("Client")
                scope_ref = st.text_input("Signed scope reference")
                lawful_basis = st.text_input("Lawful basis", value="legitimate interest")
                targets = st.text_area("Authorised targets (one per line)")
                dpia = st.text_input("DPIA reference")
                lia = st.text_input("LIA reference")
                role = st.selectbox("Role", [r.value for r in ControllerRole])
                start = st.date_input("Start", value=date.today())
                end = st.date_input("End")
                verified = st.text_area("Verified-control domains (one per line)",
                                        help="Domains the client has proven they control (required for breach lookups).")
                if st.form_submit_button("Save engagement") and eid and client:
                    repo.save(Engagement(
                        id=eid, client=client, scope_ref=scope_ref, lawful_basis=lawful_basis,
                        authorised_targets=[t.strip() for t in targets.splitlines() if t.strip()],
                        start_date=start, end_date=end, dpia_ref=dpia or None, lia_ref=lia or None,
                        controller_role=ControllerRole(role),
                        verified_domains={d.strip(): "operator-asserted" for d in verified.splitlines() if d.strip()},
                    ))
                    st.success(f"Saved {eid}. Reselect it above.")
                    st.rerun()

    if selected is None:
        st.stop()

    # --- run configuration ---
    left, right = st.columns([2, 3])
    with left:
        st.subheader("Run")
        st.write(f"**Scope:** {', '.join(selected.authorised_targets) or '(none)'}")
        seed_type = st.selectbox("Seed type", SEED_TYPES, format_func=lambda t: t.value)
        seed_value = st.text_input("Seed value")
        depth = st.slider("Depth", 1, 3, 2)
        allow_tos = st.checkbox("Enable enumeration sources — maigret/sherlock/holehe/phoneinfoga (ToS-flagged, logged)",
                                value=True,
                                help="On by default for maximum collection via public enumeration. Every use is "
                                     "logged. Uncheck to stay strictly on official/free-API sources.")
        override_reason = st.text_input("Out-of-scope override reason (optional, logged)")

        st.markdown("**Responsibility statement**")
        st.caption(LEGAL_STATEMENT)
        accepted = st.checkbox("I accept, as the operator, and take responsibility for this run.")

        run = st.button("Run expansion", type="primary", disabled=not seed_value)

    if run:
        out = execute_run(
            engagement=selected, seed_type=seed_type, seed_value=seed_value, operator="operator",
            depth_cap=depth, allow_tos_risk=allow_tos, accepted=accepted,
            audit_store=audit_store, override_reason=override_reason or None,
        )
        st.session_state["graph"] = out.graph
        st.session_state["message"] = out.message

    with right:
        st.subheader("Graph")
        if "message" in st.session_state:
            st.info(st.session_state["message"])
        graph = st.session_state.get("graph")
        if graph and graph.nodes:
            min_conf = st.slider("Minimum confidence", 0.0, 1.0, 0.0, 0.05)
            payload = build_vis_payload(graph, min_confidence=min_conf)
            st.caption(f"{len(payload['nodes'])} nodes / {len(payload['edges'])} edges")
            components.html(render_html(payload), height=620)

            st.subheader("Entity detail")
            keys = sorted(n["id"] for n in payload["nodes"])
            if keys:
                chosen = st.selectbox("Entity", keys)
                node = graph.nodes[chosen]
                st.json({"type": node.type.value, "value": node.value,
                         "confidence": node.confidence, "metadata": node.metadata})

    # --- report (deterministic + optional local-AI narrative) ---
    st.divider()
    st.subheader("Report")
    graph = st.session_state.get("graph")
    if graph and graph.nodes:
        settings = load_settings()
        col_a, col_b = st.columns([3, 1])
        model = col_a.text_input("Local model for the narrative (Ollama, optional)",
                                 value=settings.reasoner_model,
                                 help="Leave as-is for a small local model, or clear to skip AI narration.")
        if col_b.button("Generate report"):
            reasoner = OllamaReasoner(model, base_url=settings.ollama_url) if model.strip() else None
            md = build_report(selected, graph, reasoner=reasoner,
                              seeds=[seed_value] if seed_value else None)
            st.session_state["report_md"] = md
        if "report_md" in st.session_state:
            st.download_button("Download report.md", st.session_state["report_md"],
                               file_name=f"{selected.id}-report.md", mime="text/markdown")
            if has_geolocated_ips(graph):
                st.download_button("Download KML map (geolocated IPs)", build_kml(graph),
                                   file_name=f"{selected.id}-map.kml",
                                   mime="application/vnd.google-earth.kml+xml")
            st.markdown(st.session_state["report_md"])
    else:
        st.caption("Run an expansion first, then generate a report.")

    # --- audit viewer ---
    st.divider()
    st.subheader("Audit log")
    events = list(audit_store.all())[-200:]
    st.dataframe(
        [{"time": e.ts, "action": e.action, "engagement": e.engagement_id,
          "operator": e.operator, "module": e.source_module, "entity": e.entity_key,
          "detail": e.detail} for e in reversed(events)],
        use_container_width=True, hide_index=True,
    )


if __name__ == "__main__":
    main()
