"""
Sarah — Make.com integration service.

Forwards structured lead data to a Make.com (formerly Integromat) webhook.
Make.com then handles downstream automation: email alerts, CRM updates,
Slack notifications, Google Sheets logging, etc.

Design principles
-----------------
* Never raises — all failures are caught, logged, and return False.
* Skips gracefully when MAKE_WEBHOOK_URL is not configured.
* Uses a short timeout so a slow/dead Make.com endpoint never blocks Vapi.
* Sends a clean, flat JSON payload (no raw transcript blob).
"""

import logging
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

# Maximum seconds to wait for Make.com to accept the webhook
_TIMEOUT_SECONDS = 8


def send_to_make(webhook_url: str, record: Dict[str, Any]) -> bool:
    """
    POST a structured lead payload to the Make.com webhook URL.

    Args:
        webhook_url: The full HTTPS URL of the Make.com custom webhook.
                     If empty or None the function returns True (no-op).
        record:      The unified call/lead record dict produced in the
                     webhook route.  raw_json is excluded from the payload
                     sent to Make.com to keep the message lean.

    Returns:
        True  – payload delivered successfully (HTTP 2xx from Make.com).
        False – delivery skipped (no URL) or failed (network/HTTP error).
    """
    if not webhook_url:
        logger.debug("MAKE_WEBHOOK_URL not set — skipping Make.com delivery.")
        return True  # Not a failure; just not configured

    payload = _build_payload(record)

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=_TIMEOUT_SECONDS,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        logger.info(
            "Make.com delivery OK — call_id=%s  status=%s",
            payload.get("call_id"),
            response.status_code,
        )
        return True

    except requests.exceptions.Timeout:
        logger.error(
            "Make.com timed out after %ss for call_id=%s",
            _TIMEOUT_SECONDS,
            payload.get("call_id"),
        )
    except requests.exceptions.ConnectionError as exc:
        logger.error(
            "Make.com connection error for call_id=%s — %s",
            payload.get("call_id"),
            exc,
        )
    except requests.exceptions.HTTPError as exc:
        logger.error(
            "Make.com HTTP error for call_id=%s — %s  body=%s",
            payload.get("call_id"),
            exc,
            exc.response.text[:500] if exc.response else "",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unexpected error sending to Make.com for call_id=%s — %s",
            payload.get("call_id"),
            exc,
        )

    return False


# --------------------------------------------------------------------------- #
# Private helpers
# --------------------------------------------------------------------------- #

def _build_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a clean, flat JSON payload for Make.com.

    Excludes ``raw_json`` and ``transcript`` to keep the webhook body
    small.  Make.com scenarios can be rebuilt from these structured fields.

    Args:
        record: Unified call/lead dict from the webhook route.

    Returns:
        Dict safe to serialise as JSON.
    """
    return {
        "call_id":     record.get("call_id", ""),
        "caller_name": record.get("caller_name"),
        "phone":       record.get("phone"),
        "suburb":      record.get("suburb"),
        "service":     record.get("service"),
        "urgency":     record.get("urgency", "unknown"),
        "summary":     record.get("summary", ""),
        "source":      "Sarah",
    }
