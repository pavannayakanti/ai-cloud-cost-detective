"""AWS RDS (PostgreSQL) connection pool, schema setup, and queries."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import asyncpg

_pool: Optional[asyncpg.Pool] = None

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

CREATE_ANALYSES_TABLE = """
CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    resource_group TEXT NOT NULL,
    resources_scanned INTEGER,
    issues_found INTEGER,
    estimated_savings TEXT,
    analysis_result JSONB,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def init_db() -> None:
    global _pool
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set. Add it to backend/.env")

    _pool = await asyncpg.create_pool(database_url, init=_init_connection)
    async with _pool.acquire() as conn:
        await conn.execute(CREATE_USERS_TABLE)
        await conn.execute(CREATE_ANALYSES_TABLE)


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialized.")
    return _pool


async def create_analysis(
    analysis_id: str, user_id: Optional[int], resource_group: str
) -> None:
    pool = _get_pool()
    await pool.execute(
        """
        INSERT INTO analyses (id, user_id, resource_group, status)
        VALUES ($1, $2, $3, 'pending')
        """,
        analysis_id,
        user_id,
        resource_group,
    )


async def complete_analysis(
    analysis_id: str,
    resources_scanned: int,
    issues_found: int,
    estimated_savings: str,
    analysis_result: Dict[str, Any],
) -> None:
    pool = _get_pool()
    await pool.execute(
        """
        UPDATE analyses
        SET resources_scanned = $2,
            issues_found = $3,
            estimated_savings = $4,
            analysis_result = $5,
            status = 'complete'
        WHERE id = $1
        """,
        analysis_id,
        resources_scanned,
        issues_found,
        estimated_savings,
        analysis_result,
    )


async def fail_analysis(analysis_id: str, error: str) -> None:
    pool = _get_pool()
    await pool.execute(
        """
        UPDATE analyses
        SET status = 'failed', analysis_result = $2
        WHERE id = $1
        """,
        analysis_id,
        {"error": error},
    )


async def create_user(email: str, password_hash: str) -> int:
    pool = _get_pool()
    row = await pool.fetchrow(
        "INSERT INTO users (email, password_hash) VALUES ($1, $2) RETURNING id",
        email,
        password_hash,
    )
    return row["id"]


async def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    pool = _get_pool()
    row = await pool.fetchrow(
        "SELECT id, email, password_hash FROM users WHERE email = $1", email
    )
    return dict(row) if row else None


async def get_history(user_id: int) -> List[Dict[str, Any]]:
    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT id, resource_group, resources_scanned, issues_found,
               estimated_savings, analysis_result, status, created_at
        FROM analyses
        WHERE user_id = $1
        ORDER BY created_at DESC
        """,
        user_id,
    )
    return [dict(row) for row in rows]
