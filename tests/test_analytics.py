"""
Tests for analytics module
"""
import sys
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import patch
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAnalytics:
    """Tests for analytics functionality."""
    
    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create temporary database for testing."""
        db_path = tmp_path / "test_analytics.db"
        with patch('src.analytics.DB_PATH', db_path):
            # Import after patching
            from src import analytics
            analytics.init_db()
            yield analytics
    
    def test_init_db_creates_tables(self, temp_db):
        """Test database initialization creates required tables."""
        conn = temp_db.get_connection()
        cursor = conn.cursor()
        
        # Check queries table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='queries'")
        assert cursor.fetchone() is not None
        
        # Check users table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        assert cursor.fetchone() is not None
        
        conn.close()
    
    def test_track_query(self, temp_db):
        """Test query tracking."""
        temp_db.track_query(
            user_id=12345,
            username="testuser",
            first_name="Test",
            query_type="text",
            query_text="Test query"
        )
        
        stats = temp_db.get_stats()
        assert stats['total_queries'] == 1
    
    def test_track_user(self, temp_db):
        """Test user tracking."""
        temp_db.track_user(
            user_id=12345,
            username="testuser",
            first_name="Test",
            last_name="User"
        )
        
        users = temp_db.get_user_list()
        assert len(users) == 1
        assert users[0]['username'] == "testuser"
    
    def test_rate_limit_allows_under_limit(self, temp_db):
        """Test rate limit allows queries under limit."""
        user_id = 99999
        
        # First query should be allowed
        is_allowed, remaining = temp_db.check_rate_limit(user_id, daily_limit=10)
        assert is_allowed is True
        assert remaining == 10
    
    def test_rate_limit_blocks_over_limit(self, temp_db):
        """Test rate limit blocks queries over limit."""
        user_id = 88888
        
        # Track 10 queries
        for i in range(10):
            temp_db.track_query(user_id, None, None, 'text', f'Query {i}')
        
        # 11th should be blocked
        is_allowed, remaining = temp_db.check_rate_limit(user_id, daily_limit=10)
        assert is_allowed is False
        assert remaining == 0
    
    def test_admin_bypasses_rate_limit(self, temp_db):
        """Test admin users bypass rate limit."""
        admin_id = 935438639  # Admin ID
        
        # Track many queries
        for i in range(20):
            temp_db.track_query(admin_id, None, None, 'text', f'Query {i}')
        
        # Should still be allowed
        is_allowed, remaining = temp_db.check_rate_limit(
            admin_id, 
            daily_limit=10, 
            admin_ids=[admin_id]
        )
        assert is_allowed is True
        assert remaining == 999  # Unlimited indicator
    
    def test_get_stats(self, temp_db):
        """Test statistics retrieval."""
        # Add some test data
        temp_db.track_query(1, "user1", "User One", 'text', 'Query 1')
        temp_db.track_query(1, "user1", "User One", 'voice', 'Query 2')
        temp_db.track_query(2, "user2", "User Two", 'text', 'Query 3')
        
        stats = temp_db.get_stats()
        
        assert stats['total_queries'] == 3
        assert stats['unique_users'] == 2
        assert 'text' in stats['by_type']
        assert 'voice' in stats['by_type']
    
    def test_get_user_daily_count(self, temp_db):
        """Test daily query count retrieval."""
        user_id = 77777
        
        # Track some queries
        temp_db.track_query(user_id, None, None, 'text', 'Query 1')
        temp_db.track_query(user_id, None, None, 'text', 'Query 2')
        temp_db.track_query(user_id, None, None, 'voice', 'Query 3')
        
        count = temp_db.get_user_daily_count(user_id)
        assert count == 3  # text and voice both count


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
