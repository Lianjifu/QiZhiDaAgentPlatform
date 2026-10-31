"""DingTalk inbound adapter — parses DingTalk Open Platform event envelope.

DingTalk delivers two kinds of payloads to the webhook:

- **Encrypted v2 stream events**: ``{"encrypt":"<base64>"}`` whose body
  is AES-256-CBC encrypted using a key derived from the app secret
  (``SHA-256(app_secret)[:32]``) with the first 16 bytes of the
  ciphertext as IV. Decrypted plaintext is a JSON envelope with
  ``msgtype`` / ``senderId`` / ``text`` fields. When ``app_secret`` is
  configured the adapter decrypts and parses normally; otherwise it
  returns a placeholder (legacy behaviour).
- **Plain callback events**: ``{"msgtype":"text","text":{"content":...},
  "senderId":"...","conversationId":"..."}``.
"""

from __future__ import annotations

import base64
import hashlib
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


class DingTalkInboundAdapter:
    """③ 的钉钉实现 —— 产出标准 :class:`InboundMessage`。"""

    channel_type = ChannelType.DINGTALK

    def __init__(self, *, app_secret: str = "") -> None:
        # App secret → 32-byte AES-256 key. Empty secret keeps the
        # legacy placeholder behaviour so dev / unit tests keep
        # working without configuration.
        self._aes_key: bytes | None = None
        if app_secret:
            self._aes_key = hashlib.sha256(app_secret.encode("utf-8")).digest()

    def normalize(
        self,
        *,
        body: bytes,
        headers: Mapping[str, str],
        context: NormalizerContext,
    ) -> InboundMessage:
        _ = headers
        payload = _safe_json(body)

        # Stream v2 encryption. Real DingTalk signs the request with a
        # timestamp + suite ticket; signature verification is performed
        # upstream by the FastAPI handler. Here we only need to decrypt
        # ``encrypt`` so the rest of the pipeline can dispatch on
        # ``msgtype``.
        if "encrypt" in payload and isinstance(payload.get("encrypt"), str):
            return self._encrypted_message(context=context, body=body, payload=payload)

        msg_type = str(payload.get("msgtype", "text"))
        text = _extract_text(payload)
        return build_inbound_message(
            context=context,
            body=body,
            external_user_id=str(payload.get("senderId") or payload.get("senderStaffId") or ""),
            external_chat_id=str(
                payload.get("conversationId")
                or payload.get("chatId")
                or payload.get("openConversationId")
                or ""
            ),
            external_message_id=_opt_msg_id(payload),
            text=text,
            attachments=_attachments(msg_type, payload),
            raw_metadata={
                "msg_type": msg_type,
                "conversation_type": payload.get("conversationType", ""),
                "robot_code": payload.get("robotCode", ""),
            },
        )

    def _encrypted_message(
        self,
        *,
        context: NormalizerContext,
        body: bytes,
        payload: dict[str, Any],
    ) -> InboundMessage:
        raw_len = len(str(payload.get("encrypt") or ""))
        if self._aes_key is None:
            return _placeholder(
                context=context,
                body=body,
                raw_metadata={"kind": "encrypted", "raw_len": raw_len},
            )
        try:
            cipher = base64.b64decode(payload["encrypt"])
            # AES-256-CBC: IV is the first 16 bytes of the
            # ciphertext. Anything shorter is a malformed frame.
            if len(cipher) < 32:
                return _placeholder(
                    context=context,
                    body=body,
                    raw_metadata={
                        "kind": "encrypted",
                        "raw_len": raw_len,
                        "decrypt": "frame_too_short",
                    },
                )
            iv = cipher[:16]
            ct = cipher[16:]
            from cryptography.hazmat.primitives import padding as sym_padding
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

            decryptor = Cipher(algorithms.AES(self._aes_key), modes.CBC(iv)).decryptor()
            padded = decryptor.update(ct) + decryptor.finalize()
            unpadder = sym_padding.PKCS7(128).unpadder()
            plaintext = unpadder.update(padded) + unpadder.finalize()
            inner = json.loads(plaintext.decode("utf-8"))
        except Exception:
            # Decryption failed — fall back to the placeholder so
            # we never leak raw ciphertext into the audit log.
            return _placeholder(
                context=context,
                body=body,
                raw_metadata={
                    "kind": "encrypted",
                    "raw_len": raw_len,
                    "decrypt": "failed",
                },
            )
        if not isinstance(inner, dict):
            return _placeholder(
                context=context,
                body=body,
                raw_metadata={"kind": "encrypted", "decrypt": "invalid_json"},
            )
        msg_type = str(inner.get("msgtype", "text"))
        return build_inbound_message(
            context=context,
            body=body,
            external_user_id=str(inner.get("senderId") or inner.get("senderStaffId") or ""),
            external_chat_id=str(
                inner.get("conversationId")
                or inner.get("chatId")
                or inner.get("openConversationId")
                or ""
            ),
            external_message_id=_opt_msg_id(inner),
            text=_extract_text(inner),
            attachments=_attachments(msg_type, inner),
            raw_metadata={
                "msg_type": msg_type,
                "conversation_type": inner.get("conversationType", ""),
                "robot_code": inner.get("robotCode", ""),
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
        external_user_id="dingtalk-encrypted",
        external_chat_id="dingtalk-encrypted",
        text="",
        raw_metadata=raw_metadata,
    )


def _opt_msg_id(payload: dict[str, Any]) -> str | None:
    msg_id = payload.get("msgId") or payload.get("messageId")
    return str(msg_id) if msg_id else None


def _safe_json(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    return decoded


def _extract_text(payload: dict[str, Any]) -> str:
    msg_type = payload.get("msgtype", "text")
    body = payload.get(msg_type) or {}
    if isinstance(body, dict):
        return str(body.get("content", ""))
    if isinstance(body, str):
        return body
    return str(payload.get("text", {}).get("content", ""))


def _attachments(msg_type: str, payload: dict[str, Any]) -> tuple[AttachmentRef, ...]:
    """图片 / 文件 / 语音 → 统一成 :class:`AttachmentRef`（§3.4）。"""
    if msg_type not in {"image", "file", "audio", "video"}:
        return ()
    body = payload.get(msg_type) or {}
    if not isinstance(body, dict):
        return ()
    media_id = str(body.get("media_id") or body.get("fileId") or "")
    if not media_id:
        return ()
    content_type = {
        "image": "image/*",
        "file": "application/octet-stream",
        "audio": "audio/*",
        "video": "video/*",
    }.get(msg_type, "application/octet-stream")
    return (
        object_storage_attachment(
            attachment_id=media_id,
            filename=str(body.get("file_name") or ""),
            content_type=content_type,
            uri=media_id,
        ),
    )


__all__ = ["DingTalkInboundAdapter"]
