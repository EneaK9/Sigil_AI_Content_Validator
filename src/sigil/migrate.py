"""Apply the bundled SQL migrations against ``SUPABASE_DB_URL`` in order.

The migrations live in ``sigil/scraper/db/migrations/*.sql`` and are written to
be idempotent (``IF NOT EXISTS`` / ``DO`` guards), so this runner simply applies
every file in filename order. Run it once after install and after pulling new
migrations::

    sigil-migrate
"""

from __future__ import annotations

import asyncio
import sys
from importlib.resources import files

import asyncpg

from sigil.config import get_settings
from sigil.logging import configure_logging, get_logger

log = get_logger(__name__)


def _asyncpg_dsn(sqlalchemy_url: str) -> str:
    """Convert a SQLAlchemy asyncpg URL into a plain asyncpg DSN."""
    return sqlalchemy_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _migration_files() -> list[tuple[str, str]]:
    """Return ``(name, sql)`` for every bundled migration, sorted by name."""
    migrations_dir = files("sigil.scraper.db").joinpath("migrations")
    entries = sorted(
        (p for p in migrations_dir.iterdir() if p.name.endswith(".sql")),
        key=lambda p: p.name,
    )
    return [(p.name, p.read_text(encoding="utf-8")) for p in entries]


async def _run() -> int:
    settings = get_settings()
    dsn = _asyncpg_dsn(settings.supabase_db_url)

    migrations = _migration_files()
    if not migrations:
        log.warning("no_migrations_found")
        return 0

    # statement_cache_size=0 keeps us compatible with the Supabase pooler.
    conn = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        for name, sql in migrations:
            log.info("applying_migration", migration=name)
            await conn.execute(sql)
            log.info("applied_migration", migration=name)
    finally:
        await conn.close()

    log.info("migrations_complete", count=len(migrations))
    return 0


def main() -> int:
    """Console-script entrypoint (``sigil-migrate``)."""
    configure_logging(get_settings().log_level)
    try:
        return asyncio.run(_run())
    except Exception as exc:  # surface a clean non-zero exit for ops tooling
        log.error("migration_failed", error=str(exc), exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
