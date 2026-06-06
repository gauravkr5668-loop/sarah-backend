"""
Sarah — Application factory.

Creates, configures, and returns the Flask app.
All blueprints and extensions are registered here.
"""

import logging
import os

from flask import Flask

from app.models.database import init_db
from app.routes.health import health_bp
from app.routes.webhooks import webhooks_bp


def create_app() -> Flask:
    """
    Create and configure the Flask application instance.

    Reads configuration from environment variables, initialises the
    SQLite database, and registers all route blueprints.

    Returns:
        Flask: Fully configured application ready for Gunicorn.
    """
    app = Flask(__name__)

    # ------------------------------------------------------------------ #
    # Logging
    # ------------------------------------------------------------------ #
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    logger = logging.getLogger(__name__)
    logger.info("Booting Sarah backend …")

    # ------------------------------------------------------------------ #
    # App config from environment
    # ------------------------------------------------------------------ #
    app.config["DATABASE_PATH"] = os.environ.get("DATABASE_PATH", "veronica.db")
    app.config["MAKE_WEBHOOK_URL"] = os.environ.get("MAKE_WEBHOOK_URL", "")
    app.config["SECRET_TOKEN"] = os.environ.get("SECRET_TOKEN", "")

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    init_db(app.config["DATABASE_PATH"])
    logger.info("SQLite database ready: %s", app.config["DATABASE_PATH"])

    # ------------------------------------------------------------------ #
    # Blueprints
    # ------------------------------------------------------------------ #
    app.register_blueprint(health_bp)
    app.register_blueprint(webhooks_bp)
    logger.info("All blueprints registered.")

    return app
