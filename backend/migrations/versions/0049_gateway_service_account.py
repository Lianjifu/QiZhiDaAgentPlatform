"""Gateway 服务账号物化：channels 加 ``service_account`` 列。

依据：docs/architecture/session-lifecycle.md
（台账 **G3**：``dispatch_subscriber.py`` 的硬编码 ``SYSTEM_USER_ID`` /
``SYSTEM_AGENT_ID``）。

- IM 的 actor 此前是**代码里的全局常量** —— 所有租户、所有渠道共用同一个身份。
  服务账号是**渠道的属性**，因此落在渠道行上，而不是常量里。
- 列是 JSON，形状 ``{"user_id": ..., "agent_id": ..., "agent_version": ...}`` ——
  与 ``outbound_config`` 同一层级的「渠道自带的配置」，不新建表。

⚠️ **回填**：把既有的全局身份**物化**进每一条渠道行 —— 否则升级后所有存量
渠道立刻失去服务账号，IM 入站全线中断。此后每个渠道的服务账号独立可配。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049_gateway_service_account"
down_revision: str | Sequence[str] | None = "0048_memory_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column("service_account", sa.JSON(), nullable=True),
    )
    # 物化旧常量 —— 存量渠道不因这次升级而失去服务账号。
    op.execute(
        sa.text(
            """
            UPDATE channels
               SET service_account = jsonb_build_object(
                       'user_id', '00000000-0000-0000-0000-00000000c0c0',
                       'agent_id', '00000000-0000-0000-0000-00000000c0c1',
                       'agent_version', 'channel-router-1.0.0')
             WHERE service_account IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column("channels", "service_account")
