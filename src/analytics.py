"""
Simple SQLite-based analytics for the Transito HP Bot
"""
import sqlite3
import os
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "analytics.db"


def get_connection():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the analytics database."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            first_name TEXT,
            query_type TEXT NOT NULL,  -- 'text', 'voice', 'command', 'document'
            query_text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_queries_user_id ON queries(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_queries_timestamp ON queries(timestamp)")
    
    conn.commit()
    conn.close()


def track_user(user_id: int, username: Optional[str], first_name: Optional[str], last_name: Optional[str] = None):
    """Track or update a user."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO users (user_id, username, first_name, last_name, first_seen, last_seen)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            username = COALESCE(excluded.username, users.username),
            first_name = COALESCE(excluded.first_name, users.first_name),
            last_name = COALESCE(excluded.last_name, users.last_name),
            last_seen = CURRENT_TIMESTAMP
    """, (user_id, username, first_name, last_name))
    
    conn.commit()
    conn.close()


def track_query(user_id: int, username: Optional[str], first_name: Optional[str], 
                query_type: str, query_text: Optional[str] = None):
    """Track a query."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO queries (user_id, username, first_name, query_type, query_text)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, username, first_name, query_type, query_text[:500] if query_text else None))
    
    conn.commit()
    conn.close()
    
    # Also update user record
    track_user(user_id, username, first_name)


def get_stats() -> dict:
    """Get overall statistics."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Total queries
    cursor.execute("SELECT COUNT(*) as total FROM queries")
    total_queries = cursor.fetchone()['total']
    
    # Unique users
    cursor.execute("SELECT COUNT(DISTINCT user_id) as total FROM queries")
    unique_users = cursor.fetchone()['total']
    
    # Queries by type
    cursor.execute("""
        SELECT query_type, COUNT(*) as count 
        FROM queries 
        GROUP BY query_type
    """)
    by_type = {row['query_type']: row['count'] for row in cursor.fetchall()}
    
    # Today's queries
    cursor.execute("""
        SELECT COUNT(*) as total FROM queries 
        WHERE date(timestamp) = date('now')
    """)
    today_queries = cursor.fetchone()['total']
    
    # This week's queries
    cursor.execute("""
        SELECT COUNT(*) as total FROM queries 
        WHERE timestamp >= datetime('now', '-7 days')
    """)
    week_queries = cursor.fetchone()['total']
    
    # Top users
    cursor.execute("""
        SELECT user_id, username, first_name, COUNT(*) as query_count
        FROM queries
        GROUP BY user_id
        ORDER BY query_count DESC
        LIMIT 10
    """)
    top_users = [dict(row) for row in cursor.fetchall()]
    
    # Recent users (last 24h)
    cursor.execute("""
        SELECT DISTINCT user_id, username, first_name
        FROM queries
        WHERE timestamp >= datetime('now', '-24 hours')
    """)
    recent_users = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        'total_queries': total_queries,
        'unique_users': unique_users,
        'by_type': by_type,
        'today_queries': today_queries,
        'week_queries': week_queries,
        'top_users': top_users,
        'recent_users': recent_users
    }


def get_user_list() -> list:
    """Get list of all users."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT u.user_id, u.username, u.first_name, u.last_name,
               u.first_seen, u.last_seen,
               COUNT(q.id) as query_count
        FROM users u
        LEFT JOIN queries q ON u.user_id = q.user_id
        GROUP BY u.user_id
        ORDER BY u.last_seen DESC
    """)
    
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return users


def get_user_daily_count(user_id: int) -> int:
    """Get number of queries a user has made today."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) as count FROM queries 
        WHERE user_id = ? 
        AND date(timestamp) = date('now')
        AND query_type IN ('text', 'voice')
    """, (user_id,))
    
    count = cursor.fetchone()['count']
    conn.close()
    
    return count


def check_rate_limit(user_id: int, daily_limit: int = 10, admin_ids: list = None) -> tuple[bool, int]:
    """
    Check if user has exceeded daily rate limit.
    
    Returns:
        tuple: (is_allowed, remaining_count)
            is_allowed: True if user can send more messages
            remaining_count: Number of messages remaining today
    """
    # Admins have unlimited access
    if admin_ids and user_id in admin_ids:
        return True, 999
    
    daily_count = get_user_daily_count(user_id)
    remaining = max(0, daily_limit - daily_count)
    is_allowed = daily_count < daily_limit
    
    return is_allowed, remaining


# Initialize DB on import
init_db()
