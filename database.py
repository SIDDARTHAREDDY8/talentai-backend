"""
Database — async PostgreSQL via asyncpg.
Uses ALTER TABLE ... ADD COLUMN IF NOT EXISTS for safe schema migrations.
"""

import os
import asyncpg
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        # Strip sslmode from URL if present — asyncpg requires ssl kwarg instead
        url = DATABASE_URL.split("?")[0]
        _pool = await asyncpg.create_pool(
            url,
            min_size=1,
            max_size=10,
            statement_cache_size=0,
            ssl="require",
        )
    return _pool


async def get_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def create_tables():
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Core tables
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

        # Additive migrations — safe to run repeatedly
        new_columns = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'active';",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_expires_at TIMESTAMPTZ;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verify_token TEXT;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_token TEXT;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_expires TIMESTAMPTZ;",
            # OAuth — allows social login without a password
            "ALTER TABLE users ALTER COLUMN password DROP NOT NULL;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider TEXT;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_id TEXT;",
        ]
        for stmt in new_columns:
            await conn.execute(stmt)

        # Unique index so the same provider account can't link to two users
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS users_oauth_unique
            ON users (oauth_provider, oauth_id)
            WHERE oauth_provider IS NOT NULL;
        """)

    print("✅ Database tables ready")
