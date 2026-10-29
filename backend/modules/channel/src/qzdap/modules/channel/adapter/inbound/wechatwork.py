"""WeChat Work (企业微信) inbound adapter — parses Wecom callback events.

Wecom delivers three kinds of messages to the configured callback URL:

- **Encrypted JSON v2 stream events**: ``{"encrypt":"<base64>"}``
  whose body is AES-256-CBC encrypted using ``EncodingAESKey`` (43
  chars, base64-padded to 32 bytes; IV = first 16 bytes of the key).
  Decrypted plaintext is an XML envelope. With ``encoding_aes_key``
  configured the adapter decrypts and parses normally; otherwise it
  returns a placeholder (legacy behaviour).
- **Plain JSON v2 stream events** (rare; admin tool debug pings):
  ``{"msgtype":"text",...}``.
- **Legacy XML v1 callbacks**: ``<xml>...</xml>`` envelopes used by
  older apps + GET URL verification challenge.
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any

from qzdap.modules.channel.adapter.inbound._base import (
    build_inbound_message,
    object_storage_attachment,
)
from qzdap_agent_runtime.gateway.types import (
    AttachmentRef,
    ChannelType,
    InboundMessage,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from qzdap_agent_runtime.gateway.normalizer import NormalizerContext


class WeChatWorkInboundAdapter:
    """③ 的企微实现 —— 产出标准 :class:`InboundMessage`。"""

    channel_type = ChannelType.WECHATWORK

    def __init__(self, *, encoding_aes_key: str = "") -> None:
        # EncodingAESKey is 43 base64 chars; the 32-byte key is
        # derived by base64-decoding with the missing padding
        # appended (``==``). Empty key keeps the legacy placeholder
        # behaviour.
        self._aes_key: bytes | None = None
        self._aes_iv: bytes | None = None
        if encoding_aes_key:
            try:
                pad = (4 - len(encoding_aes_key) % 4) % 4
                key = base64.b64decode(encoding_aes_key + "=" * pad)
                if len(key) == 32:
                    self._aes_key = key
                    self._aes_iv = key[:16]
            except Exception:
                # Invalid key — leave as None; we silently keep the
                # placeholder behaviour so a misconfiguration never
                # crashes the boot path.
                self._aes_key = None
                self._aes_iv = None

    def normalize(
        self,
        *,
        body: bytes,
        headers: Mapping[str, str],
        context: NormalizerContext,
    ) -> InboundMessage:
        _ = headers
        text = body.decode("utf-8", errors="replace").strip()
        if not text:
            return build_inbound_message(
                context=context,
                body=body,
                external_user_id="wecom-empty",
                external_chat_id="wecom-empty",
                text="",
                raw_metadata={"kind": "empty"},
            )

        if text.startswith("{"):
            payload = _safe_json(text)
            if "encrypt" in payload:
                return self._encrypted_message(context=context, body=body, payload=payload)
            # Plain JSON v2 — parse directly.
            return build_inbound_message(
                context=context,
                body=body,
                external_user_id=str(
                    payload.get("from", {}).get("user_id", "wecom-json")
                ),
                external_chat_id=str(payload.get("chat_id", "wecom-json")),
                external_message_id=(
                    str(payload.get("msg_id")) if payload.get("msg_id") else None
                ),
                text=str(payload.get("text", "")),
                raw_metadata={
                    "msg_type": payload.get("msgtype", "text"),
                    "kind": "json",
                },
            )

        if text.startswith("<xml"):
            root = _safe_xml(body)
            return build_inbound_message(
                context=context,
                body=body,
                external_user_id=root.get("FromUserName", ""),
                external_chat_id=root.get("ChatId") or root.get("ToUserName", ""),
                external_message_id=(
                    str(root.get("MsgId") or root.get("MsgID") or "") or None
                ),
                text=root.get("Content") or "",
                attachments=_attachments(root),
                raw_metadata={
                    "msg_type": root.get("MsgType", "text"),
                    "agent_id": root.get("AgentID", ""),
                    "kind": "xml",
                },
            )

        return build_inbound_message(
            context=context,
            body=body,
            external_user_id="wecom-unknown",
            external_chat_id="wecom-unknown",
            text=text,
            raw_metadata={"kind": "raw"},
        )

    def _encrypted_message(
        self,
        *,
        context: NormalizerContext,
        body: bytes,
        payload: dict[str, Any],
    ) -> InboundMessage:
        if self._aes_key is None or self._aes_iv is None:
            return _placeholder(
                context=context, body=body, raw_metadata={"kind": "encrypted"}
            )
        try:
            cipher = base64.b64decode(payload["encrypt"])
            if len(cipher) < 32:
                return _placeholder(
                    context=context,
                    body=body,
                    raw_metadata={"kind": "encrypted", "decrypt": "frame_too_short"},
                )
            from cryptography.hazmat.primitives import padding as sym_padding
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

            decryptor = Cipher(
                algorithms.AES(self._aes_key), modes.CBC(self._aes_iv)
            ).decryptor()
            padded = decryptor.update(cipher) + decryptor.finalize()
            unpadder = sym_padding.PKCS7(128).unpadder()
            plaintext = unpadder.update(padded) + unpadder.finalize()
            xml_text = plaintext.decode("utf-8")
            root = _safe_xml_bytes(xml_text.encode("utf-8"))
        except Exception:
            return _placeholder(
                context=context,
                body=body,
                raw_metadata={"kind": "encrypted", "decrypt": "failed"},
            )
        if not root:
            return _placeholder(
                context=context,
                body=body,
                raw_metadata={"kind": "encrypted", "decrypt": "invalid_xml"},
            )
        return build_inbound_message(
            context=context,
            body=body,
            external_user_id=root.get("FromUserName", ""),
            external_chat_id=root.get("ChatId") or root.get("ToUserName", ""),
            external_message_id=(
                str(root.get("MsgId") or root.get("MsgID") or "") or None
            ),
            text=root.get("Content") or "",
            attachments=_attachments(root),
            raw_metadata={
                "msg_type": root.get("MsgType", "text"),
                "agent_id": root.get("AgentID", ""),
                "kind": "decrypted",
            },
        )


def _placeholder(
    *,
    context: NormalizerContext,
    body: bytes,
    raw_metadata: dict[str, Any],
) -> InboundMessage:
    return build_inbound_message(
        context=context,
        body=body,
        external_user_id="wecom-encrypted",
        external_chat_id="wecom-encrypted",
        text="",
        raw_metadata=raw_metadata,
    )


def _safe_json(text: str) -> dict[str, Any]:
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    return decoded


def _safe_xml(body: bytes) -> dict[str, str]:
    return _safe_xml_bytes(body)


def _safe_xml_bytes(body: bytes) -> dict[str, str]:
    try:
        from defusedxml import ElementTree as DefusedET

        root = DefusedET.fromstring(body)  # type: ignore[arg-type]
    except Exception:  # DefusedET.ParseError + xml parse error
        return {}
    return {child.tag: (child.text or "") for child in root}


def _attachments(root: dict[str, str]) -> tuple[AttachmentRef, ...]:
    """企微的图片 / 文件 → 统一成 :class:`AttachmentRef`（§3.4）。

    企微回调里图片与文件都只给 ``MediaId``（字节要另走下载接口）。
    """
    msg_type = str(root.get("MsgType") or "text")
    if msg_type not in {"image", "file", "voice", "video"}:
        return ()
    media_id = str(root.get("MediaId") or "")
    if not media_id:
        return ()
    content_type = {
        "image": "image/*",
        "file": "application/octet-stream",
        "voice": "audio/*",
        "video": "video/*",
    }.get(msg_type, "application/octet-stream")
    return (
        object_storage_attachment(
            attachment_id=media_id,
            filename="",
            content_type=content_type,
            uri=media_id,
        ),
    )


__all__ = ["WeChatWorkInboundAdapter"]
