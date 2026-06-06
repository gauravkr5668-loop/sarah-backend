"""
Sarah — Call service.

Normalises the raw Vapi end-of-call webhook payload into a clean,
flat dictionary of call-level fields that the rest of the application
can consume without knowing the exact Vapi schema.

Vapi sends payloads in this shape (simplified):

{
  "message": {
    "type": "end-of-call-report",
    "call": {
      "id": "...",
      "startedAt": "...",
      "endedAt": "...",
      "endedReason": "...",
      "duration": 42,
      "customer": { "number": "+61412345678" },
      "transcript": "AI: Hello ...\nCustomer: ...",
      "summary": "Customer called about a leaking tap ..."
    }
  }
}

Some fields may be at the root level (older Vapi versions / custom flows),
so we check multiple locations defensively.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


def parse_call_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract normalised call-level fields from a raw Vapi webhook payload.

    Handles both the nested ``{ "message": { "call": { ... } } }`` envelope
    and flat payloads where fields live at the root.

    Args:
        payload: Raw dict decoded from the Vapi POST body.

    Returns:
        Dict with keys:
            call_id      (str)  – Vapi's unique call ID
            timestamp    (str)  – ISO-8601 UTC end/start time
            transcript   (str)  – Full plain-text transcript
            summary      (str)  – Assistant-generated call summary
            caller_phone (str)  – Caller's E.164 phone number
            duration     (int)  – Duration in seconds (0 if unknown)
            ended_reason (str)  – Reason the call ended
    """
    # ------------------------------------------------------------------ #
    # Unwrap envelope
    # ------------------------------------------------------------------ #
    # Vapi may wrap in { "message": { ... } } or send the call directly.
    message: Dict[str, Any] = payload.get("message", payload) or {}
    call: Dict[str, Any] = message.get("call", message) or {}

    # ------------------------------------------------------------------ #
    # call_id
    # ------------------------------------------------------------------ #
    call_id: str = (
        _first_str(call.get("id"), message.get("callId"), payload.get("callId"))
        or ""
    )

    # ------------------------------------------------------------------ #
    # timestamp
    # ------------------------------------------------------------------ #
    raw_ts: str = (
        _first_str(
            call.get("endedAt"),
            call.get("startedAt"),
            message.get("timestamp"),
        )
        or ""
    )
    timestamp = raw_ts if raw_ts else _utcnow()

    # ------------------------------------------------------------------ #
    # transcript
    # ------------------------------------------------------------------ #
    transcript: str = (
        _first_str(message.get("transcript"), call.get("transcript"))
        or ""
    )

    # ------------------------------------------------------------------ #
    # summary
    # ------------------------------------------------------------------ #
    summary: str = (
        _first_str(message.get("summary"), call.get("summary"))
        or ""
    )

    # ------------------------------------------------------------------ #
    # caller_phone
    # ------------------------------------------------------------------ #
    customer: Dict[str, Any] = call.get("customer") or {}
    caller_phone: str = (
        _first_str(
            customer.get("number"),
            call.get("phoneNumber"),
            message.get("phoneNumber"),
        )
        or ""
    )

    # ------------------------------------------------------------------ #
    # duration (seconds)
    # ------------------------------------------------------------------ #
    try:
        duration = int(call.get("duration") or message.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0

    # ------------------------------------------------------------------ #
    # ended_reason
    # ------------------------------------------------------------------ #
    ended_reason: str = (
        _first_str(call.get("endedReason"), message.get("endedReason"))
        or ""
    )

    result = {
        "call_id":      call_id,
        "timestamp":    timestamp,
        "transcript":   transcript,
        "summary":      summary,
        "caller_phone": caller_phone,
        "duration":     duration,
        "ended_reason": ended_reason,
    }

    logger.info(
        "Parsed call — id=%s  duration=%ss  reason=%s",
        call_id, duration, ended_reason,
    )
    return result


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _first_str(*values: Any) -> str:
    """Return the first non-empty string among *values*, or empty string."""
    for v in values:
        if v and isinstance(v, str):
            return v.strip()
    return ""


def _utcnow() -> str:
    """Current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
