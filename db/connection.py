"""PostgreSQL connection factory."""

import logging

import psycopg2
import psycopg2.extensions

from config import settings

logger = logging.getLogger(__name__)


def get_connection() -> psycopg2.extensions.connection:
    """Open a new pg connection using creds from .env."""
    try:
        conn = psycopg2.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            dbname=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            connect_timeout=5,
            options="-c statement_timeout=30000",
        )
        logger.debug(
            "Connected to %s:%s/%s",
            settings.DB_HOST, settings.DB_PORT, settings.DB_NAME,
        )
        return conn
    except psycopg2.OperationalError as exc:
        logger.error("DB connection failed: %s", exc)
        raise
