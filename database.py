"""
Database — async PostgreSQL via asyncpg
Connects to Supabase (free PostgreSQL hosting)
"""

import os
import asyncpg
from typing import Optional
from dotenv import load_dotenv

# Load .env file explicitly
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=10,
            statement_cache_size=0  # Required for Supabase pgbouncer
        )
    return _pool


async def get_db():
    """Dependency — yields a single connection from the pool."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def create_tables():
    """Create all tables if they don't exist (runs on startup)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          SERIAL PRIMARY KEY,
                name        TEXT NOT NULL,
                email       TEXT UNIQUE NOT NULL,
                password    TEXT NOT NULL,
                plan        TEXT DEFAULT 'free',
                streak      INT DEFAULT 0,
                daily_goal  INT DEFAULT 3,
                today_count INT DEFAULT 0,
                last_practice_date TEXT,
                interviews_this_month INT DEFAULT 0,
                month_key   TEXT DEFAULT '',
                onboarded   BOOLEAN DEFAULT FALSE,
                target_role TEXT,
                level       TEXT,
                recommended_role TEXT,
                cover_letters_generated INT DEFAULT 0,
                jd_matches_run INT DEFAULT 0,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS resumes (
                id              SERIAL PRIMARY KEY,
                user_id         INT REFERENCES users(id) ON DELETE CASCADE,
                raw_text        TEXT,
                extracted_skills TEXT[],
                ats_score       INT DEFAULT 0,
                recommended_role TEXT,
                level           TEXT,
                analysis_json   JSONB,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id          SERIAL PRIMARY KEY,
                user_id     INT REFERENCES users(id) ON DELETE CASCADE,
                role        TEXT NOT NULL,
                avg_score   INT NOT NULL,
                questions   INT NOT NULL,
                date        TEXT NOT NULL,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS session_questions (
                id          SERIAL PRIMARY KEY,
                session_id  INT REFERENCES sessions(id) ON DELETE CASCADE,
                question    TEXT,
                user_answer TEXT,
                score       INT,
                feedback    TEXT,
                ideal_answer TEXT,
                missed      TEXT
            );

            CREATE TABLE IF NOT EXISTS skill_gaps (
                id              SERIAL PRIMARY KEY,
                user_id         INT REFERENCES users(id) ON DELETE CASCADE,
                target_role     TEXT,
                coverage        INT,
                present_skills  TEXT[],
                missing_skills  TEXT[],
                learning_plan   JSONB,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            );
        """)
    print("✅ Database tables ready")
