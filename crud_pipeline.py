from __future__ import annotations

import hashlib
import json
import os
import random
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import redis
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

# ---------------------------------------------------------------------------
# Configuracao
# ---------------------------------------------------------------------------

MONGO_URL = os.getenv("MT_MONGO_URL", "mongodb://localhost:27018")
MONGO_DB = os.getenv("MT_MONGO_DB", "modeltrace_pipeline")
REDIS_HOST = os.getenv("MT_REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("MT_REDIS_PORT", "6380"))

SEED = 20260713
random.seed(SEED)

NOW = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)

# As "principais colecoes" do modelo documental.
MAIN_COLLECTIONS = [
    "organizations",
    "users",
    "projects",
    "models",
    "model_versions",
    "predictions",
    "metrics_snapshots",
    "entity_notes",
    "audit_events",
]

# Prefixo de namespace no Redis para nao colidir com outras chaves.
RK = "mt"  # redis key prefix



def banner(title: str) -> None:
    line = "=" * 78
    print(f"\n{line}\n{title}\n{line}")


def step(msg: str) -> None:
    print(f"  -> {msg}")


def show(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gen_id(prefix: str, *parts: str) -> str:
    seed = "::".join(parts) if parts else secrets.token_hex(6)
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def score_band(score: float) -> str:
    if score < 0.25:
        return "low"
    if score < 0.50:
        return "medium"
    if score < 0.75:
        return "high"
    return "critical"


# definicoes de dominio pra popular o banco

PROJECT_DEFS: list[dict[str, Any]] = [
    {
        "id": "proj_tcc_student_outcomes",
        "name": "TCC - Risco de Evasao (FAGEN/UFU)",
        "domain": "education",
        "entity_type": "student",
        "entity_prefix": "aluno",
        "n_entities": 40,
        "positive": "high_risk",
        "negative": "low_risk",
        "threshold": 0.45,
        "base_mean": 0.42,
        "models": [
            {"name": "CatBoost Evasao", "slug": "catboost-dropout", "algo": "CatBoost",
             "features": ["curso_origem", "taxa_aprovacao", "qtd_aprovacoes", "nota_media",
                          "ch_acumulada", "qtd_reprov_freq"]},
            {"name": "XGBoost Evasao", "slug": "xgboost-dropout", "algo": "XGBoost",
             "features": ["taxa_aprovacao", "qtd_reprovacoes", "nota_media", "pct_ch_concluida", "reprov_p1"]},
            {"name": "Regressao Logistica (baseline)", "slug": "logreg-dropout", "algo": "LogisticRegression",
             "features": ["taxa_aprovacao", "qtd_reprovacoes", "nota_media", "idade_ingresso",
                          "cotista", "curso_origem"]},
        ],
    },
    {
        "id": "proj_vale_dontgo_maintenance",
        "name": "Vale - Don't Go (Manutencao Preditiva)",
        "domain": "industrial",
        "entity_type": "industrial_asset",
        "entity_prefix": "ativo",
        "n_entities": 35,
        "positive": "event_risk",
        "negative": "normal_operation",
        "threshold": 0.50,
        "base_mean": 0.28,
        "models": [
            {"name": "Don't Go LightGBM (multi-horizonte)", "slug": "dontgo-lightgbm", "algo": "LightGBM",
             "features": ["n_fam_engine_coolant_4h", "n_crit_4h", "n_distinct_alarmes_4h",
                          "n_outlier_p99_12h", "Tag_Frota", "bucket_hora"]},
            {"name": "Don't Go XGBoost (comparativo)", "slug": "dontgo-xgboost", "algo": "XGBoost",
             "features": ["n_fam_engine_coolant_1h", "n_crit_1h", "n_evt_4h", "n_naocrit_4h",
                          "Tag_Frota", "turno"]},
            {"name": "Don't Go CatBoost (comparativo)", "slug": "dontgo-catboost", "algo": "CatBoost",
             "features": ["n_fam_hydraulic_12h", "n_fam_brakes_12h", "n_crit_12h",
                          "n_classe_active_4h", "Tag_Frota", "turno"]},
        ],
    },
    {
        "id": "proj_cnpj_closure_radar",
        "name": "CNPJ - Radar de Fechamento (12 meses)",
        "domain": "economics",
        "entity_type": "company",
        "entity_prefix": "empresa",
        "n_entities": 32,
        "positive": "closes_12m",
        "negative": "remains_active",
        "threshold": 0.40,
        "base_mean": 0.32,
        "models": [
            {"name": "Logistic Full (Radar 12M)", "slug": "logistic-full", "algo": "LogisticRegression",
             "features": ["idade_empresa_meses", "idade_log_meses", "coorte_abertura_ano_c",
                          "flag_optante_simples_t", "flag_optante_mei_t", "flag_tem_regime_t"]},
            {"name": "LightGBM Radar 12M", "slug": "cnpj-lightgbm", "algo": "LightGBM",
             "features": ["idade_empresa_meses", "coorte_abertura_ano_c", "flag_optante_mei_t",
                          "flag_excluido_simples_ate_t", "qtd_escrituracoes_regime_t_log", "flag_lucro_presumido_t"]},
            {"name": "XGBoost Radar 12M", "slug": "cnpj-xgboost", "algo": "XGBoost",
             "features": ["idade_empresa_meses", "coorte_abertura_ano_c", "flag_optante_simples_t",
                          "flag_excluido_mei_ate_t", "flag_lucro_real_t", "flag_imune_ou_isenta_t"]},
        ],
    },
    {
        "id": "proj_seeddemand_forecast",
        "name": "SeedDemand - Risco de Ruptura de Sementes",
        "domain": "agro",
        "entity_type": "product_market",
        "entity_prefix": "mercado",
        "n_entities": 30,
        "positive": "stockout_risk",
        "negative": "adequate_supply",
        "threshold": 0.50,
        "base_mean": 0.32,
        "models": [
            {"name": "SARIMA (risco de ruptura)", "slug": "sarima-stockout", "algo": "SARIMA",
             "features": ["value_usd_lag1", "value_usd_lag12", "value_usd_rmean3",
                          "value_usd_rmean12", "month_sin", "partner"]},
            {"name": "Prophet (risco de ruptura)", "slug": "prophet-stockout", "algo": "Prophet",
             "features": ["value_usd_lag1", "value_usd_rmean3", "month_sin", "month_cos",
                          "unit_price_usd_kg", "flow"]},
            {"name": "LSTM (clima + demanda)", "slug": "lstm-climate", "algo": "LSTM",
             "features": ["value_usd_lag1", "value_usd_lag3", "value_usd_rstd3",
                          "uberlandia_mg_br_t2m_mean_lag6", "petrolina_pe_br_precip_mm_lag6", "hemisphere"]},
        ],
    },
    {
        "id": "proj_seedquality_price",
        "name": "SeedQuality - Risco de Qualidade de Lote",
        "domain": "agro",
        "entity_type": "seed_lot",
        "entity_prefix": "lote",
        "n_entities": 32,
        "positive": "low_quality_risk",
        "negative": "quality_ok",
        "threshold": 0.50,
        "base_mean": 0.55,
        "models": [
            {"name": "XGBoost Aprovacao de Lote", "slug": "xgboost-lot-approval", "algo": "XGBoost",
             "features": ["pureza_fisica_pct", "umidade_semente_pct", "vigor_tetrazolio_pct",
                          "germinacao_inicial_pct", "idade_armazenagem_meses", "ur_armazem_pct"]},
            {"name": "Random Forest Aprovacao de Lote", "slug": "rf-lot-approval", "algo": "RandomForest",
             "features": ["especie", "germinacao_inicial_pct", "vigor_tetrazolio_pct",
                          "temp_armazenagem_c", "idade_armazenagem_meses", "tratamento_fungicida"]},
            {"name": "Regressao Logistica (baseline)", "slug": "logreg-lot-approval", "algo": "LogisticRegression",
             "features": ["pureza_fisica_pct", "umidade_semente_pct", "germinacao_inicial_pct",
                          "idade_armazenagem_meses"]},
        ],
    },
    {
        "id": "proj_llms_microscope",
        "name": "LLMs sob o Microscopio - Risco de Underperformance",
        "domain": "ai_eval",
        "entity_type": "llm_model",
        "entity_prefix": "llm",
        "n_entities": 30,
        "positive": "underperformer_risk",
        "negative": "competitive",
        "threshold": 0.50,
        "base_mean": 0.33,
        "models": [
            {"name": "Metadata Performance Model", "slug": "llm-metadata-perf", "algo": "XGBoost",
             "features": ["log_params", "type", "architecture", "precision", "org_top"]},
            {"name": "Benchmark Tier Classifier", "slug": "llm-benchmark-tier", "algo": "GradientBoosting",
             "features": ["ifeval", "bbh", "math", "gpqa", "musr", "mmlu_pro"]},
            {"name": "Outlier Risk Detector", "slug": "llm-outlier-risk", "algo": "IsolationForest",
             "features": ["ifeval", "bbh", "math", "gpqa", "musr", "log_params"]},
        ],
    },
    {
        "id": "proj_itsm_sla_breach",
        "name": "Syngenta ITSM - Risco de Violacao de SLA",
        "domain": "it_ops",
        "entity_type": "incident",
        "entity_prefix": "chamado",
        "n_entities": 32,
        "positive": "sla_breach_risk",
        "negative": "on_track",
        "threshold": 0.45,
        "base_mean": 0.24,
        "models": [
            {"name": "SLA Breach (HistGradientBoosting)", "slug": "itsm-hgb-sla", "algo": "HistGradientBoosting",
             "features": ["priority", "u_incident_type", "reassignment_count", "contact_type",
                          "assignment_group", "reopen_count"]},
            {"name": "SLA Breach (baseline logistico)", "slug": "itsm-logreg-sla", "algo": "LogisticRegression",
             "features": ["priority", "urgency", "impact", "u_incident_type", "reassignment_count", "opened_hour"]},
        ],
    },
]

CATEGORICALS = {
    # TCC evasao
    "curso_origem": ["ADM_Integral", "ADM_Noturno", "GI"],
    # Vale Don't Go
    "Tag_Frota": ["793-D 2S", "793-D 3S", "793-D 4S", "793-D 5S", "LeTourneau L 1850"],
    "bucket_hora": ["00-06_madrugada", "06-12_manha", "12-18_tarde", "18-24_noite"],
    "turno": ["diurno", "noturno"],
    # CNPJ
    "flag_optante_simples_t": ["optante_simples", "nao_optante"],
    "flag_optante_mei_t": ["mei", "nao_mei"],
    "flag_tem_regime_t": ["com_regime_tributario", "sem_regime_tributario"],
    "flag_excluido_simples_ate_t": ["excluido_simples", "nunca_excluido"],
    "flag_excluido_mei_ate_t": ["excluido_mei", "nunca_excluido_mei"],
    "flag_lucro_real_t": ["lucro_real", "outro_regime"],
    "flag_lucro_presumido_t": ["lucro_presumido", "outro_regime"],
    "flag_imune_ou_isenta_t": ["imune_ou_isenta", "tributada"],
    # SeedDemand
    "partner": ["EUA", "Holanda", "China", "Mexico", "Franca", "Italia", "Espanha", "India"],
    "flow": ["export", "import"],
    "hemisphere": ["N", "S"],
    # SeedQuality
    "especie": ["Tomate", "Cebola", "Alface", "Cenoura", "Pimentao", "Repolho", "Feijao", "Melancia"],
    "tratamento_fungicida": ["tratado", "nao_tratado"],
    # LLMs sob o microscopio
    "type": ["fine-tuned", "base merges/moerges", "chat (RLHF/DPO/IFT)", "pretrained",
             "continuously pretrained", "multimodal", "other"],
    "architecture": ["LlamaForCausalLM", "Qwen2ForCausalLM", "MistralForCausalLM", "Gemma2ForCausalLM",
                     "MixtralForCausalLM", "Phi3ForCausalLM", "Qwen2MoeForCausalLM", "GPTNeoXForCausalLM"],
    "precision": ["bfloat16", "float16", "8bit", "4bit"],
    "org_top": ["Qwen", "meta-llama", "mistralai", "google", "sometimesanotion", "DreadPoor", "CultriX", "OUTRA"],
    # Syngenta ITSM
    "priority": ["P1", "P2", "P3", "P4"],
    "u_incident_type": ["Access/Authorization", "Software/Application", "Availability", "User Related-SAP",
                        "Data", "Network", "Platform issues", "Break/fix"],
    "contact_type": ["Email", "Phone", "Self-service", "Self-service Template", "Event", "Walk-in", "Chat"],
    "assignment_group": ["INF-SAP-DEVOPS", "DXC-SAP", "SYN-NA-EUS", "Cloud&Compute NC Team",
                         "SYN-BRAZIL-STOCK", "Service Desk"],
    "urgency": ["1 - High", "2 - Medium", "3 - Low"],
    "impact": ["1 - High", "2 - Medium", "3 - Low"],
}
NUMERIC_RANGES = {
    # TCC evasao (ratios/notas em float; contagens em int)
    "taxa_aprovacao": (0.0, 1.0), "qtd_aprovacoes": (0, 40), "nota_media": (0.0, 100.0),
    "ch_acumulada": (0.0, 1200.0), "qtd_reprov_freq": (0, 20), "qtd_reprovacoes": (0, 30),
    "pct_ch_concluida": (0.0, 1.0), "reprov_p1": (0, 8), "idade_ingresso": (16, 60), "cotista": (0, 1),
    # Vale Don't Go (contagens de alarmes/eventos por janela)
    "n_fam_engine_coolant_4h": (0, 50), "n_crit_4h": (0, 60), "n_distinct_alarmes_4h": (0, 30),
    "n_outlier_p99_12h": (0, 40), "n_fam_engine_coolant_1h": (0, 20), "n_crit_1h": (0, 25),
    "n_evt_4h": (0, 300), "n_naocrit_4h": (0, 200), "n_fam_hydraulic_12h": (0, 60),
    "n_fam_brakes_12h": (0, 40), "n_crit_12h": (0, 120), "n_classe_active_4h": (0, 150),
    # CNPJ
    "idade_empresa_meses": (0, 600), "idade_log_meses": (0.0, 6.5),
    "coorte_abertura_ano_c": (-40, 25), "qtd_escrituracoes_regime_t_log": (0.0, 6.0),
    # SeedDemand
    "value_usd_lag1": (0.0, 3_000_000.0), "value_usd_lag3": (0.0, 3_000_000.0),
    "value_usd_lag12": (0.0, 3_000_000.0), "value_usd_rmean3": (0.0, 2_500_000.0),
    "value_usd_rmean12": (0.0, 2_500_000.0), "value_usd_rstd3": (0.0, 900_000.0),
    "month_sin": (-1.0, 1.0), "month_cos": (-1.0, 1.0), "unit_price_usd_kg": (10.0, 500.0),
    "uberlandia_mg_br_t2m_mean_lag6": (15.0, 30.0), "petrolina_pe_br_precip_mm_lag6": (0.0, 250.0),
    # SeedQuality
    "pureza_fisica_pct": (94.0, 100.0), "umidade_semente_pct": (4.0, 13.0),
    "vigor_tetrazolio_pct": (40.0, 100.0), "germinacao_inicial_pct": (40.0, 100.0),
    "idade_armazenagem_meses": (0, 36), "ur_armazem_pct": (25.0, 90.0), "temp_armazenagem_c": (3.0, 38.0),
    # LLMs sob o microscopio (benchmarks 0-100)
    "log_params": (-1.0, 2.2), "ifeval": (0.0, 90.0), "bbh": (0.0, 77.0), "math": (0.0, 72.0),
    "gpqa": (0.0, 30.0), "musr": (0.0, 39.0), "mmlu_pro": (0.0, 70.0),
    # Syngenta ITSM
    "reassignment_count": (0, 31), "reopen_count": (0, 6), "opened_hour": (0, 23),
}


def feature_value(name: str) -> Any:
    if name in CATEGORICALS:
        return random.choice(CATEGORICALS[name])
    low, high = NUMERIC_RANGES.get(name, (0.0, 1.0))
    if isinstance(low, int) and isinstance(high, int):
        return random.randint(low, high)
    return round(random.uniform(low, high), 4)


# toda a interacao com Mongo + Redis


class ModelTraceRepository:
    """Camada de acesso a dados (Repository Pattern) para o pipeline NoSQL."""

    def __init__(self) -> None:
        self.mongo: MongoClient = MongoClient(MONGO_URL, serverSelectionTimeoutMS=4000)
        self.db: Database = self.mongo[MONGO_DB]
        self.r: redis.Redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

    # -- conexao ------------------------------------------------------------
    def connect(self) -> None:
        self.mongo.admin.command("ping")
        self.r.ping()
        step(f"MongoDB conectado: {MONGO_URL} (db={MONGO_DB}) v{self.mongo.server_info()['version']}")
        step(f"Redis conectado:   {REDIS_HOST}:{REDIS_PORT}")

    # =======================================================================
    # 1) CRIAR as principais colecoes (+ indices)  -> DDL do mundo documental
    # =======================================================================
    def create_collections_and_indexes(self, drop: bool = True) -> None:
        if drop:
            self.db.client.drop_database(MONGO_DB)
            step(f"Banco '{MONGO_DB}' recriado do zero (drop_database).")

        for name in MAIN_COLLECTIONS:
            self.db.create_collection(name)
        step(f"{len(MAIN_COLLECTIONS)} colecoes criadas: {', '.join(MAIN_COLLECTIONS)}")

        # Indices - espelham os indices do MongoDocumentStore 
        self.db.users.create_index([("org_id", ASCENDING), ("email_hash", ASCENDING)], unique=True)
        self.db.projects.create_index([("org_id", ASCENDING), ("domain", ASCENDING)])
        self.db.models.create_index([("project_id", ASCENDING)])
        self.db.model_versions.create_index([("model_id", ASCENDING), ("version", ASCENDING)])
        self.db.predictions.create_index([("org_id", ASCENDING), ("project_id", ASCENDING), ("created_at", DESCENDING)])
        self.db.predictions.create_index([("model_id", ASCENDING), ("model_version", ASCENDING)])
        self.db.predictions.create_index([("entity.id_hash", ASCENDING), ("project_id", ASCENDING)])
        self.db.predictions.create_index([("prediction.score", DESCENDING)])
        self.db.predictions.create_index([("feedback.classification_result", ASCENDING), ("model_id", ASCENDING)])
        # request_id UNICO -> idempotencia (tambem reforcada por Bloom Filter no Redis)
        self.db.predictions.create_index([("metadata.request_id", ASCENDING)], unique=True, sparse=True)
        self.db.metrics_snapshots.create_index([("model_id", ASCENDING), ("model_version", ASCENDING)])
        self.db.audit_events.create_index([("project_id", ASCENDING), ("created_at", DESCENDING)])
        self.db.entity_notes.create_index([("entity_id_hash", ASCENDING)])
        step("Indices criados (inclui unique em users.email_hash e predictions.metadata.request_id).")

    # =======================================================================
    # Redis: reservar estruturas probabilisticas antes de ingerir
    # =======================================================================
    def redis_reset_and_reserve(self) -> None:
        # limpa apenas o namespace deste pipeline
        keys = self.r.keys(f"{RK}:*")
        if keys:
            self.r.delete(*keys)
        # Bloom Filter: idempotencia por request_id (1% de erro, capac. 100k)
        self.r.execute_command("BF.RESERVE", f"{RK}:seen_requests", "0.01", "100000")
        # Count-Min Sketch: frequencia aproximada de predicoes por entidade
        self.r.execute_command("CMS.INITBYPROB", f"{RK}:entity_freq", "0.001", "0.01")
        # Top-K: entidades "heavy hitter" (mais avaliadas)
        self.r.execute_command("TOPK.RESERVE", f"{RK}:top_entities", "10", "2000", "7", "0.925")
        step("Redis probabilistico reservado: Bloom (seen_requests), Count-Min (entity_freq), Top-K (top_entities).")

    # =======================================================================
    # 2) POPULAR as principais colecoes
     
    def seed_reference_data(self) -> dict[str, Any]:
        """Insere org, usuarios, projetos, modelos e versoes. Demonstra INSERT."""
        org_id = "org_ufu_gi_ops"
        # ---- organization (INSERT one) ----
        self.db.organizations.insert_one({
            "_id": org_id,
            "name": "UFU GI Decision Ops Lab",
            "plan": "enterprise-simulation",
            "owner_id": "user_diego_ops",
            "settings": {"max_projects": 50, "retention_days": 1825, "enable_bias_analysis": True},
            "status": "active",
            "created_at": iso(NOW - timedelta(days=30)),
        })

        # ---- users (INSERT many) ----
        self.db.users.insert_many([
            {
                "_id": "user_diego_ops", "org_id": org_id, "name": "Diego Henrique Xavier",
                "email_hash": hashlib.sha256(b"diego").hexdigest(), "email_masked": "d***@gmail.com",
                "role": "OWNER", "preferences": {"theme": "dark", "locale": "pt-BR"},
                "status": "active", "created_at": iso(NOW - timedelta(days=30)),
            },
            {
                "_id": "user_ops_analyst", "org_id": org_id, "name": "Ana Operacoes",
                "email_hash": hashlib.sha256(b"ana").hexdigest(), "email_masked": "a***@ufu.br",
                "role": "ANALYST", "preferences": {"theme": "light", "locale": "pt-BR"},
                "status": "active", "created_at": iso(NOW - timedelta(days=20)),
            },
        ])

        models_index: dict[str, dict] = {}
        n_models = n_versions = 0
        for pdef in PROJECT_DEFS:
            # ---- project ----
            self.db.projects.insert_one({
                "_id": pdef["id"], "org_id": org_id, "name": pdef["name"], "domain": pdef["domain"],
                "problem_type": "binary_classification", "owner_id": "user_diego_ops",
                "entity_type": pdef["entity_type"],
                "settings": {
                    "default_threshold": pdef["threshold"],
                    "positive_label": pdef["positive"], "negative_label": pdef["negative"],
                    "retention_days": 1825, "data_contract_mode": "warn",
                },
                "stats": {"total_predictions": 0, "total_models": len(pdef["models"]), "active_alerts": 0},
                "status": "active", "created_at": iso(NOW - timedelta(days=25)),
            })
            for mdef in pdef["models"]:
                model_id = gen_id("model", pdef["id"], mdef["slug"])
                versions = [
                    {"version": "v1", "status": "deprecated"},
                    {"version": "v2", "status": "production"},
                ]
                prod_vid = gen_id("version", model_id, "v2")
                # ---- model ----
                self.db.models.insert_one({
                    "_id": model_id, "org_id": org_id, "project_id": pdef["id"], "name": mdef["name"],
                    "slug": mdef["slug"], "problem_type": "binary_classification",
                    "target_name": pdef["positive"],
                    "labels": {"positive": pdef["positive"], "negative": pdef["negative"]},
                    "default_threshold": pdef["threshold"],
                    "expected_features": [{"name": f, "type": "categorical" if f in CATEGORICALS else "numeric"}
                                          for f in mdef["features"]],
                    "production_version_id": prod_vid,
                    "status": "active", "created_at": iso(NOW - timedelta(days=24)),
                })
                n_models += 1
                # ---- model_versions ----
                for vdef in versions:
                    vid = gen_id("version", model_id, vdef["version"])
                    base = round(random.uniform(0.66, 0.9), 4)
                    self.db.model_versions.insert_one({
                        "_id": vid, "org_id": org_id, "project_id": pdef["id"], "model_id": model_id,
                        "version": vdef["version"], "algorithm": mdef["algo"], "status": vdef["status"],
                        "features": mdef["features"],
                        "offline_metrics": {
                            "accuracy": round(base - 0.05, 4), "precision": round(base - 0.12, 4),
                            "recall": round(base - 0.03, 4), "f1": round(base - 0.08, 4),
                            "auc_roc": base,
                        },
                        "created_at": iso(NOW - timedelta(days=23)),
                    })
                    n_versions += 1
                models_index[model_id] = {
                    "project": pdef, "model_def": mdef, "model_id": model_id,
                    "prod_version_id": prod_vid,
                    "version_ids": {v["version"]: gen_id("version", model_id, v["version"]) for v in versions},
                }

        step(f"Populado: 1 organization, 2 users, {len(PROJECT_DEFS)} projects, "
             f"{n_models} models, {n_versions} model_versions.")
        return {"org_id": org_id, "models_index": models_index}

    def build_prediction(self, ctx: dict, i: int) -> dict:
        """Monta um documento de predicao com todos os sub-documentos embutidos."""
        pdef = ctx["project"]
        mdef = ctx["model_def"]
        model_id = ctx["model_id"]
        version_name = random.choices(["v1", "v2"], weights=[0.25, 0.75], k=1)[0]
        version_id = ctx["version_ids"][version_name]
        threshold = pdef["threshold"]

        score = max(0.0, min(1.0, random.gauss(pdef["base_mean"], 0.2)))
        above = score >= threshold
        label = pdef["positive"] if above else pdef["negative"]

        raw_entity = f"{pdef['id']}-{i % max(1, ctx['n_entities'])}"
        entity_hash = hashlib.sha256(raw_entity.encode()).hexdigest()
        features = {f: feature_value(f) for f in mdef["features"]}

        # explanations: usadas no aggregation pipeline 2 ($unwind)
        top = random.sample(list(features.items()), min(3, len(features)))
        explanations = [
            {"feature": fn, "value": fv, "impact": round(0.05 + random.random() * 0.3 * score, 4),
             "direction": "risk_up" if above else "risk_down", "rank": rank}
            for rank, (fn, fv) in enumerate(top, start=1)
        ]

        # feedback correlacionado com o score (matriz de confusao realista)
        feedback: dict[str, Any] = {"available": False}
        if random.random() < 0.7:
            target = max(0.03, min(0.97, 0.45 * pdef["base_mean"] + 0.55 * score))
            observed = 1 if random.random() < target else 0
            cls = ("tp" if above and observed else "fp" if above and not observed
                   else "fn" if not above and observed else "tn")
            feedback = {
                "available": True, "observed_value": observed,
                "observed_label": pdef["positive"] if observed else pdef["negative"],
                "classification_result": cls, "source": "seed_simulation",
                "received_at": iso(NOW - timedelta(days=random.randint(0, 10))),
            }

        created = NOW - timedelta(days=random.randint(0, 25), hours=random.randint(0, 23))
        return {
            "_id": gen_id("pred", model_id, str(i)),
            "org_id": ctx["org_id"], "project_id": pdef["id"], "model_id": model_id,
            "model_version_id": version_id, "model_version": version_name,
            "entity": {"id": f"entity_{entity_hash[:12]}", "id_hash": entity_hash,
                       "type": pdef["entity_type"], "display_name_masked": "[protected]"},
            "features": features,
            "prediction": {"label": label, "score": round(score, 4), "threshold": threshold,
                           "above_threshold": above, "score_band": score_band(score)},
            "explanations": explanations,
            "decision": {"action": "human_review" if above else "auto_pass",
                         "status": "triggered" if above else "skipped",
                         "reason": "score_above_threshold" if above else "below_threshold"},
            "feedback": feedback,
            "flags": {"is_critical": score > 0.85, "reviewed_by": None},
            "metadata": {"source_system": "seed_simulation", "environment": "production_simulation",
                         "request_id": f"seed_{model_id}_{i:06d}", "algorithm": mdef["algo"]},
            "created_at": iso(created),
        }

    def seed_predictions(self, ctx: dict, per_model: int = 260) -> int:
        """Insere predicoes em lote (INSERT many) e alimenta o Redis em paralelo."""
        org_id = ctx["org_id"]
        total = 0
        for model_id, mctx in ctx["models_index"].items():
            mctx = {**mctx, "org_id": org_id, "n_entities": max(20, per_model // 4)}
            batch = [self.build_prediction(mctx, i) for i in range(per_model)]
            self.db.predictions.insert_many(batch)
            for p in batch:
                self.redis_ingest(p)  # alimenta estruturas comuns + probabilisticas
            total += len(batch)
        # atualiza stats dos projetos (UPDATE many via agregacao simples)
        for pdef in PROJECT_DEFS:
            cnt = self.db.predictions.count_documents({"project_id": pdef["id"]})
            self.db.projects.update_one({"_id": pdef["id"]}, {"$set": {"stats.total_predictions": cnt}})
        step(f"{total} predicoes inseridas (insert_many) e replicadas no Redis.")
        return total

    def seed_entity_notes(self, per_project: int = 6) -> int:
        """Notas operacionais sobre entidades (usadas no $lookup do pipeline 2)."""
        inserted = 0
        for pdef in PROJECT_DEFS:
            top = self.db.predictions.find(
                {"project_id": pdef["id"]}, {"entity": 1}
            ).sort("prediction.score", DESCENDING).limit(per_project)
            for p in top:
                self.db.entity_notes.insert_one({
                    "_id": gen_id("note", p["_id"]),
                    "org_id": "org_ufu_gi_ops", "project_id": pdef["id"],
                    "entity_id": p["entity"]["id"], "entity_id_hash": p["entity"]["id_hash"],
                    "author": "user_ops_analyst",
                    "text": "Entidade sob acompanhamento operacional (risco recorrente).",
                    "created_at": iso(NOW - timedelta(days=random.randint(0, 5))),
                })
                inserted += 1
        step(f"{inserted} entity_notes inseridas (para demonstrar $lookup no pipeline 2).")
        return inserted

    # Redis INGESTAO em estruturas comuns probabilisticas
    def redis_ingest(self, pred: dict) -> None:
        r = self.r
        model_id = pred["model_id"]
        entity_id = pred["entity"]["id"]
        score = pred["prediction"]["score"]
        req = pred["metadata"]["request_id"]

        # --- PROBABILISTICAS ---
        # HyperLogLog: cardinalidade aproximada de entidades unicas avaliadas
        r.pfadd(f"{RK}:hll:entities:{model_id}", entity_id)
        # Bloom Filter: marca request_id como visto (idempotencia)
        r.execute_command("BF.ADD", f"{RK}:seen_requests", req)
        # Count-Min Sketch: frequencia aproximada por entidade
        r.execute_command("CMS.INCRBY", f"{RK}:entity_freq", entity_id, 1)
        # Top-K: heavy hitters
        r.execute_command("TOPK.ADD", f"{RK}:top_entities", entity_id)

        # --- COMUNS ---
        # Hash: contadores ao vivo por modelo
        r.hincrby(f"{RK}:counters:{model_id}", "predictions", 1)
        if pred["prediction"]["above_threshold"]:
            r.hincrby(f"{RK}:counters:{model_id}", "positives", 1)
        if pred["feedback"].get("available"):
            r.hincrby(f"{RK}:counters:{model_id}", "with_feedback", 1)
        # Sorted Set: ranking de entidades por risco (score maximo observado)
        r.zadd(f"{RK}:risk:{pred['project_id']}", {entity_id: score}, gt=True)
        # List: stream das ultimas predicoes (mantem so as 50 mais recentes)
        r.lpush(f"{RK}:stream:{pred['project_id']}",
                json.dumps({"entity": entity_id, "score": score, "label": pred["prediction"]["label"]}))
        r.ltrim(f"{RK}:stream:{pred['project_id']}", 0, 49)

    def redis_cache_set(self, key: str, payload: dict, ttl: int = 60) -> None:
        """String/JSON cache com TTL - usado para cachear o dashboard."""
        self.r.set(f"{RK}:cache:{key}", json.dumps(payload, default=str), ex=ttl)

    def redis_cache_get(self, key: str) -> dict | None:
        raw = self.r.get(f"{RK}:cache:{key}")
        return json.loads(raw) if raw else None

    def redis_rate_limit(self, api_key: str, limit: int = 5, window: int = 60) -> bool:
        """Counter + EXPIRE: retorna True se permitido, False se estourou o limite."""
        k = f"{RK}:ratelimit:{api_key}"
        current = self.r.incr(k)
        if current == 1:
            self.r.expire(k, window)
        return current <= limit

    # =======================================================================
    # 3) CRUD das principais colecoes: INSERT / FIND / UPDATE / DELETE
    # =======================================================================

    def insert_prediction(self, doc: dict) -> dict:
        """INSERT com idempotencia: o Bloom Filter evita reprocessar request_id."""
        req = doc["metadata"]["request_id"]
        already = self.r.execute_command("BF.EXISTS", f"{RK}:seen_requests", req)
        if already:
            return {"status": "duplicate_skipped", "request_id": req}
        self.db.predictions.insert_one(doc)
        self.redis_ingest(doc)
        self.append_audit(doc["project_id"], "prediction.created", {"prediction_id": doc["_id"]})
        return {"status": "inserted", "prediction_id": doc["_id"]}

    def find_predictions(self, filter_: dict, *, sort=None, projection=None,
                         limit: int = 20, skip: int = 0) -> list[dict]:
        """FIND com filtro, projecao ($project no find), ordenacao e paginacao."""
        cursor = self.db.predictions.find(filter_, projection or {"_id": 1, "entity.id": 1,
                                          "prediction.score": 1, "prediction.label": 1,
                                          "feedback.classification_result": 1, "created_at": 1})
        if sort:
            cursor = cursor.sort(sort)
        return list(cursor.skip(skip).limit(limit))

    def find_prediction(self, pred_id: str) -> dict | None:
        return self.db.predictions.find_one({"_id": pred_id})

    def update_feedback(self, pred_id: str, observed_value: int) -> bool:
        """UPDATE: anexa feedback real e recalcula a classe da matriz de confusao."""
        pred = self.find_prediction(pred_id)
        if not pred:
            return False
        above = pred["prediction"]["above_threshold"]
        cls = ("tp" if above and observed_value else "fp" if above and not observed_value
               else "fn" if not above and observed_value else "tn")
        pos = pred["prediction"]["label"] if above else None
        res = self.db.predictions.update_one(
            {"_id": pred_id},
            {"$set": {
                "feedback.available": True,
                "feedback.observed_value": observed_value,
                "feedback.classification_result": cls,
                "feedback.received_at": iso(NOW),
                "feedback.source": "manual_review",
                "flags.reviewed_by": "user_ops_analyst",
                "flags.reviewed_at": iso(NOW),
            }},
        )
        self.append_audit(pred["project_id"], "feedback.updated",
                          {"prediction_id": pred_id, "classification_result": cls})
        return res.modified_count > 0

    def bulk_flag_critical(self, project_id: str, min_score: float = 0.85) -> int:
        """UPDATE many: marca como critico todas as predicoes acima de um score."""
        res = self.db.predictions.update_many(
            {"project_id": project_id, "prediction.score": {"$gte": min_score}},
            {"$set": {"flags.is_critical": True, "flags.escalated": True}},
        )
        return res.modified_count

    def delete_prediction(self, pred_id: str) -> bool:
        """DELETE one."""
        res = self.db.predictions.delete_one({"_id": pred_id})
        return res.deleted_count > 0

    def delete_predictions(self, filter_: dict) -> int:
        """DELETE many (ex.: expurgo por retencao)."""
        return self.db.predictions.delete_many(filter_).deleted_count

    def append_audit(self, project_id: str, event_type: str, context: dict) -> None:
        """Trilha append-only (INSERT em audit_events)."""
        self.db.audit_events.insert_one({
            "_id": gen_id("audit", project_id, event_type, secrets.token_hex(4)),
            "org_id": "org_ufu_gi_ops", "project_id": project_id,
            "actor": {"type": "system", "id": "crud_pipeline"},
            "event_type": event_type, "context": context, "created_at": iso(NOW),
        })

    # =======================================================================
    # 4) AGGREGATION PIPELINE 1 - Leaderboard de performance dos modelos
    #    Funcionalidade: ranquear modelos/versoes por F1 a partir do feedback.
    #    Estagios: $match, $group, $set, $lookup, $unwind, $project, $sort, $merge
    # =======================================================================
    def agg_model_leaderboard(self) -> list[dict]:
        pipeline = [
            # $match: so predicoes que tem feedback (rotulo real conhecido)
            {"$match": {"feedback.available": True}},
            # $group: matriz de confusao por (modelo, versao)
            {"$group": {
                "_id": {"model_id": "$model_id", "version": "$model_version"},
                "tp": {"$sum": {"$cond": [{"$eq": ["$feedback.classification_result", "tp"]}, 1, 0]}},
                "fp": {"$sum": {"$cond": [{"$eq": ["$feedback.classification_result", "fp"]}, 1, 0]}},
                "tn": {"$sum": {"$cond": [{"$eq": ["$feedback.classification_result", "tn"]}, 1, 0]}},
                "fn": {"$sum": {"$cond": [{"$eq": ["$feedback.classification_result", "fn"]}, 1, 0]}},
                "n": {"$sum": 1},
                "avg_score": {"$avg": "$prediction.score"},
            }},
            # $set (=$addFields): deriva precision, recall e F1
            {"$set": {
                "precision": {"$cond": [{"$gt": [{"$add": ["$tp", "$fp"]}, 0]},
                                        {"$divide": ["$tp", {"$add": ["$tp", "$fp"]}]}, 0]},
                "recall": {"$cond": [{"$gt": [{"$add": ["$tp", "$fn"]}, 0]},
                                     {"$divide": ["$tp", {"$add": ["$tp", "$fn"]}]}, 0]},
            }},
            {"$set": {
                "f1": {"$cond": [{"$gt": [{"$add": ["$precision", "$recall"]}, 0]},
                                 {"$divide": [{"$multiply": [2, "$precision", "$recall"]},
                                              {"$add": ["$precision", "$recall"]}]}, 0]},
            }},
            # $lookup: traz o nome do modelo da colecao models
            {"$lookup": {"from": "models", "localField": "_id.model_id",
                         "foreignField": "_id", "as": "model"}},
            # $unwind: model vira objeto (era array de 1 elemento)
            {"$unwind": "$model"},
            # $project (SELECT/reshape): escolhe e renomeia os campos de saida
            {"$project": {
                "_id": {"$concat": ["$_id.model_id", "::", "$_id.version"]},
                "model_name": "$model.name", "version": "$_id.version",
                "domain_project_id": "$model.project_id",
                "confusion": {"tp": "$tp", "fp": "$fp", "tn": "$tn", "fn": "$fn"},
                "n_with_feedback": "$n",
                "avg_score": {"$round": ["$avg_score", 4]},
                "precision": {"$round": ["$precision", 4]},
                "recall": {"$round": ["$recall", 4]},
                "f1": {"$round": ["$f1", 4]},
                "computed_at": iso(NOW),
            }},
            # $sort: melhores modelos primeiro
            {"$sort": {"f1": DESCENDING}},
            # $merge: materializa o resultado na colecao metrics_snapshots
            {"$merge": {"into": "metrics_snapshots", "on": "_id",
                        "whenMatched": "replace", "whenNotMatched": "insert"}},
        ]
        # $merge nao retorna documentos; roda o pipeline e depois le o resultado
        self.db.predictions.aggregate(pipeline)
        return list(self.db.metrics_snapshots.find().sort("f1", DESCENDING))

    # =======================================================================
    # 5) AGGREGATION PIPELINE 2 - Drivers de risco (feature importance operacional)
    #    Funcionalidade: quais features mais empurram decisoes para "risco alto",
    #    + amostra auditavel aleatoria. Estagios: $match, $unwind, $group, $set,
    #    $sort, $limit, $lookup, $project, $sample, $facet.
    # =======================================================================
    def agg_feature_drivers(self, project_id: str) -> dict:
        pipeline = [
            # $match: predicoes de risco alto/critico do projeto escolhido
            {"$match": {"project_id": project_id,
                        "prediction.score_band": {"$in": ["high", "critical"]}}},
            # $facet: dois ramos independentes sobre o mesmo conjunto filtrado
            {"$facet": {
                # Ramo A: ranking de features que dirigem o risco
                "drivers": [
                    {"$unwind": "$explanations"},          # explode a lista embutida
                    {"$group": {
                        "_id": "$explanations.feature",
                        "avg_impact": {"$avg": "$explanations.impact"},
                        "times_top_driver": {"$sum": {"$cond": [{"$eq": ["$explanations.rank", 1]}, 1, 0]}},
                        "occurrences": {"$sum": 1},
                    }},
                    {"$set": {"avg_impact": {"$round": ["$avg_impact", 4]}}},
                    {"$sort": {"avg_impact": DESCENDING}},
                    {"$limit": 5},
                    {"$project": {"_id": 0, "feature": "$_id", "avg_impact": 1,
                                  "times_top_driver": 1, "occurrences": 1}},
                ],
                # Ramo B: amostra auditavel aleatoria de 3 casos criticos + notas
                "audit_sample": [
                    {"$sample": {"size": 3}},              # amostragem aleatoria
                    {"$lookup": {"from": "entity_notes", "localField": "entity.id_hash",
                                 "foreignField": "entity_id_hash", "as": "notes"}},
                    {"$project": {"_id": 1, "entity_id": "$entity.id",
                                  "score": "$prediction.score", "label": "$prediction.label",
                                  "top_driver": {"$arrayElemAt": ["$explanations.feature", 0]},
                                  "note_count": {"$size": "$notes"}}},
                ],
                # Ramo C: contagem total do universo analisado
                "universe": [{"$count": "high_risk_total"}],
            }},
        ]
        return list(self.db.predictions.aggregate(pipeline))[0]

    # =======================================================================
    # 6) Leitura das estruturas Redis (comuns + probabilisticas) -> dashboard
    # =======================================================================
    def redis_dashboard(self) -> dict:
        r = self.r
        out: dict[str, Any] = {"common": {}, "probabilistic": {}}

        # -- COMUNS --
        # Hash: contadores por modelo
        counters = {}
        for k in r.scan_iter(f"{RK}:counters:*"):
            counters[k.split(":")[-1]] = r.hgetall(k)
        out["common"]["hash_counters_by_model"] = counters
        # Sorted Set: top-5 entidades de maior risco por projeto
        risk = {}
        for k in r.scan_iter(f"{RK}:risk:*"):
            proj = k.split(":")[-1]
            risk[proj] = r.zrevrange(k, 0, 4, withscores=True)
        out["common"]["sorted_set_top_risk"] = risk
        # List: ultimas 3 predicoes de um projeto
        sample_stream_key = next(iter(r.scan_iter(f"{RK}:stream:*")), None)
        out["common"]["list_recent_stream"] = (
            [json.loads(x) for x in r.lrange(sample_stream_key, 0, 2)] if sample_stream_key else []
        )
        # String cache
        out["common"]["string_cache_keys"] = [k for k in r.scan_iter(f"{RK}:cache:*")]

        # -- PROBABILISTICAS --
        # HyperLogLog: cardinalidade aproximada de entidades por modelo
        hll = {}
        for k in r.scan_iter(f"{RK}:hll:entities:*"):
            hll[k.split(":")[-1]] = r.pfcount(k)
        out["probabilistic"]["hyperloglog_unique_entities"] = hll
        # Bloom Filter: info + teste de pertinencia
        info = r.execute_command("BF.INFO", f"{RK}:seen_requests")
        if not isinstance(info, dict):  # compat: versoes antigas retornam lista plana
            info = dict(zip(info[::2], info[1::2]))
        out["probabilistic"]["bloom_seen_requests"] = {
            "capacity": info.get("Capacity"),
            "items_inserted": info.get("Number of items inserted"),
            "size_bytes": info.get("Size"),
        }
        # Count-Min Sketch: frequencia aproximada de algumas entidades
        top = r.execute_command("TOPK.LIST", f"{RK}:top_entities")
        cms = {e: r.execute_command("CMS.QUERY", f"{RK}:entity_freq", e)[0] for e in top[:5]}
        out["probabilistic"]["count_min_freq_of_top_entities"] = cms
        # Top-K: heavy hitters com contagem
        tk = r.execute_command("TOPK.LIST", f"{RK}:top_entities", "WITHCOUNT")
        out["probabilistic"]["topk_heavy_hitters"] = dict(zip(tk[::2], [int(x) for x in tk[1::2]]))
        return out

    # -- estatisticas finais -------------------------------------------------
    def collection_counts(self) -> dict[str, int]:
        return {c: self.db[c].count_documents({}) for c in MAIN_COLLECTIONS + ["metrics_snapshots"]}


# ===========================================================================
# Orquestracao: roda o pipeline completo e imprime o log de saida
# ===========================================================================


def main() -> None:
    repo = ModelTraceRepository()

    banner("FASE 0 - CONEXAO")
    repo.connect()

    banner("FASE 1 - CRIAR PRINCIPAIS COLECOES (+ INDICES)")
    repo.create_collections_and_indexes(drop=True)
    repo.redis_reset_and_reserve()

    banner("FASE 2 - POPULAR DADOS DE REFERENCIA (org, users, projects, models, versions)")
    ctx = repo.seed_reference_data()

    banner("FASE 3 - POPULAR PREDICOES (insert_many) + INGESTAO NO REDIS")
    total = repo.seed_predictions(ctx, per_model=260)
    repo.seed_entity_notes(per_project=6)

    # ---------------------------------------------------------------- CRUD
    banner("FASE 4 - CRUD DAS PRINCIPAIS COLECOES: INSERT / FIND / UPDATE / DELETE")

    step("INSERT: nova predicao manual (com idempotencia via Bloom Filter)")
    sample_model = next(iter(ctx["models_index"]))
    new_doc = repo.build_prediction(
        {**ctx["models_index"][sample_model], "org_id": ctx["org_id"], "n_entities": 50}, 99999)
    new_doc["metadata"]["request_id"] = "manual_demo_0001"
    print("     resultado 1a insercao:", repo.insert_prediction(new_doc))
    print("     resultado 2a insercao (duplicada):", repo.insert_prediction(new_doc))
    pred_id = new_doc["_id"]

    step("FIND one: recupera a predicao inserida")
    got = repo.find_prediction(pred_id)
    show({"_id": got["_id"], "entity": got["entity"]["id"], "prediction": got["prediction"],
          "feedback": got["feedback"]})

    step("FIND many: top 5 predicoes de maior score no projeto (com projecao + sort)")
    pid = new_doc["project_id"]
    rows = repo.find_predictions(
        {"project_id": pid}, sort=[("prediction.score", DESCENDING)], limit=5)
    show(rows)

    step("UPDATE one: anexa feedback real (observed_value=1) e recalcula a matriz")
    ok = repo.update_feedback(pred_id, observed_value=1)
    after = repo.find_prediction(pred_id)
    print("     update ok:", ok, "| feedback agora:", after["feedback"]["classification_result"])

    step("UPDATE many: marca predicoes criticas (score >= 0.85) como escaladas")
    n_flag = repo.bulk_flag_critical(pid, min_score=0.85)
    print("     predicoes escaladas:", n_flag)

    step("DELETE one: remove a predicao de demonstracao")
    print("     deletada:", repo.delete_prediction(pred_id))

    step("DELETE many: expurgo de predicoes de teste sinteticas antigas (nenhuma aqui)")
    print("     removidas por filtro de retencao:",
          repo.delete_predictions({"metadata.request_id": {"$regex": "^__never__"}}))

    # ---------------------------------------------------------- AGGREGATION 1
    banner("FASE 5 - AGGREGATION PIPELINE 1: LEADERBOARD DE MODELOS (match/group/set/lookup/unwind/project/sort/merge)")
    board = repo.agg_model_leaderboard()
    for row in board:
        print(f"  F1={row['f1']:<7} P={row['precision']:<7} R={row['recall']:<7} "
              f"n={row['n_with_feedback']:<5} {row['model_name']} [{row['version']}] "
              f"conf={row['confusion']}")
    _dump_json("aggregation_1_leaderboard.json", board)

    # ---------------------------------------------------------- AGGREGATION 2
    banner("FASE 6 - AGGREGATION PIPELINE 2: DRIVERS DE RISCO (match/facet/unwind/group/sort/limit/sample/lookup/project/count)")
    drivers = repo.agg_feature_drivers(pid)
    print("  Universo de risco alto:", drivers["universe"])
    print("  Top features que dirigem o risco:")
    for d in drivers["drivers"]:
        print(f"    - {d['feature']:<20} impacto_medio={d['avg_impact']:<8} "
              f"top_driver_em={d['times_top_driver']} ocorrencias={d['occurrences']}")
    print("  Amostra auditavel aleatoria ($sample):")
    for s in drivers["audit_sample"]:
        print(f"    - {s['entity_id']} score={s['score']} label={s['label']} top={s.get('top_driver')}")
    _dump_json("aggregation_2_feature_drivers.json", drivers)

    # ---------------------------------------------------------- REDIS
    banner("FASE 7 - REDIS: ESTRUTURAS COMUNS (String cache, Hash, Sorted Set, List, Counter)")
    step("String cache do dashboard com TTL (SET/GET)")
    repo.redis_cache_set("dashboard:overview", {"total_predictions": total, "generated_at": iso(NOW)}, ttl=120)
    print("     cache lido de volta:", repo.redis_cache_get("dashboard:overview"))

    step("Counter + EXPIRE: rate limit de uma API key (limite=5/60s)")
    decisions = [repo.redis_rate_limit("mt_live_demo", limit=5) for _ in range(7)]
    print("     permissoes das 7 chamadas:", decisions)

    dash = repo.redis_dashboard()
    print("\n  --- Estruturas COMUNS ---")
    show(dash["common"])

    banner("FASE 8 - REDIS: ESTRUTURAS PROBABILISTICAS (HyperLogLog, Bloom, Count-Min, Top-K)")
    show(dash["probabilistic"])

    step("Bloom Filter em acao: um request_id ja visto e um novo")
    seen = repo.r.execute_command("BF.EXISTS", f"{RK}:seen_requests", f"seed_{sample_model}_000001")
    unseen = repo.r.execute_command("BF.EXISTS", f"{RK}:seen_requests", "request_que_nunca_existiu")
    print(f"     BF.EXISTS(existente)={seen}  BF.EXISTS(inexistente)={unseen}")

    # ---------------------------------------------------------- SUMARIO
    banner("SUMARIO FINAL - CONTAGEM POR COLECAO")
    counts = repo.collection_counts()
    for c, n in counts.items():
        print(f"  {c:22} {n:>7}")
    _dump_json("collection_counts.json", counts)
    print("\nPipeline concluido com sucesso.")


def _dump_json(name: str, obj: Any) -> None:
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


if __name__ == "__main__":
    main()
