"""
SQLite database module for storing and retrieving shared prompt/response pairs.
"""

import os
import sqlite3
import secrets
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
import json


# Database file path - use persistent volume on Railway like vector store
if os.getenv("RAILWAY_ENVIRONMENT"):
    # Railway mounts persistent volumes at /data, or use custom path if specified
    volume_path = os.getenv("RAILWAY_VOLUME_PATH", "/data")
    DB_PATH = Path(volume_path) / "shares.db"
else:
    # Local development: store in project root
    DB_PATH = Path(__file__).parent / "shares.db"

# Sequential ID alphabet: lowercase a-z excluding ambiguous characters (i,l) + digits 2-9
SEQUENTIAL_ALPHABET = "abcdefghjkmnopqrstuvwxyz23456789"  # 32 characters total


def increment_id(id_str: str) -> str:
    """Increment an ID string to the next one in lexicographic order.

    Args:
        id_str: The current ID string

    Returns:
        The next ID string in sequence
    """
    chars = list(id_str)
    base = len(SEQUENTIAL_ALPHABET)

    # Start from the rightmost character
    i = len(chars) - 1
    while i >= 0:
        current_index = SEQUENTIAL_ALPHABET.index(chars[i])
        if current_index < base - 1:
            # Can increment this character
            chars[i] = SEQUENTIAL_ALPHABET[current_index + 1]
            return "".join(chars)
        else:
            # This character is at max, set to first and carry over
            chars[i] = SEQUENTIAL_ALPHABET[0]
            i -= 1

    # If we carried over from the leftmost character, add a new character
    return SEQUENTIAL_ALPHABET[0] + "".join(chars)


def number_to_id(number: int) -> str:
    """Convert a number to its sequential ID string representation.

    Args:
        number: The numeric value to convert (0-based)

    Returns:
        The sequential ID string
    """
    if number < 0:
        raise ValueError("Number must be non-negative")

    if number == 0:
        return SEQUENTIAL_ALPHABET[0]

    # Generate IDs by incrementing from 'a'
    current_id = SEQUENTIAL_ALPHABET[0]
    for _ in range(number):
        current_id = increment_id(current_id)

    return current_id


def id_to_number(id_str: str) -> int:
    """Convert a sequential ID string to its numeric value.

    Args:
        id_str: The sequential ID string (e.g., 'a', 'b', 'aa', etc.)

    Returns:
        The numeric value of the ID
    """
    number = 0
    current_id = SEQUENTIAL_ALPHABET[0]

    while current_id != id_str:
        current_id = increment_id(current_id)
        number += 1
        if len(current_id) > len(id_str) + 1:  # Safety check
            raise ValueError(f"ID '{id_str}' not found in sequence")

    return number


def generate_next_sequential_id() -> str:
    """Generate the next available sequential ID.

    Returns:
        The next unused sequential ID string
    """
    conn = get_db_connection()

    try:
        # Get all existing IDs
        cursor = conn.execute("SELECT id FROM shares ORDER BY id")
        existing_ids = {row[0] for row in cursor.fetchall()}

        # Find the next available ID by checking sequentially
        number = 0
        while True:
            candidate_id = number_to_id(number)
            if candidate_id not in existing_ids:
                return candidate_id
            number += 1
    finally:
        conn.close()


def get_db_connection():
    """Get a database connection, creating the database and table if needed."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Return rows as dict-like objects

    # Create table if it doesn't exist
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS shares (
            id TEXT PRIMARY KEY,
            prompt TEXT NOT NULL,
            response TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL,
            metadata TEXT,
            view_count INTEGER DEFAULT 0,
            preview_image BLOB,
            preview_generated_at TIMESTAMP
        )
    """
    )

    conn.commit()
    return conn


def create_share(
    prompt: str, response: str, metadata: Optional[Dict[str, Any]] = None
) -> str:
    """Create a new share and return the sequential short ID.

    Args:
        prompt: The user's prompt/question
        response: The AI's response
        metadata: Optional metadata dict (will be JSON-encoded)

    Returns:
        The sequential short ID for the share
    """
    conn = get_db_connection()

    # Generate the next sequential ID (guaranteed to be unique)
    short_id = generate_next_sequential_id()

    # Store the share
    metadata_json = json.dumps(metadata) if metadata else None
    created_at = datetime.now(timezone.utc).isoformat()

    conn.execute(
        "INSERT INTO shares (id, prompt, response, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
        (short_id, prompt, response, created_at, metadata_json),
    )
    conn.commit()
    conn.close()

    return short_id


def get_share(short_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a share by its short ID.

    Args:
        short_id: The short ID of the share

    Returns:
        Dict with 'id', 'prompt', 'response', 'created_at', 'metadata', 'view_count'
        or None if not found
    """
    conn = get_db_connection()

    cursor = conn.execute(
        "SELECT id, prompt, response, created_at, metadata, view_count FROM shares WHERE id = ?",
        (short_id,),
    )
    row = cursor.fetchone()

    if row is None:
        conn.close()
        return None

    # Increment view count
    conn.execute(
        "UPDATE shares SET view_count = view_count + 1 WHERE id = ?", (short_id,)
    )
    conn.commit()
    conn.close()

    # Parse metadata JSON if present
    metadata = None
    if row["metadata"]:
        try:
            metadata = json.loads(row["metadata"])
        except json.JSONDecodeError:
            pass

    return {
        "id": row["id"],
        "prompt": row["prompt"],
        "response": row["response"],
        "created_at": row["created_at"],
        "metadata": metadata,
        "view_count": row["view_count"],
    }


def store_preview_image(short_id: str, image_data: bytes) -> bool:
    """Store a generated preview image for a share.

    Args:
        short_id: The short ID of the share
        image_data: The PNG image data as bytes

    Returns:
        True if stored successfully, False otherwise
    """
    conn = get_db_connection()

    try:
        # Check if preview_image column exists
        cursor = conn.execute("PRAGMA table_info(shares)")
        columns = [row[1] for row in cursor.fetchall()]
        if "preview_image" not in columns:
            # Add the columns if they don't exist
            conn.execute("ALTER TABLE shares ADD COLUMN preview_image BLOB")
            conn.execute("ALTER TABLE shares ADD COLUMN preview_generated_at TIMESTAMP")
            conn.commit()

        created_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE shares SET preview_image = ?, preview_generated_at = ? WHERE id = ?",
            (image_data, created_at, short_id),
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error storing preview image: {e}")
        return False
    finally:
        conn.close()


def get_preview_image(short_id: str) -> Optional[bytes]:
    """Retrieve a cached preview image for a share.

    Args:
        short_id: The short ID of the share

    Returns:
        Image data as bytes if cached and valid, None otherwise
    """
    conn = get_db_connection()

    try:
        # Check if preview_image column exists
        cursor = conn.execute("PRAGMA table_info(shares)")
        columns = [row[1] for row in cursor.fetchall()]
        if "preview_image" not in columns:
            return None  # Columns don't exist yet

        cursor = conn.execute(
            "SELECT preview_image, preview_generated_at FROM shares WHERE id = ?",
            (short_id,),
        )
        row = cursor.fetchone()

        if row is None or row["preview_image"] is None:
            return None

        # Check if the cached image is still valid (within 24 hours)
        if row["preview_generated_at"]:
            generated_at = datetime.fromisoformat(
                row["preview_generated_at"].replace("Z", "+00:00")
            )
            age = datetime.now(timezone.utc) - generated_at
            if age.total_seconds() > 24 * 60 * 60:  # 24 hours
                # Image is too old, remove it
                conn.execute(
                    "UPDATE shares SET preview_image = NULL, preview_generated_at = NULL WHERE id = ?",
                    (short_id,),
                )
                conn.commit()
                return None

        return row["preview_image"]

    except Exception as e:
        print(f"Error retrieving preview image: {e}")
        return None
    finally:
        conn.close()


def clear_preview_image(short_id: str) -> bool:
    """Clear the cached preview image for a share, forcing regeneration.

    Args:
        short_id: The short ID of the share

    Returns:
        True if the cache was cleared, False otherwise
    """
    conn = get_db_connection()

    try:
        cursor = conn.execute(
            """
            UPDATE shares
            SET preview_image = NULL, preview_generated_at = NULL
            WHERE id = ?
        """,
            (short_id,),
        )

        conn.commit()
        return cursor.rowcount > 0

    except Exception as e:
        print(f"Error clearing preview image: {e}")
        return False
    finally:
        conn.close()


def clear_all_preview_cache() -> int:
    """Clear cached preview images for all shares, forcing regeneration.

    Returns:
        int: Number of caches cleared
    """
    conn = get_db_connection()

    try:
        cursor = conn.execute(
            """
            UPDATE shares
            SET preview_image = NULL, preview_generated_at = NULL
            WHERE preview_image IS NOT NULL
        """
        )

        cleared_count = cursor.rowcount
        conn.commit()
        return cleared_count

    except Exception as e:
        print(f"Error clearing all preview cache: {e}")
        return 0
    finally:
        conn.close()


def clear_all_shares() -> int:
    """Delete all shares from the database.

    Returns:
        int: Number of shares deleted
    """
    conn = get_db_connection()

    try:
        cursor = conn.execute("DELETE FROM shares")
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count

    except Exception as e:
        print(f"Error clearing all shares: {e}")
        return 0
    finally:
        conn.close()
