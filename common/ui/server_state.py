"""Whether the server can be used right now, and what to tell the user when it cannot.

Being connected is not enough: whoever entered without an account has no token, so the server answers
"Sign-in required." to every request. The views ask here before calling, and say which of the two it is.

Autore: Samuele Gallo
"""
from __future__ import annotations

from typing import Any

from common.i18n import tr


def server_ready(session: Any) -> bool:
    """True when the application can talk to the server on behalf of somebody: connected, and with an account."""
    return bool(getattr(session, "online", False) and getattr(session, "client", None)
                and not getattr(session, "is_guest", False))


def server_note(session: Any) -> str:
    """Why the server cannot be used now, in one line for the views."""
    if getattr(session, "is_guest", False):
        return tr("You are using the application without an account: sign in to use the server.")
    return tr("You are offline: the server folders are not available.")
