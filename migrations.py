from pathlib import Path

from db import SCHEMA, get_pool

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def run_migrations() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA}.schema_migrations (
              version TEXT PRIMARY KEY,
              applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        applied = {
            row["version"]
            for row in await conn.fetch(
                f"SELECT version FROM {SCHEMA}.schema_migrations"
            )
        }
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.stem
            if version in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    f"INSERT INTO {SCHEMA}.schema_migrations (version) VALUES ($1)",
                    version,
                )
