# 企智搭 · 智能体平台 · 新项目蓝图澄清

> 修正日期：2026-09-19
> **澄清**：qizhida-agent-platform 是**全新项目**（greenfield），不是对现有 `backend/` `frontend/` 的重构。

---

## 1. 关系澄清

| 路径 | 含义 |
|---|---|
| `backend/` `frontend/` | **旧项目遗留代码**（Go+Python+React）；保留作为**契约参考**与**业务灵感来源** |
| `docs/qizhida-agent-platform/` | **新项目方案**（独立仓库或独立目录规划）；4D 架构从头设计 |

**两个项目无强绑定关系**：
- 新项目可以借鉴旧项目的业务模型（如 Skill / Tool / Knowledge 等概念）
- 新项目**不继承**旧项目的技术栈（不沿用 Go monolith / `@de/*` / axios / shadcn-ui）
- 新项目**不沿用**旧项目的 API 设计（不沿用 `/api/*` 信封）

---

## 2. 新项目的核心决策（与旧项目无关）

### 2.1 后端栈选择

| 选项 | 优势 | 决策 |
|---|---|---|
| **Python FastAPI** | 文档已写；AI/ML 生态；异步友好 | ✅ **采用** |
| Go monolith | 性能 | ❌ 旧项目栈，不继承 |
| Node.js (NestJS) | 与前端同语言 | ❌ 不选 |

### 2.2 前端栈选择

| 选项 | 优势 | 决策 |
|---|---|---|
| **pnpm + FSD + DDD + Hex（4D）** | 文档化强；架构清晰 | ✅ **采用** |
| Next.js + RSC | SSR 简单 | ❌ 与 4D 冲突 |
| CRA | 简单 | ❌ 旧时代 |

### 2.3 包命名（`@qzdap/*`）

| 选择 | 理由 |
|---|---|
| **`@qzdap/*` 前缀** | Enterprise OS 缩写；区别于旧项目 `@de/*`（Digital Employee） |

### 2.4 UI 库

| 选择 | 理由 |
|---|---|
| **antd** | 中后台完整组件库；企业级；与中文字体兼容好 |
| shadcn/ui | 灵活 | ❌ 不选（企业级中后台需要 antd 全套） |

---

## 3. 新旧项目边界

```
┌─────────────────────────────────────────┐
│          旧项目（backend/ frontend/）     │
│  - Go + Python + React @de/*             │
│  - 业务已运行多年                          │
│  - 仅作为新项目的业务灵感来源               │
└─────────────────────────────────────────┘
                  ↓ 借鉴业务模型
┌─────────────────────────────────────────┐
│    新项目（qizhida-agent-platform/）         │
│  - Python FastAPI + 4D 前端 @qzdap/*        │
│  - 从 0 开始设计                           │
│  - 文档完整定义 13 节架构                  │
└─────────────────────────────────────────┘
```

---

## 4. 文档立场确认

**`docs/qizhida-agent-platform/{backend,web}/` 13 节文档**：

- ✅ 是新项目的**目标态架构定义**（不是对现状的描述）
- ✅ 不依赖旧项目代码；可以从 0 实施
- ✅ 仅借鉴旧项目的**业务概念**（Skill / Tool / Knowledge 等）
- ⚠️ 与旧项目**不共享**任何代码或配置

---

## 5. 旧项目参考用法

可在以下场景使用旧项目：

| 场景 | 用法 |
|---|---|
| 业务模型 | 参考 Skill / Tool / Memory / Channel 等概念 |
| 数据模型 | 参考业务实体字段（如 Agent 有哪些属性） |
| API 形态 | 不参考（旧项目用信封式；新项目用严格状态码） |
| 部署架构 | 不参考（旧项目 Go；新项目 Python） |

---

## 6. 新项目实施起点

新项目仓库结构（建议）：

```
qizhida-agent-platform/         ← 新独立仓库（或新目录）
├── backend/                  ← Python FastAPI + 模块化单体
│   ├── modules/
│   │   ├── agent_runtime/
│   │   ├── session/
│   │   ├── skill/
│   │   ├── tool/
│   │   ├── knowledge/
│   │   ├── memory/
│   │   ├── governance/
│   │   └── identity/
│   ├── shared/
│   └── main.py
├── web/                      ← pnpm + FSD + DDD + Hex
│   ├── packages/
│   │   ├── web-api/         # @qzdap/web-api
│   │   ├── web-mock/        # @qzdap/web-mock
│   │   ├── web-types/       # @qzdap/web-types
│   │   ├── web-hooks/       # @qzdap/web-hooks
│   │   ├── web-ui/          # @qzdap/web-ui
│   │   └── web-utils/       # @qzdap/web-utils
│   └── src/
│       └── features/<8 BC>/
├── docs/                     ← 即 docs/qizhida-agent-platform/
├── deploy/
├── scripts/
└── README.md
```

**与本仓库（旧项目）平行的位置**：
- 新项目仓库：`~/projects/qizhida-agent-platform/`（独立）
- 或：本仓库下新建 `qizhida-agent-platform/` 子目录（如果要求同 monorepo）

---

## 7. 文档目录最终定位

```
docs/qizhida-agent-platform/        ← 新项目方案（独立可用）
├── README.md                     ← 顶层索引
├── REVIEW.md                     ← 本文档（澄清）
├── backend/                      ← 后端 13 节方案（Python FastAPI）
│   └── 00-13 docs
└── web/                          ← 前端 13 节方案（4D 架构）
    └── 00-13 docs
```

**不引用旧项目**；**不与旧项目代码绑定**；**独立可执行**。

---

## 8. 总结

- ❌ 之前 REVIEW.md 基于"新项目 = 旧项目重构"的错误假设
- ✅ 新项目是 greenfield；与现有 `backend/` `frontend/` 无强绑定
- ✅ 13 节文档描述的是新项目的目标态架构；可直接执行
- ✅ 仅借鉴旧项目的业务概念；不沿用技术栈