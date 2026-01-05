"""
SQLite database module for storing and retrieving shared prompt/response pairs.
"""

import sqlite3
import secrets
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
import json


# Database file path (in project root)
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
            view_count INTEGER DEFAULT 0
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

