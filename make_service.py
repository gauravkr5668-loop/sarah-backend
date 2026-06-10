"""
Sarah — Airtable integration service.
Forwards structured lead data directly to Airtable.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

AIRTABLE_BASE_ID = "appCibqTYnKGmutgV"
AIRTABLE_TABLE_NAME = "Leads"
AIRTABLE_API_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
_TIMEOUT_SECONDS = 8


def send_to_make(webhook_url: str, record: Dict[str, Any]) -> bool:
    import os
    api_key = os.environ.get("AIRTABLE_API_KEY", "")

    if not api_key:
        logger.error("AIRTABLE_API_KEY not set — skipping Airtable delivery.")
        return False

    payload = {
        "fields": {
            "Name": record.get("caller_name") or "Unknown",
            "Phone": record.get("phone") or "",
            "Service": record.get("service") or "",
            "Suburb": record.get("suburb") or "",
            "Urgency": record.get("urgency") or "unknown",
            "Notes": record.get("summary") or "",
            "Timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }

    try:
        response = requests.post(
            AIRTABLE_API_URL,
            json=payload,
            timeout=_TIMEOUT_SECONDS,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        logger.info("Airtable delivery OK — call_id=%s", record.get("call_id"))
        return True

    except requests.exceptions.HTTPError as exc:
        logger.error("Airtable HTTP error — %s body=%s", exc,
                     exc.response.text[:500] if exc.response else "")
    except Exception as exc:
        logger.exception("Unexpected error sending to Airtable — %s", exc)

    return False
