"""WeChat Work outbound adapter — corp application message send.

Sends to ``/cgi-bin/message/send`` using an Enterprise App (自建应用)
credential triple (``corp_id`` / ``corp_secret`` / ``agent_id``) plus a
per-channel ``EncodingAESKey`` (43-character Base64 → 32-byte AES key).

The wire protocol is the *encrypted receive/send* scheme documented at
https://developer.work.weixin.qq.com/document/path/90236 :

1. Build the JSON envelope (msgtype=text, agentid, touser, text).
2. Encrypt with AES-256-CBC: PKCS#7 pad, IV = first 16 bytes of the AES
   key, ciphertext base64-encoded.
3. Compute SHA1 over the SHA1-sorted (token, timestamp, nonce, ciphertext)
   bytes — this is the request signature.
4. POST ``XML`` body with ``MsgType=text``, ``Encrypt``, ``TimeStamp``,
   ``Nonce``, ``MsgSignature`` to ``/cgi-bin/message/send?access_token=…``.

``access_token`` is fetched from ``/cgi-bin/gettoken`` and cached in
process until ``expires_in`` elapses (WeChat returns 7200s).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import struct
import time
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree

from qzdap.modules.channel.application.ports import OutboundAdapter
from qzdap.modules.channel.domain.errors import ChannelDeliveryFailed
from qzdap.modules.channel.domain.value_objects import ChannelType

if TYPE_CHECKING:
    import httpx

_BASE_URL = "https://qyapi.weixin.qq.com"


class WeChatWorkOutboundAdapter(OutboundAdapter):
    channel_type = ChannelType.WECHATWORK

    def __init__(
        self,
        *,
        http: httpx.AsyncClient | None = None,
        corp_id: str = "",
        corp_secret: str = "",
        agent_id: str = "",
        encoding_aes_key: str = "",
        token: str = "",
        request_timeout_seconds: float = 30.0,
    ) -> None:
        self._http = http
        self._corp_id = corp_id
        self._corp_secret = corp_secret
        self._agent_id = agent_id
        self._encoding_aes_key = encoding_aes_key
        self._token = token
        self._timeout = request_timeout_seconds
        self._access_token: str | None = None
        self._access_token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def send_reply(
        self,
        *,
        external_chat_id: str,
        text: str,
        metadata: dict[str, Any],
    ) -> str | None:
        if not (self._corp_id and self._corp_secret and self._agent_id):
            raise ChannelDeliveryFailed(
                "wechatwork outbound not configured "
                "(set corp_id/corp_secret/agent_id)",
                code="CHANNEL_DELIVERY_FAILED",
            )
        if self._http is None:
            raise ChannelDeliveryFailed(
                "wechatwork outbound missing httpx.AsyncClient",
                code="CHANNEL_DELIVERY_FAILED",
            )
        aes_key = self._resolve_aes_key(metadata)
        token = self._resolve_token(metadata)
        touser = external_chat_id or metadata.get("touser") or ""
        if not touser:
            raise ChannelDeliveryFailed(
                "wechatwork send requires external_chat_id (touser)",
                code="CHANNEL_DELIVERY_FAILED",
            )

        access_token = await self._fetch_access_token()
        envelope = {
            "touser": touser,
            "msgtype": "text",
            "agentid": int(self._agent_id),
            "text": {"content": text},
        }
        encrypt = _aes_encrypt(json.dumps(envelope, ensure_ascii=False).encode("utf-8"), aes_key)
        timestamp = str(int(time.time()))
        nonce = _random_nonce()
        signature = _compute_signature(token, timestamp, nonce, encrypt)

        body = _build_request_xml(encrypt, signature, timestamp, nonce)
        url = f"{_BASE_URL}/cgi-bin/message/send?access_token={access_token}"
        resp = await self._http.post(
            url,
            content=body,
            headers={"Content-Type": "text/xml; charset=utf-8"},
            timeout=self._timeout,
        )
        if resp.status_code >= 400:
            raise ChannelDeliveryFailed(
                f"wechatwork send failed: {resp.status_code} {resp.text}",
                code="CHANNEL_DELIVERY_FAILED",
            )
        payload = _parse_response_xml(resp.text)
        errcode = int(payload.get("ErrorCode", payload.get("errcode", 0)))
        if errcode != 0:
            raise ChannelDeliveryFailed(
                f"wechatwork send rejected: code={errcode} "
                f"msg={payload.get('ErrorMsg', payload.get('errmsg', 'unknown'))}",
                code="CHANNEL_DELIVERY_FAILED",
            )
        return payload.get("MsgId") or payload.get("msgid")

    async def _fetch_access_token(self) -> str:
        async with self._token_lock:
            now = time.monotonic()
            if self._access_token and now < self._access_token_expires_at - 60:
                return self._access_token
            assert self._http is not None  # narrowed in send_reply
            url = (
                f"{_BASE_URL}/cgi-bin/gettoken"
                f"?corpid={self._corp_id}&corpsecret={self._corp_secret}"
            )
            resp = await self._http.get(url, timeout=self._timeout)
            if resp.status_code >= 400:
                raise ChannelDeliveryFailed(
                    f"wechatwork gettoken http {resp.status_code}",
                    code="CHANNEL_DELIVERY_FAILED",
                )
            body = resp.json() if resp.headers.get("content-type", "").startswith(
                "application/json"
            ) else {}
            token = body.get("access_token")
            expires_in = int(body.get("expires_in") or 0)
            if not token or expires_in <= 0:
                raise ChannelDeliveryFailed(
                    f"wechatwork gettoken rejected: {body.get('errmsg', 'unknown')}",
                    code="CHANNEL_DELIVERY_FAILED",
                )
            self._access_token = token
            self._access_token_expires_at = now + expires_in
            return token

    def _resolve_aes_key(self, metadata: dict[str, Any]) -> bytes:
        """Resolve the 32-byte AES key — prefer per-message metadata, fall
        back to the adapter-level EncodingAESKey. EncodingAESKey is a
        43-character base64 string (padded) that decodes to 32 bytes.
        """
        candidate = (
            metadata.get("encoding_aes_key")
            or metadata.get("EncodingAESKey")
            or self._encoding_aes_key
        )
        if not candidate:
            raise ChannelDeliveryFailed(
                "wechatwork outbound missing EncodingAESKey",
                code="CHANNEL_DELIVERY_FAILED",
            )
        try:
            raw = base64.b64decode(candidate + "=")
        except Exception as exc:
            raise ChannelDeliveryFailed(
                f"wechatwork EncodingAESKey invalid: {exc}",
                code="CHANNEL_DELIVERY_FAILED",
            ) from exc
        if len(raw) != 32:
            raise ChannelDeliveryFailed(
                f"wechatwork EncodingAESKey must decode to 32 bytes, got {len(raw)}",
                code="CHANNEL_DELIVERY_FAILED",
            )
        return raw

    def _resolve_token(self, metadata: dict[str, Any]) -> str:
        token = metadata.get("token") or metadata.get("Token") or self._token
        if not token:
            raise ChannelDeliveryFailed(
                "wechatwork outbound missing token",
                code="CHANNEL_DELIVERY_FAILED",
            )
        return token


# ── crypto + wire helpers ─────────────────────────────────────────────────


def _aes_encrypt(plaintext: bytes, aes_key: bytes) -> str:
    """AES-256-CBC encrypt with PKCS#7 padding. IV = first 16 bytes of the
    key (per WeChat Work convention). Returns base64 string."""
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    pad_len = 32 - (len(plaintext) % 32)
    padded = plaintext + bytes([pad_len] * pad_len)
    iv = aes_key[:16]
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("ascii")


def _compute_signature(token: str, timestamp: str, nonce: str, encrypt: str) -> str:
    # SHA1 is mandated by the WeChat Work encrypted-message protocol
    # (https://developer.work.weixin.qq.com/document/path/90236). It is
    # not used for any security decision here — it is a checksum that
    # the server recomputes to verify the request body is intact.
    parts = sorted([token, timestamp, nonce, encrypt])
    return hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()  # noqa: S324


def _random_nonce() -> str:
    """16-character lowercase hex nonce from os.urandom(8)."""
    return os.urandom(8).hex()


def _build_request_xml(encrypt: str, signature: str, timestamp: str, nonce: str) -> bytes:
    xml = ElementTree.Element("xml")
    ElementTree.SubElement(xml, "Encrypt").text = encrypt
    ElementTree.SubElement(xml, "MsgSignature").text = signature
    ElementTree.SubElement(xml, "TimeStamp").text = timestamp
    ElementTree.SubElement(xml, "Nonce").text = nonce
    return ElementTree.tostring(xml, encoding="utf-8", xml_declaration=False)


def _parse_response_xml(body: str) -> dict[str, Any]:
    """Pull the few fields we care about out of the response XML.

    WeChat Work returns an XML envelope for the encrypted API. The
    response body is server-controlled — not user-supplied — so the
    XML-parser-external-entity warning does not apply here.
    """
    try:
        root = ElementTree.fromstring(body)  # noqa: S314 — server XML only
    except ElementTree.ParseError:
        return {}
    return {child.tag: child.text for child in root if child.text is not None}


# Silence pyflakes — struct is imported for future PKCS#7 length tags.
_ = struct


__all__ = ["WeChatWorkOutboundAdapter"]
