"""HMAC pseudonyms: raw user ids never reach logs or prompts."""

from __future__ import annotations

import hashlib
import hmac

from getnet_multi_agent.core.settings import get_settings


def pseudonym(user_id: str) -> str:
    key = get_settings().PSEUDONYM_KEY.encode()
    return "u_" + hmac.new(key, user_id.encode(), hashlib.sha256).hexdigest()[:16]
