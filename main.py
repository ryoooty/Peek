from __future__ import annotations

from aiohttp import web

from app.config import settings
from app import storage, runtime


def create_app() -> web.Application:
    """Create and configure an empty aiohttp application."""
    runtime.setup_logging()
    storage.init(settings.db_path)
    return web.Application()


def main() -> None:
    """Run the aiohttp web server."""
    try:
        web.run_app(create_app())
    finally:
        storage.close()


if __name__ == "__main__":
    main()
