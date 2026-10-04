"""DingTalk inbound adapter — parses DingTalk Open Platform event envelope.

DingTalk delivers two kinds of payloads to the webhook:

- **Encrypted v2 stream events**: ``{"encrypt":"<base64>"}`` whose body
  is AES-256-CBC encrypted using a key derived from the app secret
  (``SHA-256(app_secret)[:32]``) with the first 16 bytes of the
  ciphertext as IV. Decrypted plaintext is a JSON envelope with
  ``msgtype`` / ``senderId`` / ``text`` fields. When ``app_secret`` is
  configured the adapter decrypts and parses normally; otherwise it
  returns a ``kind=encrypted`` placeholder (legacy behaviour).
- **Plain callback events**: ``{"msgtype":"text","text":{"content":...},
  "senderId":"...","conversationId":"..."}``.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from qzdap.modules.channel.application.ports import InboundAdapter, ParsedMessage
from qzdap.modules.channel.domain.value_objects import ChannelType


class DingTalkInboundAdapter(InboundAdapter):
    channel_type = ChannelType.DINGTALK

    def __init__(self, *, app_secret: str = "") -> None:
        # App secret → 32-byte AES-256 key. Empty secret keeps the
        # legacy placeholder behaviour so dev / unit tests keep
        # working without configuration.
        self._aes_key: bytes | None = None
        if app_secret:
            self._aes_key = hashlib.sha256(app_secret.encode("utf-8")).digest()

    def parse_webhook(
        self,
        *,
        body: bytes,
        headers: dict[str, str],
    ) -> ParsedMessage:
        payload = _safe_json(body)

        # Stream v2 encryption. Real DingTalk signs the request with a
        # timestamp + suite ticket; signature verification is performed
        # upstream by the FastAPI handler. Here we only need to decrypt
        # ``encrypt`` so the rest of the pipeline can dispatch on
        # ``msgtype``.
        if "encrypt" in payload and isinstance(payload.get("encrypt"), str):
            if self._aes_key is None:
                return ParsedMessage(
                    external_user_id="dingtalk-encrypted",
                    external_chat_id="dingtalk-encrypted",
                    external_message_id=None,
                    text="",
                    metadata={"kind": "encrypted", "raw_len": len(payload["encrypt"])},
                )
            try:
                cipher = base64.b64decode(payload["encrypt"])
                # AES-256-CBC: IV is the first 16 bytes of the
                # ciphertext. Anything shorter is a malformed frame.
                if len(cipher) < 32:
                    return ParsedMessage(
                        external_user_id="dingtalk-encrypted",
                        external_chat_id="dingtalk-encrypted",
                        external_message_id=None,
                        text="",
                        metadata={
                            "kind": "encrypted",
                            "raw_len": len(payload["encrypt"]),
                            "decrypt": "frame_too_short",
                        },
                    )
                iv = cipher[:16]
                ct = cipher[16:]
                from cryptography.hazmat.primitives import padding as sym_padding
                from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

                decryptor = Cipher(
                    algorithms.AES(self._aes_key), modes.CBC(iv)
                ).decryptor()
                padded = decryptor.update(ct) + decryptor.finalize()
                unpadder = sym_padding.PKCS7(128).unpadder()
                plaintext = unpadder.update(padded) + unpadder.finalize()
                inner = json.loads(plaintext.decode("utf-8"))
            except Exception:
                # Decryption failed — fall back to the placeholder so
                # we never leak raw ciphertext into the audit log.
                return ParsedMessage(
                    external_user_id="dingtalk-encrypted",
                    external_chat_id="dingtalk-encrypted",
                    external_message_id=None,
                    text="",
                    metadata={
                        "kind": "encrypted",
                        "raw_len": len(payload["encrypt"]),
                        "decrypt": "failed",
                    },
                )
            if not isinstance(inner, dict):
                return ParsedMessage(
                    external_user_id="dingtalk-encrypted",
                    external_chat_id="dingtalk-encrypted",
                    external_message_id=None,
                    text="",
                    metadata={"kind": "encrypted", "decrypt": "invalid_json"},
                )
            msg_type = inner.get("msgtype", "text")
            text = _extract_text(inner)
            sender_id = str(
                inner.get("senderId")
                or inner.get("senderStaffId")
                or ""
            )
            chat_id = str(
                inner.get("conversationId")
                or inner.get("chatId")
                or inner.get("openConversationId")
                or ""
            )
            msg_id = inner.get("msgId") or inner.get("messageId")
            return ParsedMessage(
                external_user_id=sender_id,
                external_chat_id=chat_id,
                external_message_id=str(msg_id) if msg_id else None,
                text=text,
                metadata={
                    "msg_type": msg_type,
                    "conversation_type": inner.get("conversationType", ""),
                    "robot_code": inner.get("robotCode", ""),
                    "kind": "decrypted",
                },
            )

        msg_type = payload.get("msgtype", "text")
        text = _extract_text(payload)
        sender_id = str(payload.get("senderId") or payload.get("senderStaffId") or "")
        chat_id = str(
            payload.get("conversationId")
            or payload.get("chatId")
            or payload.get("openConversationId")
            or ""
        )
        msg_id = payload.get("msgId") or payload.get("messageId")

        return ParsedMessage(
            external_user_id=sender_id,
            external_chat_id=chat_id,
            external_message_id=str(msg_id) if msg_id else None,
            text=text,
            metadata={
                "msg_type": msg_type,
                "conversation_type": payload.get("conversationType", ""),
                "robot_code": payload.get("robotCode", ""),
            },
        )


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


__all__ = ["DingTalkInboundAdapter"]
