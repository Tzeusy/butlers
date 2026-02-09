"""Database provisioning and connection pool management for butlers."""

from __future__ import annotations

import logging
import os

import asyncpg

logger = logging.getLogger(__name__)


class Database:
    """Manages asyncpg connection pool and database provisioning.

    Each butler owns a dedicated PostgreSQL database. This class handles
    creating the database if it doesn't exist (provisioning) and managing
    the asyncpg connection pool for runtime queries.
    """

    def __init__(
        self,
        db_name: str,
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
        password: str = "postgres",
        min_pool_size: int = 2,
        max_pool_size: int = 10,
    ) -> None:
        self.db_name = db_name
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self.pool: asyncpg.Pool | None = None

    async def provision(self) -> None:
        """Create the database if it doesn't exist.

        Connects to the 'postgres' maintenance database to check for and
        optionally create the butler's database.
        """
        conn = await asyncpg.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database="postgres",
        )
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1",
                self.db_name,
            )
            if not exists:
                # Can't use parameterized query for CREATE DATABASE
                # Sanitize db_name to prevent SQL injection
                safe_name = self.db_name.replace('"', '""')
                await conn.execute(f'CREATE DATABASE "{safe_name}"')
                logger.info("Created database: %s", self.db_name)
            else:
                logger.info("Database already exists: %s", self.db_name)
        finally:
            await conn.close()

    async def connect(self) -> asyncpg.Pool:
        """Create and return a connection pool to the butler's database."""
        self.pool = await asyncpg.create_pool(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.db_name,
            min_size=self.min_pool_size,
            max_size=self.max_pool_size,
        )
        logger.info("Connection pool created for: %s", self.db_name)
        return self.pool

    async def close(self) -> None:
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("Connection pool closed for: %s", self.db_name)

    @classmethod
    def from_env(cls, db_name: str) -> Database:
        """Create Database instance from environment variables.

        Reads POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, and
        POSTGRES_PASSWORD from the environment, falling back to defaults.
        """
        return cls(
            db_name=db_name,
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=int(os.environ.get("POSTGRES_PORT", "5432")),
            user=os.environ.get("POSTGRES_USER", "postgres"),
            password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
        )
