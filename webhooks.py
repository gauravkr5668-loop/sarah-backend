"""
Sarah — Webhook routes.

POST /call-end
    Entry point for Vapi's end-of-call webhook.
    Orchestrates:
        1. Optional bearer-token auth check
        2. Raw payload parsing
        3. Call-level field extraction  (call_service)
        4. Lead data extraction         (lead_service)
        5. SQLite persistence           (database)
        6. Make.com forwarding          (make_service)

Always returns HTTP 200 to Vapi — downstream failures are logged but
must never cause Vapi to retry and flood the endpoint.
"""

import logging
import os
from typing import Tuple

from flask import Blueprint, Response, current_app, jsonify, request

from app.models.database import save_call
from app.services.call_service import parse_call_payload
from app.services.lead_service import extract_lead
from app.services.make_service import send_to_make

logger = logging.getLogger(__name__)

webhooks_bp = Blueprint("webhooks", __name__)


# --------------------------------------------------------------------------- #
# Route
# --------------------------------------------------------------------------- #

@webhooks_bp.route("/call-end", methods=["POST"])
def call_end() -> Tuple[Response, int]:
    """
    Receive and process a Vapi end-of-call webhook.

    Flow:
        1. Validate the optional SECRET_TOKEN header.
        2. Decode the JSON body (fail gracefully on bad input).
        3. Parse call-level metadata via call_service.
        4. Extract structured lead fields via lead_service.
        5. Persist the unified record to SQLite.
        6. Forward the lead payload to Make.com.
        7. Return 200 JSON regardless of downstream failures.

    Returns:
        Tuple[Response, int]: JSON acknowledgement + HTTP 200.
    """
    # ------------------------------------------------------------------ #
    # 1. Optional secret-token auth
    # ------------------------------------------------------------------ #
    secret = current_app.config.get("SECRET_TOKEN", "")
    if secret:
        auth_header = request.headers.get("Authorization", "")
        provided = auth_header.removeprefix("Bearer ").strip()
        if provided != secret:
            logger.warning(
                "Unauthorised /call-end request from %s", request.remote_addr
            )
            return jsonify({"status": "error", "message": "Unauthorised"}), 401

    # ------------------------------------------------------------------ #
    # 2. Decode body
    # ------------------------------------------------------------------ #
    raw_payload = request.get_json(silent=True, force=True)

    if not raw_payload:
        logger.warning(
            "Empty or non-JSON body received on /call-end from %s",
            request.remote_addr,
        )
        return jsonify({"status": "error", "message": "Empty or invalid JSON body"}), 400

    logger.info("Received /call-end webhook.")
    logger.debug("Raw payload keys: %s", list(raw_payload.keys()))

    # ------------------------------------------------------------------ #
    # 3. Parse Vapi call fields
    # ------------------------------------------------------------------ #
    try:
        call_data = parse_call_payload(raw_payload)
    except Exception as exc:  # noqa: BLE001
        logger.exception("call_service failed to parse payload: %s", exc)
        call_data = {
            "call_id":      "",
            "timestamp":    "",
            "transcript":   "",
            "summary":      "",
            "caller_phone": "",
            "duration":     0,
            "ended_reason": "",
        }

    # ------------------------------------------------------------------ #
    # 4. Extract lead data from transcript / summary
    # ------------------------------------------------------------------ #
    try:
        lead_data = extract_lead(call_data)
    except Exception as exc:  # noqa: BLE001
        logger.exception("lead_service failed to extract lead: %s", exc)
        lead_data = {
            "caller_name": None,
            "phone":       call_data.get("caller_phone"),
            "suburb":      None,
            "service":     None,
            "urgency":     "unknown",
            "summary":     call_data.get("summary", ""),
        }

    # ------------------------------------------------------------------ #
    # 5. Build unified record and persist to SQLite
    # ------------------------------------------------------------------ #
    record: dict = {
        "call_id":      call_data.get("call_id", ""),
        "caller_name":  lead_data.get("caller_name"),
        "phone":        lead_data.get("phone") or call_data.get("caller_phone"),
        "suburb":       lead_data.get("suburb"),
        "service":      lead_data.get("service"),
        "urgency":      lead_data.get("urgency", "unknown"),
        "summary":      lead_data.get("summary") or call_data.get("summary", ""),
        "transcript":   call_data.get("transcript", ""),
        "raw_json":     raw_payload,
    }

    db_path = current_app.config["DATABASE_PATH"]
    db_ok = save_call(db_path, record)

    if not db_ok:
        logger.error(
            "Failed to persist call_id=%s to SQLite.", record["call_id"]
        )

    # ------------------------------------------------------------------ #
    # 6. Forward to Make.com
    # ------------------------------------------------------------------ #
    make_url = current_app.config.get("MAKE_WEBHOOK_URL", "")
    make_ok = send_to_make(make_url, record)

    if not make_ok:
        logger.warning(
            "Make.com delivery failed for call_id=%s — "
            "record is still stored locally.",
            record["call_id"],
        )

    # ------------------------------------------------------------------ #
    # 7. Always respond 200 to Vapi
    # ------------------------------------------------------------------ #
    return jsonify(
        {
            "status":    "ok",
            "call_id":   record["call_id"],
            "db_saved":  db_ok,
            "make_sent": make_ok,
        }
    ), 200
