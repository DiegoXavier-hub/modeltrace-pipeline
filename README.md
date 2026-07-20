# Pipeline de Banco NoSQL — ModelTrace

Pipeline completo de banco de dados NoSQL (**MongoDB + Redis + Neo4j**) do projeto **ModelTrace**,
uma plataforma de observabilidade e governança de decisões de Machine Learning.

Todo o código de banco documental/chave-valor fica em **um único arquivo de CRUD**:
[`crud_pipeline.py`](crud_pipeline.py). O grafo de conhecimento (Neo4j + Graph Data Science)
fica em [`graph_pipeline.py`](graph_pipeline.py). A interface protótipo (Streamlit) fica em
[`streamlit_app.py`](streamlit_app.py) e reutiliza as duas camadas de banco.

---

## 1. Arquitetura

| Camada | Tecnologia | Papel |
|--------|-----------|-------|
| Banco documental | **MongoDB 7** | 9 coleções principais; a coleção `predictions` agrega toda a decisão de ML em 1 documento |
| Chave-valor / probabilístico | **Redis Stack** (RedisBloom) | cache, contadores, rankings + estruturas probabilísticas |
| Grafo / Graph Data Science | **Neo4j 5 + GDS** | grafo de conhecimento do domínio (não do código) + nodeSimilarity/louvain/pageRank |
| Interface protótipo | **Streamlit** | telas de INSERT / FIND / UPDATE / DELETE, dashboards e visualização do grafo 2D/3D |

Modelagem visual (referências 1:N + agregação/embedding): **[`docs/modelagem-er-simplificada.png`](docs/modelagem-er-simplificada.png)**

![ER simplificado](docs/modelagem-er-simplificada.png)

---

## 2. Como rodar

### Windows — automático

```bat
instalar.bat            :: 1a vez: verifica Python/Docker/Git e instala tudo num .venv local
executar_pipeline.bat    :: sobe a infra, popula o banco, gera o grafo e abre o Streamlit
```

`instalar.bat` confere se Python, Docker e Git estão no PATH (avisando onde baixar o que
faltar), cria um ambiente virtual isolado em `.venv\` e instala as dependências ali —
inclusive a biblioteca do grafo (`constelario`), que vem direto do GitHub. Ao final, roda
[`verificar_ambiente.py`](verificar_ambiente.py) e confirma que cada biblioteca importa
corretamente. Rode de novo sempre que quiser reconferir o ambiente.

### Manual (qualquer sistema)

```bash
# 1) Infra (Docker) — MongoDB + Redis Stack + Neo4j (GDS)
docker compose -f docker-compose.pipeline.yml up -d

# 2) Dependências Python
pip install -r requirements-pipeline.txt

# 3) Pipeline de banco: cria + popula coleções, roda CRUD, os 2 aggregation
#    pipelines e as estruturas Redis. A saída vira o log da entrega.
python crud_pipeline.py

# 4) Pipeline de grafo: constrói o grafo no Neo4j, roda os 3 algoritmos GDS
#    (nodeSimilarity, louvain, pageRank) e gera grafo.html.
python graph_pipeline.py

# 5) Protótipo de interface (funcionalidade mais importante + aba de grafo)
streamlit run streamlit_app.py
```

> As portas são `27018` (Mongo), `6380` (Redis) e `7688`/`7475` (Neo4j Bolt/Browser) para
> não conflitar com serviços já em uso. Configuráveis por `MT_MONGO_URL`, `MT_MONGO_DB`,
> `MT_REDIS_HOST`, `MT_REDIS_PORT`, `MT_NEO4J_URI`, `MT_NEO4J_USER`, `MT_NEO4J_PASSWORD`.

---

## 3. Estrutura de arquivos

```
├── instalar.bat                 # 1a vez: verifica Python/Docker/Git, cria .venv, instala tudo
├── verificar_ambiente.py        # checagem chamada pelo instalar.bat (cada lib importa?)
├── executar_pipeline.bat        # sobe a infra, popula, gera o grafo e abre o Streamlit
│
├── crud_pipeline.py             # ARQUIVO ÚNICO de CRUD (MongoDB + Redis)
├── graph_pipeline.py            # grafo de conhecimento + GDS (Neo4j)
├── grafo_visual.py               # ARQUIVO ÚNICO da visualização do grafo (biblioteca constelario)
├── grafo.html                    # gerado por grafo_visual.py — 2D/3D interativo (nao versionado)
├── streamlit_app.py              # protótipo de interface (reutiliza as camadas acima)
│
├── docker-compose.pipeline.yml  # Mongo + Redis Stack + Neo4j (plugin graph-data-science)
├── requirements-pipeline.txt
│
├── docs/                         # modelagem e material de referência
│   ├── modelagem-er-simplificada.png
│   └── modelagem-json-simplificada.json
│
├── screenshots/                 # print de cada tela e de cada coleção (atividade 1.4)
│
└── logs/                        # saída de cada pipeline (evidência da entrega)
    ├── crud_pipeline_output.log
    ├── aggregation_1_leaderboard.json
    ├── aggregation_2_feature_drivers.json
    ├── collection_counts.json
    ├── collections_samples.json
    ├── graph_pipeline_output.log
    ├── graph_export.json           # grafo completo (nós+arestas+propriedades GDS)
    ├── graph_gds_top_similarity.json
    ├── graph_gds_top_pagerank.json
    └── graph_gds_communities.json
```

> A apresentação de slides é um projeto próprio (**ModelTrace-Apresentacao**), separado
> deste repositório — não faz parte do pipeline.

---

## 4. Checklist da entrega

### Requisitos principais

| # | Requisito | Onde |
|---|-----------|------|
| 1 | Protótipo de interface (funcionalidade mais importante) em Streamlit | [`streamlit_app.py`](streamlit_app.py) · [print](screenshots/mt-01-dashboard.png) |
| 2 | Criar e popular as principais coleções | `create_collections_and_indexes()` + `seed_*()` |
| 3 | Telas e uso de INSERT, FIND, UPDATE, DELETE | telas Streamlit + `crud_pipeline.py` (FASE 4) |
| 4 | Print de cada tela e cada coleção num diretório do repositório | [`screenshots/`](screenshots/) |
| 5 | Grafo de conhecimento + operação(ões) GDS para funcionalidade relevante | [`graph_pipeline.py`](graph_pipeline.py) · [seção 6](#6-grafo-de-conhecimento--neo4j-graph-data-science) |

### Aggregation pipelines (2, para funcionalidades distintas)

Operadores usados no conjunto: `$match`, `$group`, `$set`/`$addFields`, `$lookup`,
`$unwind`, `$project`, `$sort`, `$merge`, `$sample`, `$facet`, `$limit`, `$count`.

- **Pipeline 1 — Leaderboard de modelos** (`agg_model_leaderboard`)
  Ranqueia modelos/versões por F1 a partir do feedback real e **materializa** o
  resultado em `metrics_snapshots` via `$merge`.
  Estágios: `$match → $group → $set → $lookup → $unwind → $project → $sort → $merge`.
  Resultado: [`logs/aggregation_1_leaderboard.json`](logs/aggregation_1_leaderboard.json)

- **Pipeline 2 — Drivers de risco** (`agg_feature_drivers`)
  Descobre quais *features* mais empurram a decisão para "risco alto" e traz uma
  amostra auditável aleatória com as notas da entidade.
  Estágios: `$match → $facet[ $unwind → $group → $set → $sort → $limit → $project | $sample → $lookup → $project | $count ]`.
  Resultado: [`logs/aggregation_2_feature_drivers.json`](logs/aggregation_2_feature_drivers.json)

### Redis — estruturas comuns e probabilísticas

| Tipo | Estrutura | Recurso implementado |
|------|-----------|----------------------|
| Comum | String/JSON + TTL | cache do dashboard (`SET/GET EX`) |
| Comum | Hash | contadores ao vivo por modelo (`HINCRBY`) |
| Comum | Sorted Set | ranking de entidades por risco (`ZADD/ZREVRANGE`) |
| Comum | List | stream das últimas predições (`LPUSH/LTRIM`) |
| Comum | Counter | rate limit por API key (`INCR + EXPIRE`) |
| **Probabilística** | HyperLogLog | entidades únicas avaliadas (`PFADD/PFCOUNT`) |
| **Probabilística** | Bloom Filter | idempotência por `request_id` (`BF.ADD/BF.EXISTS`) |
| **Probabilística** | Count-Min Sketch | frequência aproximada por entidade (`CMS.INCRBY/QUERY`) |
| **Probabilística** | Top-K | entidades mais avaliadas / heavy hitters (`TOPK.ADD/LIST`) |

---

## 5. Coleções principais

`organizations`, `users`, `projects`, `models`, `model_versions`, **`predictions`**
(central), `metrics_snapshots`, `entity_notes`, `audit_events`.

A coleção **`predictions`** é o documento agregado: embute `entity`, `features`
(mapa livre por modelo), `prediction`, `explanations` (array), `decision`,
`feedback`, `flags` e `metadata` — modelo documental clássico, onde "o que está
dentro do que" substitui várias tabelas relacionais.

Prints de cada coleção com amostra de documento:
**[`screenshots/mt-09-collections-gallery.png`](screenshots/mt-09-collections-gallery.png)**.

---

## 6. Grafo de conhecimento — Neo4j Graph Data Science

Última atividade da entrega: um **grafo das entidades reais do banco** (organização,
projetos, modelos, versões, entidades avaliadas, predições, features e outcomes — não o
código/projeto) com **3 operações GDS encadeadas** implementando uma única funcionalidade:

> **"Radar de Casos Similares"** — dada uma entidade sinalizada como risco, o investigador
> enxerga (1) os casos mais parecidos com ela pelos mesmos fatores de risco, (2) a que
> cluster de padrão de risco ela pertence e (3) quais nós são mais influentes no grafo
> inteiro. É o complemento *multi-hop* do aggregation pipeline 2 (drivers de risco), que é
> agregação plana e não enxerga relação entre entidades.

### Esquema do grafo

```
(:Organization)-[:OWNS]->(:Project)-[:HAS_MODEL]->(:Model)-[:HAS_VERSION]->(:ModelVersion)
(:ModelVersion)-[:PRODUCED]->(:Prediction)-[:FOR_ENTITY]->(:Entity)
(:Prediction)-[:DRIVEN_BY {impact, rank}]->(:Feature)
(:Prediction)-[:CLASSIFIED_AS]->(:Outcome)              # TP / FP / TN / FN / PENDING
(:Entity)-[:RISK_FACTOR {weight}]->(:Feature)            # agregado, usado pelo GDS
(:Entity)-[:SIMILAR_TO {score}]->(:Entity)                # escrito pelo gds.nodeSimilarity
```

350 nós · 2.199 arestas · 7 comunidades (dados fictícios, mesmo tema dos 3 projetos:
educação/industrial/econômico) — gerados por [`graph_pipeline.py`](graph_pipeline.py).

### Operações GDS

| # | Algoritmo | Projeção | Escreve | Funcionalidade |
|---|-----------|----------|---------|-----------------|
| 1 | `gds.nodeSimilarity` | `Entity` ↔ `Feature` via `RISK_FACTOR` | `(:Entity)-[:SIMILAR_TO {score}]->(:Entity)` | casos parecidos (Jaccard, topK=5) |
| 2 | `gds.louvain` | `Entity` + `SIMILAR_TO` | `Entity.community_id` | clusters de padrão de risco |
| 3 | `gds.pageRank` | grafo completo | `<label>.pagerank` | nós mais influentes ("God Nodes" do risco) |

```python
CALL gds.graph.project('entity-feature', ['Entity','Feature'], 'RISK_FACTOR')
CALL gds.nodeSimilarity.write('entity-feature', {
  writeRelationshipType: 'SIMILAR_TO', writeProperty: 'score', topK: 5, similarityCutoff: 0.1
}) YIELD nodesCompared, relationshipsWritten
```

Resultado real ([`logs/graph_gds_top_similarity.json`](logs/graph_gds_top_similarity.json),
[`logs/graph_gds_top_pagerank.json`](logs/graph_gds_top_pagerank.json),
[`logs/graph_gds_communities.json`](logs/graph_gds_communities.json)):

- 500 pares `SIMILAR_TO` escritos · **7 comunidades** (modularidade 0,68 — o Louvain
  redescobre sozinho a separação por domínio: educação/industrial/econômico).
- Nós mais influentes por `pageRank`: as **features** (`qtd_reprovacoes`, `tipo_ingresso`,
  `nota_media`, ...) — fazem sentido como hub estrutural, já que toda predição de risco
  aponta pra elas via `DRIVEN_BY`/`RISK_FACTOR`.

### Visualização interativa 2D/3D

[`grafo.html`](grafo.html) — página autocontida (sem servidor),
também embutida na aba **Grafo** do Streamlit. Inspirada na visualização do
[graphify](https://github.com/safishamsi/graphify) (busca, legenda clicável, painel de
inspeção ao clicar num nó) e no layout tipo "árvore de talentos" (constelação radial,
ícones por tipo de nó, trilhas que acendem ao passar o mouse):

- **Toggle 2D/3D** (`vis-network` e `3d-force-graph`, mesmo grafo embutido nos dois).
- Tamanho do nó proporcional ao **grau** (nº de arestas); cor por **tipo**, **domínio** ou
  **comunidade** (coloração de grafos: comunidades vizinhas nunca recebem a mesma cor).
  A cor da comunidade vale tanto para os nós quanto para as arestas entre eles.
  Ícones ([Lucide](https://lucide.dev), licença ISC) por tipo de nó/entidade.
- Busca, legenda (ordenada por quantidade de nós, com contagem), painel de inspeção ao
  clicar (propriedades, grau, pagerank, comunidade, vizinhos clicáveis e — para entidades —
  os casos mais similares), botão "isolar vizinhança".
- Painéis com os resultados reais do GDS: top casos similares, nós mais influentes,
  comunidades.

Prints: [mt-10-graph-2d.png](screenshots/mt-10-graph-2d.png) ·
[mt-11-graph-nodeinfo.png](screenshots/mt-11-graph-nodeinfo.png) ·
[mt-12-graph-3d.png](screenshots/mt-12-graph-3d.png) ·
[mt-13-graph-community.png](screenshots/mt-13-graph-community.png) ·
[mt-14-streamlit-grafo-tab.png](screenshots/mt-14-streamlit-grafo-tab.png).

---

## 7. Prints (telas e coleções)

| Tela | Print |
|------|-------|
| Dashboard (KPIs + leaderboard) | [mt-01-dashboard.png](screenshots/mt-01-dashboard.png) |
| INSERT (form) / resultado | [mt-02-insert.png](screenshots/mt-02-insert.png) · [mt-02b-insert-result.png](screenshots/mt-02b-insert-result.png) |
| FIND (filtro + inspector) | [mt-03-find.png](screenshots/mt-03-find.png) |
| UPDATE (feedback / escalar) | [mt-04-update.png](screenshots/mt-04-update.png) |
| DELETE | [mt-05-delete.png](screenshots/mt-05-delete.png) |
| Aggregations (pipelines 1 e 2) | [mt-06-aggregations.png](screenshots/mt-06-aggregations.png) |
| Redis (comuns + probabilísticas) | [mt-07-redis.png](screenshots/mt-07-redis.png) |
| Collections (navegador) | [mt-08-collections-predictions.png](screenshots/mt-08-collections-predictions.png) |
| **Todas as coleções + amostra** | [mt-09-collections-gallery.png](screenshots/mt-09-collections-gallery.png) |
| Grafo 2D / inspeção / 3D / comunidades | [mt-10](screenshots/mt-10-graph-2d.png) · [mt-11](screenshots/mt-11-graph-nodeinfo.png) · [mt-12](screenshots/mt-12-graph-3d.png) · [mt-13](screenshots/mt-13-graph-community.png) |
| Aba "Grafo" no Streamlit | [mt-14-streamlit-grafo-tab.png](screenshots/mt-14-streamlit-grafo-tab.png) |

---

## 8. Apresentação

Abra [`docs/apresentacao.html`](docs/apresentacao.html) no navegador (setas `←` `→` para navegar,
ou clique nas laterais). Mostra, em ~11 slides, o código de cada parte do pipeline
MongoDB/Redis com os resultados reais.

Uma apresentação mais completa, cobrindo **as 6 atividades** (incluindo o grafo/GDS),
está publicada em GitHub Pages:
**[diegoxavier-hub.github.io/modeltrace-apresentacao](https://diegoxavier-hub.github.io/modeltrace-apresentacao/)**
(repositório próprio: [modeltrace-apresentacao](https://github.com/DiegoXavier-hub/modeltrace-apresentacao),
gerado a partir da pasta `apresentacao/` na raiz deste projeto, que fica fora deste git).
