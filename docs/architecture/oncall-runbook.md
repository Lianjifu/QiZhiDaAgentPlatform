# 值班手册 · 会话架构重构期间 ✓

> **什么时候用** ✓：告警响了 ✓（规则见 [`deploy/prometheus/alerts.yml`](../../deploy/prometheus/alerts.yml) ✓）—— **先看这里** ✓（别猜 ✓ —— H2 的验收 ✓）。
>
> ⚠️ **每条告警都有回退步骤** ✓ —— 「出了事怎么办」写在下面 ✓（**不用翻代码** ✓）。
>
> ⚠️ **通用回退手段**（按代价从小到大 ✓）：
>
> | 顺序 | 手段 | 代价 | 适用 |
> |---|---|---|---|
> | 1 | **关开关**（下表逐条列 ✓） | 秒级 ✓ | 有开关的 ✓ |
> | 2 | **回滚到上一个镜像 / 版本** | 分钟级 ✓ | 通用 ✓ |
> | 3 | **停后台任务**（间隔调大 ✓ —— `QZDAP_*_INTERVAL` ✓） | 秒级 ✓ | 淘汰 / 清扫 / 补写类 ✓ |
> | 4 | **数据回滚**（`alembic downgrade` ✓ —— **只在 dev / 预发** ✓） | 高 ⚠️ | **生产不许** ✗✗（S-36 的 DROP 不可逆 ✓） |

---

## 收敛闸门

### LegacyCallResurrected

- **含义** ✓：台账条目 `entry` 对应的**旧实现又被调用了** ✓（清理窗口内它必须归零 ✓）。
- **为什么重要** ✓：旧路径还在跑 = **新旧两套实现并存** ✓（这正是这次重构要消灭的东西 ✗✗）→ **不许删旧实现** ✓（删了就是删了还在用的路径 ✗✗）。
- **排查** ✓：
  ```bash
  # 哪个 entry 在涨？
  curl -s localhost:9151/metrics | grep '^qzdap_legacy_calls_total' | grep -v ' 0$'
  # 找到打点位置（打点就在旧实现的入口处 ✓）
  grep -rn "record_legacy_call(\"<entry>\")" backend/
  ```
- **回退** ✓：**不要回退** ✓ —— 这是「有人绕过了新实现」✓ → **改代码** ✓（把那个调用点切到新实现 ✓）→ 然后确认计数归零 ✓ 再删旧实现 ✓。
- **关联** ✓：台账 [`cleanup-ledger.md`](cleanup-ledger.md) ✓ · 实施计划 P-04（打点随旧实现删除逐条撤除 ✓）。

### LegacyCallNotZero

- **含义** ✓：清理窗口已到，但该 entry 的计数**仍非零** ✓。
- **排查** ✓：同上一条 ✓（先确认是「真在用」✓ 还是「进程重启前的历史计数」✓ —— counter 重启归零 ✓）。
- **回退** ✓：**不许删旧实现** ✓ → 把计数清零的判据写清楚 ✓ → 真归零了再进删除 Stage ✓。

---

## Router

### RouterSeqSnapshotDrift

- **含义** ✓：排队**兜底放行**被触发 ✓（`qzdap_router_seq_snapshot_drift_total` ✓ —— 正常**恒为 0** ✓）。
- **为什么重要** ✓：轮次终态与会话快照的更新**不在同一个事务里** ✓ → 放行时机可能早于上一轮真正结束 ✓ → 同会话并发 ✗✗。
- **排查** ✓：
  ```bash
  curl -s localhost:9151/metrics | grep qzdap_router_seq_snapshot_drift_total
  ```
  看 `qzdap_router_queue_depth`（`tenant_id` 标签 ✓）与 `qzdap_active_turns` ✓。
- **回退** ✓：**关排队** ✓ —— `QZDAP_ROUTER_QUEUE_ENABLED=0` ✓（回到旧语义「拒绝 409 `SESSION_BUSY`」✓ —— 前端已兼容 ✓）→ 重启 ✓ → 观察 ✓。

### RouterFallbackRateHigh

- **含义** ✓：路由**兜底命中率 > 20%** ✓（粘住 / 显式 / 业务线 / 标签都没命中 ✓）。
- **排查** ✓：`qzdap_router_route_total{strategy="fallback"}` ✓ → 看这些会话的 agent 配置 ✓（是没绑 agent ✓ 还是规则缺了 ✓）。
- **回退** ✓：通常**不需要回退** ✓ —— 是配置问题 ✓ → 补规则 / 补绑定 ✓（兜底本身是安全兜底 ✓ —— 不丢消息 ✓）。

### RouterConcurrencyRejected

- **含义** ✓：有轮次被**并发上限拒了** ✓（`reason=queue_full` / `queue_timeout` ✓）。
- **排查** ✓：同一会话的请求来得比处理快 ✓ → 看 `qzdap_router_queue_wait_seconds` ✓。
- **回退** ✓：调大队列 / 关闭排队 ✓（`QZDAP_ROUTER_QUEUE_ENABLED=0` ✓ → 回到 409 语义 ✓ —— **前端会看到错误** ✓ —— 与「排队中」相比是**更明确的失败** ✓）。

---

## Memory

### MemoryVectorDropped

- **含义** ✓：向量补写队列**满了** ✓（有任务被丢 ✓）。
- **为什么不是事故** ✓：丢掉的向量由**兜底补写**捡回来 ✓（`VectorizeWorker.backfill_once` ✓ —— 每 20 轮跑一次 ✓）→ **不会永久缺失** ✓。
- **排查** ✓：`qzdap_memory_vector_enqueued_total{outcome="dropped"}` ✓ 的增速 ✓ → embedding 服务慢 ✓？
- **回退** ✓：**不需要回退** ✓ → 调大 embedding 并发 / 队列容量 ✓（`VectorizeWorker(batch_size=…)` ✓ —— 属代码改动 ✓）→ 期间靠兜底补写 ✓。

### MemoryEvictionSpike

- **含义** ✓：一小时淘汰 > 50 条 ✓（`reason=ttl` / `max_items` / `storage` ✓）。
- **为什么不是事故** ✓：淘汰是**保留策略在执行** ✓（不是错误 ✓ —— 淘汰 = 置 `retired` ✓ **不物理删** ✓ —— 审计还在 ✓）。
- **排查** ✓：管理端 `/api/admin/memory/policies` ✓ 看保留天数 / 上限有没有被改 ✓。
- **回退** ✓：把保留策略调回去 ✓（管理端可改 ✓）→ 已淘汰的**不恢复** ✓（审计保留 ✓ —— 需要的话从审计里捞 ✓）。

---

## 两套栈：账号与入口（**先分清是哪一套** ✓）

⚠️ **演示数据与开发数据严格分开** ✓ —— 不共用库 ✓ / 不共用租户 ✓ / 不共用账号 ✓ / 不共用密码 ✓（数据通道分离 ✓）。

| | **开发栈（dev）** | **演示栈（demo）** |
|---|---|---|
| 前端 | `http://127.0.0.1:9152` ✓ | `http://127.0.0.1:9162` ✓ |
| 网关 | `http://127.0.0.1:9150` ✓ | 无 ✓（前端直连后端 ✓） |
| 后端 | `http://127.0.0.1:9151` ✓ | `http://127.0.0.1:9161` ✓ |
| 库 | `127.0.0.1:9153/qzdap_dev` ✓ | `127.0.0.1:9153/qzdap_demo` ✓ |
| 租户 | slug `dev` ✓（id **随机** ✓ —— `uuid4()` ✓） | slug `demo` ✓（id 固定 `00000000-…-0001` ✓） |
| 管理员 | `admin@dev.qzdap.dev` / `dev-admin-password-change-me` ✓ | `admin@acme.com` / `demo-password-change-me` ✓ |
| 成员（**用户侧** ✓） | `user@dev.qzdap.dev` / `dev-user-password-change-me` ✓（口令与管理员**不共用** ✓） | `user@acme.com` / `demo-password-change-me` ✓ |
| 其它账号 | 验收样本（**只在 dev 库** ✓）：`qa-a-admin@example.invalid` / `qa-a-user@example.invalid`（租户 `qa-tenant-a` ✓）· `qa-b-admin@example.invalid` / `qa-b-user@example.invalid`（租户 `qa-tenant-b` ✓）—— 口令一律 `qa-local-samples-only` ✓ | 无 ✓ |
| 种子内容 | 验收样本 ✓（无演示内容 ✓） | 演示智能体 5 ✓ / 工作流 3 ✓ / 知识库 ✓ / 演示会话 ✓ / 记忆 ✓ / 管理台 30 个集合 ✓ |
| LLM 供应商 | **未配** ✓ → 发一轮必然 `TURN_FAILED` ✓ | **未配** ✓ → 同左 ✓（不是回归 ✓ —— 配了才通 ✓） |

⚠️ **账号来源** ✓：`backend/composition/qzdap_app/src/qzdap/composition/settings.py` 的 `demo_*` / `dev_*` ✓ —— `backend/.env.local` 与栈脚本**都没覆盖** ✓ → 跑的就是这些默认值 ✓。

⚠️ **怎么确认自己连的是哪一套** ✓：
```bash
# 租户 slug 就是答案：demo / dev / qa-tenant-a / qa-tenant-b
curl -s -X POST http://127.0.0.1:9161/v1/identity/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@acme.com","password":"demo-password-change-me"}' \
  | python3 -c "import sys,json,base64;t=json.load(sys.stdin)['access_token'].split('.')[1];\
print(json.loads(base64.urlsafe_b64decode(t+'='*(-len(t)%4)))['tid'])"
```
⚠️ **demo 账号在 dev 栈上登录会 401** ✓（`INVALID_CREDENTIALS` ✓）—— 两套**彻底隔离** ✓。

⚠️ **两种角色进的是**不同的**页面** ✓ —— **管理员只进管理台** ✓（`/admin/*` ✓），**成员进用户侧** ✓（工作台 / 对话 / 任务 / 知识库… ✓）→ 所以**两种角色都要有账号** ✓（只有管理员就看不到用户侧长什么样 ✗✗）→ 登录页的「一键登录」按运行模式给**两个**按钮 ✓。

⚠️ **起停** ✓：`bin/qzdap-stack/run-qzdap-stack.sh`（dev ✓）/ `run-qzdap-demo-stack.sh`（demo ✓）/ 对应的 `stop-*.sh` ✓ —— **改完代码要重启** ✓（否则跑的还是旧代码 ✓）。

---

## 通用

### HttpServerErrorRateHigh

- **排查** ✓：先看**是不是刚发的版本** ✓ → `git log --oneline -5` ✓ → 看 5xx 的 route 标签 ✓。
- **回退** ✓：**回滚到上一个镜像 / 版本** ✓（最快 ✓）。

### SseFirstChunkSlow

- **含义** ✓：SSE 首块 P95 > 5 秒 ✓（用户等太久 ✓）。
- **排查** ✓：慢在**模型** ✓ 还是**上下文太大** ✓ → `qzdap_llm_tokens_total{direction="input"}` ✓ 的量级 ✓。
- **回退** ✓：调小上下文窗口 / 换快模型 ✓；**不用回滚** ✓（不是故障 ✓）。

### ActiveTurnsStuck

- **含义** ✓：在途轮次 > 20 且 15 分钟不降 ✓。
- **排查** ✓：先分清「**审批挂起**」✓（有意停在 `waiting` ✓ —— 要人去批 ✓）与「**真卡住**」✓ → 查 `session_turns.status` ✓：
  ```sql
  SELECT status, count(*) FROM session_turns
  WHERE status IN ('running','waiting','queued') GROUP BY status;
  ```
- **回退** ✓：**审批挂起** → 通知审批人 ✓（不是故障 ✓）；**真卡住** → 调大清扫间隔是反作用 ✓ —— 改用**重启 worker** ✓（`QZDAP_SESSION_SWEEPER_INTERVAL` ✓ 调大只是少扫 ✓）。

### LlmCostSpike

- **含义** ✓：一小时成本 > 50 美元 ✓（**起步阈值** ✓ —— 按真实基线调 ✓）。
- **回退** ✓：看是不是**循环没停** ✓（`qzdap_router_concurrency_rejected_total` ✓ 一起看 ✓）→ 必要时**限流** ✓。

---

## 相关文档

- 指标定义：[`backend/libs/observability/src/qzdap_observability/metrics.py`](../../backend/libs/observability/src/qzdap_observability/metrics.py) ✓
- 告警规则：[`deploy/prometheus/alerts.yml`](../../deploy/prometheus/alerts.yml) ✓
- 台账（`entry` 编号的来源）：[`cleanup-ledger.md`](cleanup-ledger.md) ✓
- 实施计划：[`cleanup-ledger.md`](./cleanup-ledger.md) ✓
