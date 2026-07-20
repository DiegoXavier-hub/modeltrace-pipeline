#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Rodar:
    streamlit run streamlit_app.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crud_pipeline import (  # noqa: E402
    MAIN_COLLECTIONS,
    PROJECT_DEFS,
    ModelTraceRepository,
    RK,
    feature_value,
    gen_id,
    iso,
    score_band,
)
from neo4j import GraphDatabase  # noqa: E402
from pymongo import DESCENDING  # noqa: E402

# ---------------------------------------------------------------------------
# Setup + tema
# ---------------------------------------------------------------------------

st.set_page_config(page_title="ModelTrace — Monitoramento de Modelos", layout="wide")

# Design system alinhado a visualizacao do grafo (dark + dourado). Um unico tema
# premium para todo o app: tipografia Inter/IBM Plex Mono, superficies quentes,
# accent dourado, menu lateral como navegacao real (nao input) e botoes sem icones.
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap');

      :root{
        --mt-bg:#0a0806; --mt-bg2:#120d09; --mt-panel:#181109; --mt-panel2:#100b06;
        --mt-stroke:#3a2c17; --mt-strokeSoft:#241a0f; --mt-ink:#ecdfc2; --mt-muted:#9c8a6a;
        --mt-gold:#d9ad3f; --mt-gold2:#f2c766; --mt-jade:#4a9c8c; --mt-ruby:#b3453f;
      }

      /* ---- base ---- */
      .stApp{
        background:
          radial-gradient(1100px 700px at 18% 12%, #1c140a 0%, transparent 60%),
          radial-gradient(900px 900px at 88% 88%, #150f08 0%, transparent 55%),
          var(--mt-bg);
        color:var(--mt-ink);
        font-family:'Inter',-apple-system,Segoe UI,sans-serif;
      }
      .block-container{padding-top:2.4rem;max-width:1400px}
      h1,h2,h3,h4{color:var(--mt-ink);font-family:'Inter',sans-serif;font-weight:700;letter-spacing:-.01em}
      h1{font-size:1.8rem;font-weight:800}
      h2{font-size:1.25rem;color:var(--mt-gold2)}
      h3{font-size:1.05rem}
      a{color:var(--mt-gold2)}
      code,pre,.mono,[data-testid="stCode"]{font-family:'IBM Plex Mono',Consolas,monospace}
      hr{border-color:var(--mt-strokeSoft)}
      [data-testid="stCaptionContainer"]{color:var(--mt-muted)}

      /* ---- sidebar ---- */
      section[data-testid="stSidebar"]{background:linear-gradient(180deg,#181109,#100b06);
        border-right:1px solid var(--mt-stroke)}
      section[data-testid="stSidebar"] .block-container{padding-top:1.4rem}
      .mt-brand{font-weight:800;font-size:1.35rem;color:var(--mt-gold2);letter-spacing:.2px;line-height:1}
      .mt-brand-sub{color:var(--mt-muted);font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;
        margin-top:5px;margin-bottom:2px}
      .mt-navlabel{color:var(--mt-muted);font-size:.68rem;letter-spacing:.16em;text-transform:uppercase;
        margin:14px 2px 6px}

      /* ---- nav (radio -> menu de navegacao, sem cara de input) ---- */
      section[data-testid="stSidebar"] div[role="radiogroup"]{gap:3px}
      section[data-testid="stSidebar"] div[role="radiogroup"] > label{
        display:flex;align-items:center;width:100%;margin:0;padding:9px 13px;border-radius:9px;
        cursor:pointer;border:1px solid transparent;color:var(--mt-muted);
        font-size:.92rem;font-weight:500;transition:background .12s,color .12s,border-color .12s}
      section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover{
        background:#1c140b;color:var(--mt-ink);border-color:var(--mt-strokeSoft)}
      /* esconde a bolinha do radio */
      section[data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-child{display:none}
      /* estado selecionado */
      section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked){
        background:linear-gradient(90deg,#2a1f0d,#1b140b);color:var(--mt-gold2);
        border-color:var(--mt-stroke);font-weight:600;box-shadow:inset 2px 0 0 0 var(--mt-gold)}

      /* ---- metrics como cartoes ---- */
      div[data-testid="stMetric"]{background:var(--mt-panel);border:1px solid var(--mt-stroke);
        border-radius:12px;padding:14px 16px}
      div[data-testid="stMetricLabel"] p{color:var(--mt-muted);font-size:.78rem;
        text-transform:uppercase;letter-spacing:.06em}
      div[data-testid="stMetricValue"]{color:var(--mt-gold2);font-weight:700}
      section[data-testid="stSidebar"] div[data-testid="stMetric"]{background:var(--mt-panel2)}

      /* ---- botoes (sem icones, accent dourado) ---- */
      .stButton>button, .stDownloadButton>button, div[data-testid="stFormSubmitButton"]>button{
        background:var(--mt-panel);color:var(--mt-ink);border:1px solid var(--mt-stroke);
        border-radius:9px;padding:8px 16px;font-weight:600;font-family:'Inter',sans-serif;
        transition:border-color .12s,background .12s,color .12s}
      .stButton>button:hover, .stDownloadButton>button:hover{
        border-color:var(--mt-gold);color:var(--mt-gold2);background:#1c140b}
      .stButton>button[kind="primary"], div[data-testid="stFormSubmitButton"]>button[kind="primary"]{
        background:linear-gradient(180deg,var(--mt-gold2),var(--mt-gold));color:#231a08;
        border:1px solid var(--mt-gold);box-shadow:0 4px 16px -6px #d9ad3f88}
      .stButton>button[kind="primary"]:hover{filter:brightness(1.06);color:#231a08}

      /* ---- inputs / tabs / tabelas ---- */
      .stSelectbox div[data-baseweb="select"]>div, .stTextInput input, .stNumberInput input,
      .stTextArea textarea{background:var(--mt-panel2);border-color:var(--mt-stroke);color:var(--mt-ink)}
      .stSelectbox label, .stTextInput label, .stNumberInput label, .stSlider label,
      .stRadio label{color:var(--mt-muted)}
      div[data-baseweb="tab-list"]{border-bottom:1px solid var(--mt-strokeSoft);gap:4px}
      button[data-baseweb="tab"]{color:var(--mt-muted)}
      button[data-baseweb="tab"][aria-selected="true"]{color:var(--mt-gold2)}
      div[data-baseweb="tab-highlight"]{background:var(--mt-gold)!important}
      .stSlider [data-baseweb="slider"] div[role="slider"]{background:var(--mt-gold)}
      [data-testid="stDataFrame"]{border:1px solid var(--mt-stroke);border-radius:12px}
      [data-testid="stJson"]{background:var(--mt-panel2);border:1px solid var(--mt-strokeSoft);
        border-radius:10px;padding:8px 10px}

      /* ---- helpers ---- */
      .mt-badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600}
      .mt-card{background:var(--mt-panel);border:1px solid var(--mt-stroke);border-radius:12px;
        padding:16px 18px;margin-bottom:10px}
      .mt-muted{color:var(--mt-muted);font-size:13px}

      /* ---- pagina de status do servidor ---- */
      .mt-status-banner{padding:13px 20px;border-radius:11px;font-weight:700;margin:4px 0 22px;
        font-size:.95rem;letter-spacing:.02em}
      .mt-status-banner.ok{background:#22c55e15;border:1px solid #22c55e4d;color:#4ade80}
      .mt-status-banner.down{background:#ef444415;border:1px solid #ef44444d;color:#f87171}
      .mt-status-card{background:var(--mt-panel);border:1px solid var(--mt-stroke);border-radius:14px;
        padding:22px 18px;text-align:center;height:100%}
      .mt-status-dot{width:13px;height:13px;border-radius:50%;margin:0 auto 12px}
      .mt-status-name{font-size:1.1rem;font-weight:800;color:var(--mt-ink);margin-bottom:8px}
      .mt-status-badge{display:inline-block;padding:3px 13px;border-radius:999px;font-size:.68rem;
        font-weight:700;text-transform:uppercase;letter-spacing:.08em;border:1px solid;margin-bottom:12px}
      .mt-status-desc{color:var(--mt-muted);font-size:.78rem;margin-bottom:10px;min-height:2.4em;
        line-height:1.35}
      .mt-status-detail{font-family:'IBM Plex Mono',monospace;font-size:.8rem;color:var(--mt-ink);
        margin-bottom:5px;word-break:break-word}
      .mt-status-latency{font-family:'IBM Plex Mono',monospace;font-size:.7rem;color:var(--mt-muted)}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_repo() -> ModelTraceRepository:
    repo = ModelTraceRepository()
    repo.connect()
    return repo


repo = get_repo()
db = repo.db


def project_options() -> dict[str, str]:
    return {p["name"]: p["_id"] for p in db.projects.find({}, {"name": 1}).sort("name", 1)}


def models_for_project(project_id: str) -> dict[str, dict]:
    return {m["name"]: m for m in db.models.find({"project_id": project_id})}


def badge(text: str, color: str) -> str:
    return f'<span class="mt-badge" style="background:{color}22;color:{color};border:1px solid {color}55">{text}</span>'


BAND_COLOR = {"low": "#22c55e", "medium": "#eab308", "high": "#f97316", "critical": "#ef4444"}

# Nomes amigaveis para os conjuntos de dados (esconde os nomes tecnicos das colecoes).
COLLECTION_LABELS = {
    "organizations": "Organizações", "users": "Usuários", "projects": "Projetos",
    "models": "Modelos", "model_versions": "Versões de modelo", "predictions": "Predições",
    "metrics_snapshots": "Métricas", "entity_notes": "Notas de entidade",
    "audit_events": "Eventos de auditoria",
}


def record_table(doc: dict) -> None:
    """Mostra um registro como tabela Campo/Valor (leitura de produto, sem JSON cru)."""
    flat = pd.json_normalize(doc, sep=" · ").iloc[0]
    st.dataframe(
        pd.DataFrame({"Campo": flat.index, "Valor": [str(v) for v in flat.values]}),
        use_container_width=True, hide_index=True,
    )

# ---------------------------------------------------------------------------
# Sidebar / navegacao
# ---------------------------------------------------------------------------

st.sidebar.markdown(
    '<div class="mt-brand">ModelTrace</div>'
    '<div class="mt-brand-sub">Monitoramento de Modelos</div>'
    '<div class="mt-muted" style="font-size:12px">Ambiente de demonstração</div>',
    unsafe_allow_html=True,
)

total_preds = db.predictions.count_documents({})
if total_preds == 0:
    st.sidebar.warning("Nenhum dado carregado ainda.")
    if st.sidebar.button("Carregar dados de demonstração", type="primary"):
        with st.spinner("Preparando os dados de demonstração..."):
            repo.create_collections_and_indexes(drop=True)
            repo.redis_reset_and_reserve()
            ctx = repo.seed_reference_data()
            repo.seed_predictions(ctx, per_model=260)
            repo.seed_entity_notes(per_project=6)
        st.rerun()
    st.stop()

PAGES = ["Visão geral", "Nova decisão", "Predições", "Feedback", "Retenção",
         "Desempenho", "Tempo real", "Casos similares", "Base de dados",
         "Status do servidor"]
st.sidebar.markdown('<div class="mt-navlabel">Navegação</div>', unsafe_allow_html=True)
page = st.sidebar.radio("Telas", PAGES, label_visibility="collapsed")

st.sidebar.divider()
st.sidebar.metric("Predições monitoradas", f"{total_preds:,}")
st.sidebar.metric("Modelos", db.models.count_documents({}))


# ===========================================================================
# DASHBOARD
# ===========================================================================
if page == "Visão geral":
    st.title("Visão geral")
    st.caption("Indicadores de operação e desempenho dos modelos em produção.")

    counts = repo.collection_counts()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Predicoes", f"{counts['predictions']:,}")
    c2.metric("Modelos", counts["models"])
    c3.metric("Projetos", counts["projects"])
    unique_entities = sum(
        repo.r.pfcount(k) for k in repo.r.scan_iter(f"{RK}:hll:entities:*")
    ) if any(True for _ in repo.r.scan_iter(f"{RK}:hll:entities:*")) else 0
    c4.metric("Entidades únicas", f"~{unique_entities:,}")

    st.subheader("Desempenho dos modelos")
    board = list(db.metrics_snapshots.find().sort("f1", DESCENDING))
    if not board:
        board = repo.agg_model_leaderboard()
    df = pd.DataFrame([{
        "modelo": r["model_name"], "versao": r["version"],
        "modelo_versao": f"{r['model_name']} [{r['version']}]", "F1": r["f1"],
        "precision": r["precision"], "recall": r["recall"],
        "n_feedback": r["n_with_feedback"],
        "tp": r["confusion"]["tp"], "fp": r["confusion"]["fp"],
        "tn": r["confusion"]["tn"], "fn": r["confusion"]["fn"],
    } for r in board])
    st.dataframe(df.drop(columns=["modelo_versao"]), use_container_width=True, hide_index=True)
    st.bar_chart(df.set_index("modelo_versao")["F1"], horizontal=True)


# ===========================================================================
# INSERT
# ===========================================================================
elif page == "Nova decisão":
    st.title("Nova decisão")
    st.caption("Registre uma nova decisão de modelo. Requisições duplicadas são ignoradas automaticamente.")

    popts = project_options()
    pname = st.selectbox("Projeto", list(popts.keys()))
    project_id = popts[pname]
    pdef = next(p for p in PROJECT_DEFS if p["id"] == project_id)
    models = models_for_project(project_id)
    mname = st.selectbox("Modelo", list(models.keys()))
    model = models[mname]

    st.markdown("**Features do modelo** (campos dinamicos por contrato):")
    feats: dict = {}
    cols = st.columns(3)
    for i, f in enumerate(model["expected_features"]):
        with cols[i % 3]:
            if f["type"] == "categorical":
                from crud_pipeline import CATEGORICALS
                feats[f["name"]] = st.selectbox(f["name"], CATEGORICALS.get(f["name"], ["A", "B"]))
            else:
                feats[f["name"]] = st.number_input(f["name"], value=float(feature_value(f["name"])
                                                    if not isinstance(feature_value(f["name"]), str) else 0.0))

    colA, colB = st.columns(2)
    score = colA.slider("Score do modelo", 0.0, 1.0, 0.72, 0.01)
    req_id = colB.text_input("Identificador da requisição", value="manual_ui_0001")
    threshold = model["default_threshold"]
    above = score >= threshold
    label = model["labels"]["positive"] if above else model["labels"]["negative"]

    st.markdown(
        f"Decisao prevista: {badge(label, '#d9ad3f')} &nbsp; "
        f"banda {badge(score_band(score), BAND_COLOR[score_band(score)])} &nbsp; "
        f"limiar={threshold}", unsafe_allow_html=True)

    if st.button("Registrar decisão", type="primary"):
        import hashlib
        raw_entity = f"{project_id}-ui-{req_id}"
        ent_hash = hashlib.sha256(raw_entity.encode()).hexdigest()
        doc = {
            "_id": gen_id("pred", model["_id"], req_id),
            "org_id": "org_ufu_gi_ops", "project_id": project_id, "model_id": model["_id"],
            "model_version_id": model["production_version_id"], "model_version": "v2",
            "entity": {"id": f"entity_{ent_hash[:12]}", "id_hash": ent_hash,
                       "type": pdef["entity_type"], "display_name_masked": "[protected]"},
            "features": feats,
            "prediction": {"label": label, "score": round(score, 4), "threshold": threshold,
                           "above_threshold": above, "score_band": score_band(score)},
            "explanations": [{"feature": k, "value": v, "impact": round(0.1, 4),
                              "direction": "risk_up" if above else "risk_down", "rank": i + 1}
                             for i, (k, v) in enumerate(list(feats.items())[:3])],
            "decision": {"action": "human_review" if above else "auto_pass",
                         "status": "triggered" if above else "skipped",
                         "reason": "score_above_threshold" if above else "below_threshold"},
            "feedback": {"available": False},
            "flags": {"is_critical": score > 0.85, "reviewed_by": None},
            "metadata": {"source_system": "streamlit_ui", "environment": "prototype",
                         "request_id": req_id, "algorithm": model.get("slug")},
            "created_at": iso(datetime.now(timezone.utc)),
        }
        result = repo.insert_prediction(doc)
        if result["status"] == "inserted":
            st.success(f"Decisão registrada: {result['prediction_id']}")
            record_table(doc)
        else:
            st.warning(f"Requisição '{req_id}' já registrada anteriormente — nada foi duplicado.")


# ===========================================================================
# FIND
# ===========================================================================
elif page == "Predições":
    st.title("Predições")
    st.caption("Busque e filtre as decisões registradas pelos modelos.")

    popts = {"(todos)": None, **project_options()}
    c1, c2, c3, c4 = st.columns(4)
    pname = c1.selectbox("Projeto", list(popts.keys()))
    band = c2.selectbox("Banda de score", ["(todas)", "low", "medium", "high", "critical"])
    fb = c3.selectbox("Feedback", ["(todos)", "com feedback", "sem feedback"])
    min_score = c4.slider("Score minimo", 0.0, 1.0, 0.0, 0.05)

    flt: dict = {"prediction.score": {"$gte": min_score}}
    if popts[pname]:
        flt["project_id"] = popts[pname]
    if band != "(todas)":
        flt["prediction.score_band"] = band
    if fb == "com feedback":
        flt["feedback.available"] = True
    elif fb == "sem feedback":
        flt["feedback.available"] = {"$ne": True}

    rows = repo.find_predictions(flt, sort=[("prediction.score", DESCENDING)], limit=50)
    if rows:
        df = pd.json_normalize(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(f"{len(rows)} resultado(s) — total no filtro: "
                   f"{db.predictions.count_documents(flt):,}")
        ids = [r["_id"] for r in rows]
        sel = st.selectbox("Ver detalhes da decisão", ids)
        if sel:
            record_table(repo.find_prediction(sel))
    else:
        st.info("Nenhuma decisão para esse filtro.")


# ===========================================================================
# UPDATE
# ===========================================================================
elif page == "Feedback":
    st.title("Feedback")
    st.caption("Registre o resultado real observado e escale decisões críticas para revisão.")

    tab1, tab2 = st.tabs(["Registrar resultado observado", "Escalar decisões críticas"])

    with tab1:
        pending = list(db.predictions.find(
            {"feedback.available": {"$ne": True}}, {"_id": 1, "prediction.score": 1, "prediction.label": 1}
        ).sort("prediction.score", DESCENDING).limit(30))
        if pending:
            opt = {f"{p['_id']} · score={p['prediction']['score']} · {p['prediction']['label']}": p["_id"]
                   for p in pending}
            choice = st.selectbox("Predicao sem feedback", list(opt.keys()))
            observed = st.radio("Resultado real observado", [1, 0],
                                format_func=lambda x: "Positivo (evento ocorreu)" if x else "Negativo")
            if st.button("Salvar feedback", type="primary"):
                repo.update_feedback(opt[choice], int(observed))
                doc = repo.find_prediction(opt[choice])
                st.success(f"Resultado salvo · classificação: "
                           f"{doc['feedback']['classification_result']}")
                record_table(doc["feedback"])
        else:
            st.info("Todas as decisões já têm feedback.")

    with tab2:
        popts = project_options()
        pname = st.selectbox("Projeto", list(popts.keys()))
        thr = st.slider("Escalar predicoes com score >=", 0.5, 1.0, 0.85, 0.01)
        n_target = db.predictions.count_documents(
            {"project_id": popts[pname], "prediction.score": {"$gte": thr}})
        st.caption(f"{n_target} decisões seriam afetadas.")
        if st.button("Escalar decisões críticas"):
            n = repo.bulk_flag_critical(popts[pname], thr)
            st.success(f"{n} decisões escaladas para revisão.")


# ===========================================================================
# DELETE
# ===========================================================================
elif page == "Retenção":
    st.title("Retenção")
    st.caption("Remova decisões individualmente ou faça o expurgo dos dados de demonstração.")

    tab1, tab2 = st.tabs(["Remover uma decisão", "Expurgo de dados de demonstração"])
    with tab1:
        recent = list(db.predictions.find({}, {"_id": 1, "prediction.score": 1})
                      .sort("created_at", DESCENDING).limit(30))
        opt = {f"{p['_id']} · score={p['prediction']['score']}": p["_id"] for p in recent}
        choice = st.selectbox("Decisão", list(opt.keys()))
        if st.button("Remover decisão", type="primary"):
            st.success(f"Removida: {repo.delete_prediction(opt[choice])}")

    with tab2:
        st.markdown("Remover as decisões **criadas nesta demonstração**:")
        n = db.predictions.count_documents({"metadata.source_system": "streamlit_ui"})
        st.caption(f"{n} decisões de demonstração no ambiente.")
        if st.button("Expurgar decisões de demonstração"):
            removed = repo.delete_predictions({"metadata.source_system": "streamlit_ui"})
            st.success(f"{removed} decisão(ões) removida(s).")


# ===========================================================================
# AGGREGATIONS
# ===========================================================================
elif page == "Desempenho":
    st.title("Desempenho")
    st.caption("Rankings e análises de desempenho e risco dos modelos.")

    st.subheader("Ranking de modelos")
    if st.button("Atualizar ranking", type="primary"):
        board = repo.agg_model_leaderboard()
        st.dataframe(pd.DataFrame([{
            "modelo": r["model_name"], "versao": r["version"], "F1": r["f1"],
            "precision": r["precision"], "recall": r["recall"], "n": r["n_with_feedback"],
            **r["confusion"]} for r in board]), use_container_width=True, hide_index=True)
        st.success("Ranking atualizado.")

    st.subheader("Fatores de risco")
    popts = project_options()
    pname = st.selectbox("Projeto para analisar", list(popts.keys()))
    if st.button("Analisar fatores de risco", type="primary"):
        res = repo.agg_feature_drivers(popts[pname])
        st.write("Universo de risco alto:", res["universe"])
        st.markdown("**Principais fatores que dirigem o risco:**")
        st.dataframe(pd.DataFrame(res["drivers"]), use_container_width=True, hide_index=True)
        st.markdown("**Amostra auditável de casos:**")
        st.dataframe(pd.DataFrame(res["audit_sample"]), use_container_width=True, hide_index=True)


# ===========================================================================
# REDIS
# ===========================================================================
elif page == "Tempo real":
    st.title("Tempo real")
    st.caption("Métricas operacionais atualizadas continuamente à medida que as decisões chegam.")
    dash = repo.redis_dashboard()

    st.subheader("Métricas operacionais")
    cc = st.columns(2)
    with cc[0]:
        st.markdown("**Contadores por modelo**")
        st.json(dash["common"]["hash_counters_by_model"])
        st.markdown("**Últimas decisões**")
        st.json(dash["common"]["list_recent_stream"])
    with cc[1]:
        st.markdown("**Ranking de risco por projeto**")
        st.json(dash["common"]["sorted_set_top_risk"])
        st.markdown("**Cache ativo**")
        st.json(dash["common"]["string_cache_keys"])
        st.markdown("**Limite de requisições (5 por 60s)**")
        if st.button("Simular 7 chamadas de API"):
            st.write([repo.redis_rate_limit("mt_live_ui", limit=5) for _ in range(7)])

    st.divider()
    st.subheader("Estimativas rápidas")
    pc = st.columns(2)
    with pc[0]:
        st.markdown("**Entidades únicas (aprox.)**")
        st.json(dash["probabilistic"]["hyperloglog_unique_entities"])
        st.markdown("**Requisições já vistas**")
        st.json(dash["probabilistic"]["bloom_seen_requests"])
        rq = st.text_input("Testar um identificador de requisição", "seed_x")
        if rq:
            exists = repo.r.execute_command("BF.EXISTS", f"{RK}:seen_requests", rq)
            st.write("Já vista:", bool(exists))
    with pc[1]:
        st.markdown("**Frequência das entidades mais avaliadas**")
        st.json(dash["probabilistic"]["count_min_freq_of_top_entities"])
        st.markdown("**Entidades mais avaliadas**")
        st.json(dash["probabilistic"]["topk_heavy_hitters"])


# ===========================================================================
# GRAFO DE CONHECIMENTO (Neo4j + GDS)
# ===========================================================================
elif page == "Casos similares":
    st.title("Casos similares")
    st.caption("Explore casos parecidos, agrupamentos de padrões de risco e as "
               "entidades mais influentes da rede de decisões.")

    graph_json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "graph_export.json")
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grafo.html")

    if not os.path.exists(graph_json_path) or not os.path.exists(html_path):
        st.warning("O grafo ainda não foi gerado neste ambiente.")
        st.caption("Gere-o rodando `graph_pipeline.py` com o Neo4j ativo.")
    else:
        with open(graph_json_path, "r", encoding="utf-8") as f:
            gjson = json.load(f)
        stats = gjson.get("stats", {})
        mcols = st.columns(5)
        mcols[0].metric("Nós", f"{stats.get('nodes', 0):,}")
        mcols[1].metric("Arestas", f"{stats.get('edges', 0):,}")
        mcols[2].metric("Comunidades", stats.get("communities", "—"))
        mcols[3].metric("Pares similares", stats.get("similarity_pairs_written", "—"))
        mcols[4].metric("Iterações do cálculo", stats.get("pagerank_iterations", "—"))

        with open(html_path, "r", encoding="utf-8") as f:
            st.components.v1.html(f.read(), height=760, scrolling=False)

        gcols = st.columns(2)
        with gcols[0]:
            st.markdown("**Casos mais similares**")
            st.dataframe(pd.DataFrame(gjson.get("top_similarity", []))[["a_label", "b_label", "score"]]
                         .rename(columns={"a_label": "entidade A", "b_label": "entidade B"}),
                         use_container_width=True, hide_index=True)
        with gcols[1]:
            st.markdown("**Entidades mais influentes**")
            st.dataframe(pd.DataFrame(gjson.get("top_pagerank", []))[["label", "type", "pagerank"]]
                         .rename(columns={"label": "nó", "type": "tipo"}),
                         use_container_width=True, hide_index=True)


# ===========================================================================
# COLLECTIONS
# ===========================================================================
elif page == "Base de dados":
    st.title("Base de dados")
    st.caption("Cada conjunto de dados com sua contagem e uma amostra de registros.")

    all_cols = MAIN_COLLECTIONS
    counts = {c: db[c].count_documents({}) for c in all_cols}
    mcols = st.columns(5)
    for i, (c, n) in enumerate(counts.items()):
        mcols[i % 5].metric(COLLECTION_LABELS.get(c, c), f"{n:,}")

    st.divider()
    chosen = st.selectbox("Conjunto de dados", all_cols,
                          index=all_cols.index("predictions"),
                          format_func=lambda c: COLLECTION_LABELS.get(c, c))
    n = counts[chosen]
    st.markdown(f"**{COLLECTION_LABELS.get(chosen, chosen)}** — {n:,} registro(s)")
    sample = list(db[chosen].find().limit(5))
    if sample:
        st.dataframe(pd.json_normalize(sample), use_container_width=True, hide_index=True)
    else:
        st.info("Conjunto de dados vazio.")


# ===========================================================================
# STATUS DO SERVIDOR
# ===========================================================================
elif page == "Status do servidor":
    st.title("Status do servidor")
    st.caption("Saúde dos três bancos que sustentam o pipeline, em tempo real.")

    if st.button("Atualizar"):
        st.rerun()

    def _check(fn):
        t0 = time.perf_counter()
        try:
            detail = fn()
            return True, (time.perf_counter() - t0) * 1000, detail
        except Exception as exc:  # noqa: BLE001 - qualquer falha de conexao interessa aqui
            return False, (time.perf_counter() - t0) * 1000, str(exc).splitlines()[0][:80]

    def _check_mongo() -> str:
        info = repo.mongo.server_info()
        return f"v{info['version']}"

    def _check_redis() -> str:
        info = repo.r.info("server")
        return f"v{info.get('redis_version', '?')}"

    def _check_neo4j() -> str:
        uri = os.getenv("MT_NEO4J_URI", "bolt://localhost:7688")
        user = os.getenv("MT_NEO4J_USER", "neo4j")
        password = os.getenv("MT_NEO4J_PASSWORD", "modeltrace123")
        driver = GraphDatabase.driver(uri, auth=(user, password))
        try:
            with driver.session(database=os.getenv("MT_NEO4J_DATABASE", "neo4j")) as session:
                session.run("RETURN 1").consume()
            return "GDS ativo"
        finally:
            driver.close()

    SERVICES = [
        ("MongoDB", "predições, projetos e modelos", _check_mongo),
        ("Redis", "cache, contadores e estruturas probabilísticas", _check_redis),
        ("Neo4j", "grafo de conhecimento e Graph Data Science", _check_neo4j),
    ]
    results = [(name, desc, *_check(fn)) for name, desc, fn in SERVICES]
    all_ok = all(ok for _, _, ok, _, _ in results)

    st.markdown(
        f'<div class="mt-status-banner {"ok" if all_ok else "down"}">'
        f'{"Todos os serviços operacionais" if all_ok else "Um ou mais serviços indisponíveis"}'
        f'</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(3)
    for col, (name, desc, ok, ms, detail) in zip(cols, results):
        color = "#22c55e" if ok else "#ef4444"
        with col:
            st.markdown(
                f'<div class="mt-status-card">'
                f'<div class="mt-status-dot" style="background:{color};box-shadow:0 0 12px {color}99"></div>'
                f'<div class="mt-status-name">{name}</div>'
                f'<div class="mt-status-badge" style="color:{color};border-color:{color}66;'
                f'background:{color}1f">{"online" if ok else "offline"}</div>'
                f'<div class="mt-status-desc">{desc}</div>'
                f'<div class="mt-status-detail">{detail}</div>'
                f'<div class="mt-status-latency">{ms:.0f} ms</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.divider()
    st.subheader("Dados")
    counts = repo.collection_counts()
    dcols = st.columns(4)
    dcols[0].metric("Predições", f"{counts.get('predictions', 0):,}")
    dcols[1].metric("Projetos", f"{counts.get('projects', 0):,}")
    dcols[2].metric("Modelos", f"{counts.get('models', 0):,}")
    dcols[3].metric("Notas de entidade", f"{counts.get('entity_notes', 0):,}")

    graph_export_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "logs", "graph_export.json")
    if os.path.exists(graph_export_path):
        with open(graph_export_path, encoding="utf-8") as f:
            gpayload = json.load(f)
        gstats = gpayload.get("stats", {})
        st.caption(
            f"Grafo: {gstats.get('nodes', '?')} nós · {gstats.get('edges', '?')} arestas · "
            f"{gstats.get('communities', '?')} comunidades — gerado em "
            f"{gpayload.get('generated_at') or '?'}"
        )

    st.caption(f"Última verificação: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
