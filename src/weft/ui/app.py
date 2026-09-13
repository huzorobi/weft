"""Weft graph UI (Streamlit).

A thin shell over the tested services. Flow: accept the terms once at first launch, then just
enter a seed and run — the engagement (auto id, client, stamped date, seed as scope) is created
for you. Below: the live graph (pyvis), an entity detail panel, a confidence filter, the report,
and the audit log. All data logic lives in ``weft.ui.runner``, ``weft.ui.graphview``, and
``weft.storage.meta``.

Run:  streamlit run src/weft/ui/app.py
"""
from __future__ import annotations

from datetime import date, datetime

import streamlit as st
import streamlit.components.v1 as components

from weft.compliance.engagement import ControllerRole, Engagement
from weft.config import load_settings
from weft.core.entity import EntityType
from weft.core.reasoner import OllamaReasoner
from weft.reporting import build_kml, build_report, has_geolocated_ips
from weft.storage.meta import EngagementRepository, MetaStore, SqlAuditStore
from weft.ui import consent
from weft.ui.graphview import build_vis_payload, render_html
from weft.ui.runner import execute_run

SEED_TYPES = [
    EntityType.DOMAIN, EntityType.EMAIL, EntityType.USERNAME, EntityType.NAME,
    EntityType.PERSON, EntityType.PHONE, EntityType.CRYPTO_ADDRESS, EntityType.CVE,
]
SEED_HINT = {
    EntityType.DOMAIN: "example.com", EntityType.EMAIL: "jane@example.com",
    EntityType.USERNAME: "janedoe", EntityType.NAME: "Jane Doe", EntityType.PERSON: "Jane Doe",
    EntityType.PHONE: "+44 20 7946 0000", EntityType.CRYPTO_ADDRESS: "0x… or 1A1z…",
    EntityType.CVE: "CVE-2021-44228",
}


@st.cache_resource
def _stores():
    settings = load_settings()
    meta = MetaStore(settings.database_url)
    return meta, EngagementRepository(meta), SqlAuditStore(meta)


def _sidebar_system() -> None:
    from weft.ui.health import all_live, service_status
    with st.sidebar:
        status = service_status()
        st.markdown(f"**{'🟢 All services live' if all_live(status) else '🟠 Some services down'}**")
        cols = st.columns(len(status))
        for col, (svc, ok) in zip(cols, status.items()):
            col.markdown(f"{'🟢' if ok else '🔴'} {svc}")
        if not all_live(status) and st.button("🔄 Restart services", use_container_width=True):
            from weft.ui.services import restart_services
            with st.spinner("Starting services (~30s while Neo4j boots)…"):
                ok, msg = restart_services()
            (st.success if ok else st.error)(msg)
            st.rerun()
        st.divider()
        with st.expander("⏻  Shut down Weft"):
            st.caption("Stops the stack (Neo4j, SearXNG, Tor) and this UI. Ollama is left running.")
            if st.button("Shut down now", type="primary", use_container_width=True):
                from weft.ui.shutdown import request_shutdown
                request_shutdown()
                st.success("✅ Weft is shutting down.")
                st.info("This tab will show a **connection error** shortly — that is expected (the UI "
                        "stopped). Close the tab.")
                st.stop()


def _terms_gate(audit_store) -> None:
    """First-launch terms & conditions. Blocks the app until accepted (once)."""
    st.title("Weft")
    st.subheader("Terms & conditions")
    st.markdown(consent.TERMS_TEXT)
    st.divider()
    operator = st.text_input("Your name (recorded with the acceptance)", value="operator")
    agree = st.checkbox("I have read and accept these terms, and take responsibility as the operator.")
    if st.button("Accept and continue", type="primary", disabled=not agree):
        rec = consent.record_acceptance(operator)
        try:
            audit_store.record(action="terms_accept", engagement_id="-", operator=rec["operator"],
                               detail={"version": rec["version"], "accepted_at": rec["accepted_at"]})
        except Exception:
            pass
        st.rerun()


def _auto_engagement(client: str, seed_type: EntityType, seed_value: str) -> Engagement:
    """Create a minimal engagement: auto id, client, stamped date; the seed is its scope."""
    today = date.today()
    return Engagement(
        id=f"WEFT-{datetime.now():%Y%m%d-%H%M%S}",
        client=(client.strip() or "Ad-hoc"),
        scope_ref="operator accepted terms at launch",
        lawful_basis="operator-asserted (terms accepted)",
        authorised_targets=[seed_value.strip()],
        start_date=today, end_date=today,
        controller_role=ControllerRole.CONTROLLER,
        verified_domains=({seed_value.strip(): "operator-asserted"} if seed_type is EntityType.DOMAIN else {}),
    )


def main() -> None:
    st.set_page_config(page_title="Weft — OSINT recon", layout="wide")
    meta, repo, audit_store = _stores()
    _sidebar_system()

    # First launch: accept the terms once.
    if not consent.is_accepted():
        _terms_gate(audit_store)
        return

    rec = consent.accepted_record() or {}
    st.title("Weft")
    st.caption(f"Free-source OSINT recon · passive, public sources only · terms accepted by "
               f"{rec.get('operator', 'operator')} on {str(rec.get('accepted_at', ''))[:10]}.")

    # --- the search form is always visible ---
    st.subheader("New search")
    c1, c2, c3 = st.columns([1, 1, 2])
    client = c1.text_input("Client / case", value="Ad-hoc", help="A label for this investigation.")
    seed_type = c2.selectbox("Seed type", SEED_TYPES, format_func=lambda t: t.value)
    seed_value = c3.text_input("Seed value", placeholder=SEED_HINT.get(seed_type, ""),
                               help="What to investigate: a domain, email, username, name, phone, "
                                    "crypto address, or CVE.")

    o1, o2, o3, o4 = st.columns(4)
    depth = o1.slider("Depth", 1, 3, 2, help="How many hops to expand from the seed.")
    allow_tos = o2.checkbox("Enumeration sources", value=True,
                            help="maigret/sherlock/holehe/phoneinfoga — public enumeration, logged.")
    hunt = o3.checkbox("🤖 AI hunter", value=False,
                       help="The local model picks high-value pivots from a validated action menu.")
    dark_web = o4.checkbox("🌐 Dark-web", value=False,
                           help="Passive Ahmia index search over Tor (opt-in, logged). Search-only.")
    run = st.button("Run search", type="primary", disabled=not seed_value.strip(), use_container_width=True)

    if run:
        eng = _auto_engagement(client, seed_type, seed_value)
        repo.save(eng)
        settings = load_settings()
        reasoner = OllamaReasoner(settings.reasoner_model, base_url=settings.ollama_url) if hunt else None
        with st.spinner("Collecting from open sources…"):
            out = execute_run(
                engagement=eng, seed_type=seed_type, seed_value=seed_value.strip(),
                operator=rec.get("operator", "operator"), depth_cap=depth, allow_tos_risk=allow_tos,
                accepted=True, audit_store=audit_store, hunt=hunt, reasoner=reasoner,
                allow_dark_web=dark_web,
            )
        st.session_state["graph"] = out.graph
        st.session_state["message"] = out.message
        st.session_state["engagement"] = eng
        st.session_state["seed_value"] = seed_value.strip()

    # --- results ---
    if "message" in st.session_state:
        st.success(st.session_state["message"])
    graph = st.session_state.get("graph")
    if graph and graph.nodes:
        st.divider()
        left, right = st.columns([3, 2])
        with left:
            st.subheader("Graph")
            min_conf = st.slider("Minimum confidence", 0.0, 1.0, 0.0, 0.05)
            payload = build_vis_payload(graph, min_confidence=min_conf)
            st.caption(f"{len(payload['nodes'])} nodes / {len(payload['edges'])} edges")
            components.html(render_html(payload), height=560)
        with right:
            st.subheader("Entity detail")
            keys = sorted(n["id"] for n in payload["nodes"])
            if keys:
                chosen = st.selectbox("Entity", keys)
                node = graph.nodes[chosen]
                st.json({"type": node.type.value, "value": node.value,
                         "confidence": node.confidence, "metadata": node.metadata})

        # --- report ---
        st.divider()
        st.subheader("Report")
        settings = load_settings()
        eng = st.session_state.get("engagement")
        col_a, col_b = st.columns([3, 1])
        model = col_a.text_input("Local model for the AI narrative (Ollama; clear to skip)",
                                 value=settings.reasoner_model)
        if col_b.button("Generate report", use_container_width=True):
            reasoner = OllamaReasoner(model, base_url=settings.ollama_url) if model.strip() else None
            st.session_state["report_md"] = build_report(
                eng, graph, reasoner=reasoner, seeds=[st.session_state.get("seed_value")])
        if "report_md" in st.session_state:
            st.download_button("⬇ report.md", st.session_state["report_md"],
                               file_name=f"{eng.id}-report.md", mime="text/markdown")
            if has_geolocated_ips(graph):
                st.download_button("⬇ map.kml (geolocated IPs)", build_kml(graph),
                                   file_name=f"{eng.id}-map.kml",
                                   mime="application/vnd.google-earth.kml+xml")
            st.markdown(st.session_state["report_md"])

    # --- audit log ---
    st.divider()
    with st.expander("Audit log"):
        events = list(audit_store.all())[-200:]
        st.dataframe(
            [{"time": e.ts, "action": e.action, "engagement": e.engagement_id,
              "operator": e.operator, "module": e.source_module, "entity": e.entity_key,
              "detail": e.detail} for e in reversed(events)],
            use_container_width=True, hide_index=True,
        )


if __name__ == "__main__":
    main()
