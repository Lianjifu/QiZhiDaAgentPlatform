# knowledge — 知识库与 RAG

> 能力域之一。负责知识库的文档、分块、向量索引、检索与召回，以及知识源的同步。

## 职责

- 知识库（KB）的创建、查询、启停
- 文档的增删改查与**分块 + 向量化 + 入库**
- **RAG 检索**：向量优先 + 关键词兜底，支持按分淘汰
- 知识源的登记与同步
- 记忆的 L2 事实**晋升到知识库**（承接 memory 模块）

## 源码位置

```
backend/modules/knowledge/src/qzdap/modules/knowledge/
├── domain/          entities.py（KnowledgeBase · KnowledgeDoc · DocChunk · IndexedChunk · KnowledgeSource · KnowledgeTask · KnowledgeEvalCase）
├── application/
│   ├── services.py        KnowledgeService（唯一门面）
│   ├── chunker.py         split_text（默认 800 字 / 重叠 80）
│   ├── ports.py           EmbeddingPort · VectorSearchPort · KnowledgeCatalogRepository
│   └── evaluator.py       检索评估
└── adapter/
    ├── http/         router.py
    ├── persistence/  models.py · repositories.py · vector_adapter.py（PgKnowledgeVectorAdapter）
    └── promotion.py        KnowledgeCandidateAdapter（承接 memory 的晋升）
```

## HTTP 端点

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/admin/knowledge/kbs` | 知识库列表 |
| POST | `/api/admin/knowledge/kbs` | 建知识库 |
| POST | `/api/admin/knowledge/kbs/__batch__` | 批量建 |
| GET | `/api/admin/knowledge/kbs/{kb_id}` | 知识库详情 |
| POST | `/api/admin/knowledge/kbs/{kb_id}/toggle-status` | 启停 |
| GET | `/api/admin/knowledge/docs` | 文档列表 |
| POST | `/api/admin/knowledge/docs` | 建文档 |
| GET | `/api/admin/knowledge/docs/{doc_id}` | 文档详情 |
| PATCH | `/api/admin/knowledge/docs/{doc_id}` | 更新文档 |
| GET | `/api/admin/knowledge/sources` | 知识源列表 |
| POST | `/api/admin/knowledge/sources` | 登记知识源 |
| POST | `/api/admin/knowledge/sources/{source_id}/sync` | 同步知识源 |
| GET | `/api/admin/knowledge/tasks` | 索引任务列表 |
| GET | `/api/admin/knowledge/eval` | 评测用例 |
| GET | `/api/catalog/knowledge` | 用户侧目录 |
| POST | `/api/catalog/knowledge/{doc_id}/favorite` | 收藏 |
| **POST** | **`/api/catalog/knowledge/ask`** | **提问（RAG 检索）** |
| GET | `/api/knowledge/docs` | 文档列表（用户侧） |

## 数据表

| 表 | 职责 | 关键列 |
|---|---|---|
| `admin_knowledge_kbs` | 知识库 | id / tenant_id / name / status / embedding_model |
| `admin_knowledge_docs` | 文档 | id / kb_id / title / source / status / published |
| `admin_knowledge_chunks` | 分块正文 | id / doc_id / ordinal / heading / content |
| `admin_knowledge_sources` | 知识源 | id / type / config / last_sync_at / status |
| `admin_knowledge_doc_user_state` | 用户对文档的个人状态 | doc_id / user_id / favorite |
| `admin_knowledge_tasks` | 索引任务 | id / doc_id / status / error |
| `admin_knowledge_eval_cases` | 评测用例 | id / kb_id / query / expected |

向量本身存在 **pgvector** 的 `admin_knowledge_vec` 表，payload 带 `kb_id` / `doc_id` / `ordinal` / `heading`，保证召回可追溯到原文位置。

## 关键类

| 层 | 类 | 职责 |
|---|---|---|
| domain | `KnowledgeBase` `KnowledgeDoc` `DocChunk` `IndexedChunk` `KnowledgeSource` `KnowledgeTask` `KnowledgeEvalCase` | 聚合根 |
| application | `KnowledgeService` | **唯一门面**：ingest_doc / sync_source / ask / search_query |
| application | `split_text` | 分块（800 字，重叠 80） |
| adapter | `PgKnowledgeVectorAdapter` | 包 `qzdap_vector.pg_vector.PgVectorStore` |
| adapter | `KnowledgeCandidateAdapter` | 承接 memory 的 L2 晋升，落成 KB 候选文档 |

## 实现要点

- **检索是混合的**：`services.py:397` → `embedding.embed` → `vectors.search`（向量）→ `_drop_unpublished`（丢弃草稿命中）→ `_keyword_hits`（关键词兜底）→ `_merge_hits` 混合打分
- **召回结果可追溯**：每个命中带原文链接（doc_id + ordinal + heading）
- **权限隔离**：知识库按工作区授权，检索时按 agent 的 `knowledge_refs` 约束可见范围
- **自动注入上下文**：agent 配置里的 `knowledge_refs` → `graph/runner.py:1437 _knowledge_package_ids`（只取 enabled）→ `KnowledgeSearchPort.search` → 由 `ContextBuilder` 以 system 段注入（TOP_K = 6），同时另发 `knowledge_search` chunk
- **降级可见**：召回失败会置 `recall_degraded` 标记，透传到每一块 chunk 的 `flags`，前端据此提示用户回答可能不完整

## 已知边界

- ⚠️ **没有嵌入供应商时，整条向量检索降级为关键词**：`EmbeddingPort` 未配置时装的是 `UnavailableEmbeddingAdapter`，调用直接 503（开发环境也拦），不会静默返回零向量
- ⚠️ `admin_knowledge_tasks` / `admin_knowledge_eval_cases` **只有 list API，没有真正跑任务 / 跑评测的端点**——索引与评测的执行入口缺失
- ⚠️ `/api/catalog/knowledge/__noop__/ask` 是给前端预留的隐藏别名，与主路径行为一致
- ⚠️ 知识源同步的「拉取源内容」依赖各源类型的适配实现，未覆盖的源类型会失败而不是降级
