from __future__ import annotations

from aiohttp import web

from app.handlers.payments import http_router
from app.config import settings
from app import storage, runtime


def create_app() -> web.Application:
    """Create and configure the aiohttp application."""
    # Initialize logging and storage once on startup
    runtime.setup_logging()
    storage.init(settings.db_path)
    app = web.Application()
    app.add_routes(http_router)
    return app


def main() -> None:
    """Run the aiohttp web server."""
    try:
        web.run_app(create_app())
    finally:
        storage.close()


if __name__ == "__main__":
    main()
