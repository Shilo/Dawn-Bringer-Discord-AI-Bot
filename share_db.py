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

# Short ID length (6 characters gives ~56 billion combinations)
SHORT_ID_LENGTH = 6


def get_db_connection():
    """Get a database connection, creating the database and table if needed."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Return rows as dict-like objects
    
    # Create table if it doesn't exist
    conn.execute("""
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
    """)
    
    conn.commit()
    return conn


def generate_short_id() -> str:
    """Generate a random short ID for sharing.
    
    Returns:
        A random alphanumeric string of SHORT_ID_LENGTH characters
    """
    alphabet = string.ascii_letters + string.digits  # a-z, A-Z, 0-9
    return ''.join(secrets.choice(alphabet) for _ in range(SHORT_ID_LENGTH))


def create_share(prompt: str, response: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    """Create a new share and return the short ID.
    
    Args:
        prompt: The user's prompt/question
        response: The AI's response
        metadata: Optional metadata dict (will be JSON-encoded)
        
    Returns:
        The short ID for the share
    """
    conn = get_db_connection()
    
    # Generate a unique short ID (retry if collision, though extremely unlikely)
    short_id = generate_short_id()
    max_retries = 10
    retries = 0
    
    while retries < max_retries:
        # Check if ID already exists
        cursor = conn.execute("SELECT id FROM shares WHERE id = ?", (short_id,))
        if cursor.fetchone() is None:
            break
        short_id = generate_short_id()
        retries += 1
    
    if retries >= max_retries:
        raise Exception("Failed to generate unique short ID after multiple attempts")
    
    # Store the share
    metadata_json = json.dumps(metadata) if metadata else None
    created_at = datetime.now(timezone.utc).isoformat()
    
    conn.execute(
        "INSERT INTO shares (id, prompt, response, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
        (short_id, prompt, response, created_at, metadata_json)
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
        (short_id,)
    )
    row = cursor.fetchone()

    if row is None:
        conn.close()
        return None

    # Increment view count
    conn.execute("UPDATE shares SET view_count = view_count + 1 WHERE id = ?", (short_id,))
    conn.commit()
    conn.close()

    # Parse metadata JSON if present
    metadata = None
    if row['metadata']:
        try:
            metadata = json.loads(row['metadata'])
        except json.JSONDecodeError:
            pass

    return {
        'id': row['id'],
        'prompt': row['prompt'],
        'response': row['response'],
        'created_at': row['created_at'],
        'metadata': metadata,
        'view_count': row['view_count']
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
        if 'preview_image' not in columns:
            # Add the columns if they don't exist
            conn.execute("ALTER TABLE shares ADD COLUMN preview_image BLOB")
            conn.execute("ALTER TABLE shares ADD COLUMN preview_generated_at TIMESTAMP")
            conn.commit()

        created_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE shares SET preview_image = ?, preview_generated_at = ? WHERE id = ?",
            (image_data, created_at, short_id)
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
        if 'preview_image' not in columns:
            return None  # Columns don't exist yet

        cursor = conn.execute(
            "SELECT preview_image, preview_generated_at FROM shares WHERE id = ?",
            (short_id,)
        )
        row = cursor.fetchone()

        if row is None or row['preview_image'] is None:
            return None

        # Check if the cached image is still valid (within 24 hours)
        if row['preview_generated_at']:
            generated_at = datetime.fromisoformat(row['preview_generated_at'].replace('Z', '+00:00'))
            age = datetime.now(timezone.utc) - generated_at
            if age.total_seconds() > 24 * 60 * 60:  # 24 hours
                # Image is too old, remove it
                conn.execute("UPDATE shares SET preview_image = NULL, preview_generated_at = NULL WHERE id = ?", (short_id,))
                conn.commit()
                return None

        return row['preview_image']

    except Exception as e:
        print(f"Error retrieving preview image: {e}")
        return None
    finally:
        conn.close()

