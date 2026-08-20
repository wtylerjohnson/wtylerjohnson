"""Signed deck tokens. HMAC-SHA256, key from the environment, never committed.

Token = b64url(payload json) + "." + b64url(hmac). Payload:
{deck_id, exec_id, persona, client, display_order_seed, variant, exp}.
The persona rides in the payload, never typed. exec_id is opaque; no names,
no emails, anywhere near this module.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from lila import config


class TokenError(Exception):
    pass


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def signing_key() -> bytes:
    key = os.environ.get(config.SIGNING_KEY_ENV)
    if not key:
        raise TokenError(f"{config.SIGNING_KEY_ENV} not set; the signing key comes from the environment")
    return key.encode()


def mint(payload: dict, key: bytes | None = None) -> str:
    key = key or signing_key()
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = hmac.new(key, body, hashlib.sha256).digest()
    return _b64e(body) + "." + _b64e(sig)


def verify(token: str, key: bytes | None = None) -> dict:
    key = key or signing_key()
    try:
        body_s, sig_s = token.split(".")
        body = _b64d(body_s)
        sig = _b64d(sig_s)
    except Exception as e:
        raise TokenError("malformed token") from e
    expected = hmac.new(key, body, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        raise TokenError("bad signature")
    payload = json.loads(body)
    if payload.get("exp") and payload["exp"] < time.time():
        raise TokenError("token expired")
    return payload
