"""
Database configuration.
Manages connection settings for PostgreSQL.
"""

import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT",5433))
DB_NAME = os.environ.get("DB_NAME", "auditdoctape")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_POOL_MIN = int(os.environ.get("DB_POOL_MIN", 2))
DB_POOL_MAX = int(os.environ.get("DB_POOL_MAX", 10))
def get_connection_string() -> str:
    """Generate PostgreSQL connection string."""
    if DB_PASSWORD:
        return f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    else:
        return f"postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


if __name__ == "__main__":
    print("Database configuration:")
    print(f"  Host: {DB_HOST}")
    print(f"  Port: {DB_PORT}")
    print(f"  Database: {DB_NAME}")
    print(f"  User: {DB_USER}")
    print(f"  Pool: {DB_POOL_MIN}-{DB_POOL_MAX}")
    print(f"\nConnection string: {get_connection_string()}")

