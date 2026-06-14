"""Web UI — FastAPI application for viewing and managing movies.

Entry point for the web application. Run from the project root:
    python src/webui/main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import logging

import uvicorn

from src.common.config import load_config
from src.common.db import get_engine, get_session_factory, init_db
from src.webui.app import create_app


def main() -> None:
    """Start the FastAPI web application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [webui] %(levelname)s %(message)s",
    )
    logger = logging.getLogger(__name__)

    logger.info("Starting pelis-feed web UI")

    # Load configuration
    try:
        config = load_config()
    except FileNotFoundError as e:
        logger.error("Configuration error: %s", e)
        sys.exit(1)

    # Initialize database
    engine = get_engine(config)
    init_db(engine)
    session_factory = get_session_factory(engine)

    # Create and run app
    app = create_app(config, session_factory)

    host = config.get("webapp", {}).get("host", "127.0.0.1")
    port = config.get("webapp", {}).get("port", 8080)

    logger.info("Serving on http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
