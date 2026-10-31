"""**knowledge 承接 L3 的语义** ✓（台账 **X15** ✓ —— 决策 #1 ✓ —— **M-47** ✓）。

⚠️ **这一步是「先上新」** ✓ —— 表**还没删** ✓（删表是 **0059** ✓）→
两套并存的那段时间里 **knowledge 已经能装团队知识** ✓。

⚠️ **为什么 knowledge 要加这几列** ✓：

- ``category``（类别）✓ —— L3 有（自由文本 ✓ —— 「话术」/「术语表」/「规范」✓），
  knowledge 的 ``type`` 是**枚举** ✓（``manual`` / ``policy`` / … ✓）→ 装不下 ✓；
- ``publish_state``（发布态）✓ —— L3 的 ``draft`` / ``published`` / ``retired`` ✓
  与 knowledge 的 ``status``（**处理**状态 ✓ —— ``parsed`` / ``parsing`` / … ✓）
  **不是一根轴** ✓ → 另立一列 ✓（不要拿处理状态冒充发布态 ✗✗）；
- ``contributor``（贡献者）✓ —— L3 有 ✓；knowledge 的 ``owner`` 在 **KB** 上 ✓
  → 文档级还要知道自己是谁写的 ✓；
- ``origin``（来源）✓ —— **迁移痕迹** ✓ —— 「这条文档是从 L3 迁来的」✓
  —— **downgrade 要靠它把行还原回去** ✓（不然会把普通知识文档也当成 L3 行 ✗✗）。

⚠️ **L3 → knowledge 的映射** ✓：

| L3 | knowledge | 说明 |
|---|---|---|
| ``team`` | **KB**（一个团队一个库 ✓） | KB 有 ``scope``（部门 ✓）与 ``owner`` ✓ |
| ``title`` | ``docs.name`` | ✓ |
| ``summary`` | **chunk 正文** ✓ + ``chunks_preview`` | ✓ |
| ``category`` | ``docs.category`` | ✓ |
| ``status`` | ``docs.publish_state`` | ✓ |
| ``contributor`` | ``docs.contributor`` + ``kb.owner`` | ✓ |
| ``promoted_from_l2_ids`` | ``docs.source_id``（逗号串 ✓） | 与 knowledge 现有的提升口径一致 ✓ |
| ``hits`` / ``hits_trend`` | **不迁** ✓ | 那是 L3 自己的**运行时统计** ✓ —— 退役后**没有执行者** ✓ → 留着就是死数据 ✗✗ |

⚠️ **文档 id 沿用 L3 的 id** ✓ —— 这样「谁引用过这条」**不用重连** ✓
（前端 / agent 绑定里的 id 仍指得到 ✓）—— 也让 downgrade 能**原样还原** ✓。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0058_knowledge_absorb_l3"
down_revision: str | Sequence[str] | None = "0057_memory_retire_l1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_knowledge_docs",
        sa.Column("category", sa.String(64), nullable=False, server_default=sa.text("''")),
    )
    op.add_column(
        "admin_knowledge_docs",
        sa.Column(
            "publish_state",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'published'"),
        ),
    )
    op.add_column(
        "admin_knowledge_docs",
        sa.Column("contributor", sa.String(128), nullable=False, server_default=sa.text("''")),
    )
    op.add_column(
        "admin_knowledge_docs",
        sa.Column("origin", sa.String(16), nullable=False, server_default=sa.text("'manual'")),
    )

    # ⚠️ **先建 KB** ✓ —— 一个团队一个库 ✓（KB 名 = team ✓）。
    # ⚠️ **ON CONFLICT DO NOTHING** ✓ —— 同名的库可能已经有了 ✓（演示种子 ✓）
    # → **复用它** ✓（不覆盖 ✓ —— 那会把真知识冲掉 ✗✗）。
    op.execute(
        """
        INSERT INTO admin_knowledge_kbs (
            id, tenant_id, workspace_id, name, description, owner, scope, status,
            created_at, updated_at
        )
        SELECT
            gen_random_uuid(), tenant_id, workspace_id, team, '', max(contributor), '部门', 'indexed',
            now(), now()
        FROM admin_memory_l3
        GROUP BY tenant_id, workspace_id, team
        ON CONFLICT (tenant_id, workspace_id, name) DO NOTHING
        """
    )

    # ⚠️ **文档 id 沿用 L3 的 id** ✓（见模块 docstring ✓）。
    op.execute(
        """
        INSERT INTO admin_knowledge_docs (
            id, tenant_id, workspace_id, kb_id, name, type, status, source_id,
            size_kb, chunks, citations, chunks_preview,
            category, publish_state, contributor, origin, created_at, updated_at
        )
        SELECT
            l3.id,
            l3.tenant_id,
            l3.workspace_id,
            kb.id,
            l3.title,
            'manual',
            'parsed',
            left(
                coalesce(
                    (
                        SELECT string_agg(item, ',')
                        FROM jsonb_array_elements_text(l3.promoted_from_l2_ids) AS item
                    ),
                    ''
                ),
                64
            ),
            greatest(1, length(l3.summary) / 1024),
            1,
            0,
            jsonb_build_array(
                jsonb_build_object(
                    'index', 0, 'snippet', l3.summary, 'citations', 0, 'tokens', 0,
                    'heading', l3.title
                )
            ),
            l3.category,
            l3.status,
            l3.contributor,
            'memory_l3',
            l3.created_at,
            l3.updated_at
        FROM admin_memory_l3 AS l3
        JOIN admin_knowledge_kbs AS kb
          ON kb.tenant_id = l3.tenant_id
         AND kb.workspace_id = l3.workspace_id
         AND kb.name = l3.team
        """
    )

    # ⚠️ **正文进 chunk** ✓ —— 检索走的就是 chunk ✓（knowledge 的召回路径 ✓）。
    op.execute(
        """
        INSERT INTO admin_knowledge_chunks (
            id, tenant_id, workspace_id, kb_id, doc_id, ordinal, heading, content,
            tokens, created_at, updated_at
        )
        SELECT
            gen_random_uuid(), l3.tenant_id, l3.workspace_id, kb.id, l3.id, 0,
            l3.title, l3.summary, 0, l3.created_at, l3.updated_at
        FROM admin_memory_l3 AS l3
        JOIN admin_knowledge_kbs AS kb
          ON kb.tenant_id = l3.tenant_id
         AND kb.workspace_id = l3.workspace_id
         AND kb.name = l3.team
        """
    )


def downgrade() -> None:
    # ⚠️ **L3 表这时还在** ✓ —— 删表是 **0059** ✓（所以这里**不建表** ✓
    # —— 建了就撞车 ✗✗）。
    op.execute("DELETE FROM admin_memory_l3")

    # ⚠️ **只还原 origin='memory_l3' 的文档** ✓ —— 普通知识文档**不是 L3 行** ✗✗。
    op.execute(
        """
        INSERT INTO admin_memory_l3 (
            id, tenant_id, workspace_id, team, title, summary, category, hits,
            contributor, status, hits_trend, promoted_from_l2_ids, created_at, updated_at
        )
        SELECT
            d.id,
            d.tenant_id,
            d.workspace_id,
            kb.name,
            d.name,
            coalesce(chunk.content, ''),
            d.category,
            0,
            d.contributor,
            d.publish_state,
            '[]'::jsonb,
            coalesce(
                (
                    SELECT to_jsonb(array_agg(item::uuid))
                    FROM unnest(string_to_array(d.source_id, ',')) AS item
                    WHERE item <> ''
                ),
                '[]'::jsonb
            ),
            d.created_at,
            d.updated_at
        FROM admin_knowledge_docs AS d
        JOIN admin_knowledge_kbs AS kb ON kb.id = d.kb_id
        LEFT JOIN admin_knowledge_chunks AS chunk
          ON chunk.doc_id = d.id AND chunk.ordinal = 0
        WHERE d.origin = 'memory_l3'
        """
    )

    op.drop_column("admin_knowledge_docs", "origin")
    op.drop_column("admin_knowledge_docs", "contributor")
    op.drop_column("admin_knowledge_docs", "publish_state")
    op.drop_column("admin_knowledge_docs", "category")
