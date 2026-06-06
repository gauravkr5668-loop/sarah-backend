"""
Sarah — Health check route.

GET /
    Returns a simple JSON payload confirming the service is live.
    Used by Railway health checks and external uptime monitors.
"""

import logging
from typing import Tuple

from flask import Blueprint, Response, jsonify

logger = logging.getLogger(__name__)

health_bp = Blueprint("health", __name__)


@health_bp.route("/", methods=["GET"])
def health_check() -> Tuple[Response, int]:
    """
    Health check endpoint.

    Returns:
        200 JSON response: {"status": "ok"}
    """
    logger.debug("Health check ping received.")
    return jsonify({"status": "ok", "service": "Sarah"}), 200
