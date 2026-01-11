#!/usr/bin/env python3
"""
Script to clear all shares from the database.
Run this on Railway: python clear_shares.py
"""

import sqlite3
import os
from pathlib import Path

def clear_all_shares():
    # Database file path - use persistent volume on Railway like vector store
    if os.getenv("RAILWAY_ENVIRONMENT"):
        # Railway mounts persistent volumes at /data, or use custom path if specified
        volume_path = os.getenv("RAILWAY_VOLUME_PATH", "/data")
        db_path = Path(volume_path) / "shares.db"
    else:
        # Local development: store in project root
        db_path = Path(__file__).parent / "shares.db"

    print(f"Connecting to database: {db_path}")

    if not db_path.exists():
        print("Database file does not exist")
        return 0

    conn = sqlite3.connect(str(db_path))

    try:
        # Get count before deletion
        cursor = conn.execute("SELECT COUNT(*) FROM shares")
        count_before = cursor.fetchone()[0]
        print(f"Found {count_before} shares in database")

        # Delete all shares
        cursor = conn.execute("DELETE FROM shares")
        deleted_count = cursor.rowcount
        conn.commit()

        print(f"Successfully deleted {deleted_count} shares")

        # Verify deletion
        cursor = conn.execute("SELECT COUNT(*) FROM shares")
        count_after = cursor.fetchone()[0]
        print(f"Shares remaining: {count_after}")

        return deleted_count

    except Exception as e:
        print(f"Error clearing shares: {e}")
        return 0
    finally:
        conn.close()

if __name__ == "__main__":
    deleted = clear_all_shares()
    print(f"\nOperation completed. Deleted {deleted} shares.")