# channel — 渠道接入

> 能力域之一。负责飞书 / 企业微信 / 钉钉 / Web / API 五类渠道的入站消息归一化与出站回复投递。

## 职责

- 渠道的注册、配置与状态管理
- **入站**：webhook 验签 → 解密 → 归一化成 `InboundMessage` → 交给 Gateway 驱动对话
- **出站**：把结果编码成各平台的消息格式 → 投递 → 记录投递状态
- 服务账号物化：渠道消息以登记的服务账号身份发起对话

## 源码位置

```
backend/modules/channel/src/qzdap/modules/channel/
├── domain/          entities.py（Channel · ChannelDelivery）· events.py
├── application/     services.py（ChannelService）· ports.py
└── adapter/
    ├── http/         router.py
    ├── persistence/  models.py · repositories.py
    ├── inbound/      feishu.py · dingtalk.py · wechatwork.py · web.py · api.py
    ├── outbound/     feishu.py · wechatwork.py · dingtalk.py · web.py · encoder.py · result_sink.py · channel_outbox_dispatcher.py
    ├── crypto/       webhook_cipher.py（AES-GCM 加密 webhook secret）
    └── dispatch/     channel_turn_dispatcher.py（渠道侧驱动一轮对话）
```

## HTTP 端点

前缀 `/v1`。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/v1/channels` | 渠道列表 |
| POST | `/v1/channels` | 注册渠道 |
| GET | `/v1/channels/{id}` | 渠道详情 |
| PATCH | `/v1/channels/{id}` | 更新渠道 |
| POST | `/v1/channels/{id}/webhook` | **入站 webhook**（返回 202，异步处理） |
| POST | `/v1/channels/{id}/send` | **出站发送** |

## 数据表

| 表 | 职责 | 关键列 |
|---|---|---|
| `channels` | 渠道定义 | id / tenant_id / type / status / inbound_config / outbound_config / **service_account**(JSONB) |
| `channel_deliveries` | 投递记录 | id / channel_id / external_message_id / status / payload / error / delivered_at |
| `channel_secrets` | webhook 密钥（加密存） | channel_id / encrypted_secret / key_version |

## 关键类

| 层 | 类 | 职责 |
|---|---|---|
| domain | `Channel` `ChannelDelivery` | 聚合根；值对象 `ChannelStatus` / `DeliveryStatus` |
| application | `ChannelService` | 注册 / 列表 / 状态 / handle_webhook / send_reply |
| application | `ChannelRepository` `ChannelDeliveryRepository` `WebhookSecretRepository` `WebhookSecretCipher` `OutboundAdapter` `ChannelEventPublisher` | 端口 |
| adapter | `AesGcmWebhookCipher` | webhook secret 加密 |
| adapter | `channel_turn_dispatcher` | 解码 → 取服务账号 → 跑一轮 → 出站投递 |

## 实现要点

- **入站签名验签是真实现**：飞书 / 企微 / 钉钉三套各自按平台规范验签与解密——钉钉走 Stream v2 的 AES-CBC，企微走 AES 解密 + base64 拼接
- **服务账号物化**：`channels.service_account` JSONB 列（迁移 0049）取代了早期硬编码的 `SYSTEM_USER_ID` / `SYSTEM_AGENT_ID`。**渠道没登记服务账号就不跑这一轮**，并留错误日志
- **入站统一走 `Gateway.accept`**：五个渠道经同一个门面归一化，除 `channel_type` / `raw_metadata` 外字段完全一致
- **幂等在 `session_inbox`**：跨进程可见的原子 claim，替代了原先进程内 LRU 去重
- **出站走 outbox**：结果先进 outbox，由 `channel_outbox_dispatcher` 异步投递，投递状态落 `channel_deliveries`
- **webhook secret 加密**：用 AES-GCM，主密钥同模型凭据那套 `QZDAP_*_REF` 解析链

## 已知边界

- ⚠️ `adapter/outbound/result_sink.py:97` 的 `replay()` **明确抛 `NotImplementedError`**——出站重放未实现
- ⚠️ 钉钉 / 企微**解密失败时回落 `_placeholder`**（`dingtalk.py:131`、`wechatwork.py:136`）——静默降级而不是报错，排查困难
- ⚠️ `adapter/http/router.py` 底部的 `_tenant_from_channel` 是**遗留 helper，直接 raise RuntimeError**
- ⚠️ 出站适配器在 boot 时携带**空占位凭据**，须从 `channels.outbound_config` 读取——凭据装配不完整
- ⚠️ `adapter/outbound/encoder.py:97` 留有「Session 方案 Stage 5 的未接管行」标记
