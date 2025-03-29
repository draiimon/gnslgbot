import os
import psycopg2
import psycopg2.extras
from datetime import datetime
import pytz

# Get the database URL from environment variables
DATABASE_URL = os.getenv('DATABASE_URL')

def get_connection():
    """Create a connection to the PostgreSQL database"""
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Initialize the database with required tables"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Create users table for economy system
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    coins BIGINT DEFAULT 50000,
                    last_daily TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create message_history table for conversation tracking
            cur.execute('''
                CREATE TABLE IF NOT EXISTS message_history (
                    id SERIAL PRIMARY KEY,
                    channel_id BIGINT,
                    is_user BOOLEAN,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create rate_limit table for tracking user command usage
            cur.execute('''
                CREATE TABLE IF NOT EXISTS rate_limit (
                    user_id BIGINT,
                    timestamp TIMESTAMP,
                    PRIMARY KEY (user_id, timestamp)
                )
            ''')
            
            # Create blackjack_games table for storing game state
            cur.execute('''
                CREATE TABLE IF NOT EXISTS blackjack_games (
                    user_id BIGINT PRIMARY KEY,
                    player_hand TEXT,
                    dealer_hand TEXT,
                    bet INTEGER,
                    game_state TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            print("✅ Database initialized successfully")

# User Balance Functions
def get_user_balance(user_id):
    """Get user's balance from the database"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT coins FROM users WHERE user_id = %s", (user_id,))
            result = cur.fetchone()
            if result:
                return result[0]
            else:
                # Create user if not exists
                cur.execute(
                    "INSERT INTO users (user_id, coins) VALUES (%s, %s) RETURNING coins", 
                    (user_id, 50000)
                )
                conn.commit()
                return 50000

def add_coins(user_id, amount):
    """Add coins to user's balance"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (user_id, coins) VALUES (%s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET coins = users.coins + %s, updated_at = CURRENT_TIMESTAMP "
                "RETURNING coins",
                (user_id, 50000 + amount, amount)
            )
            conn.commit()
            result = cur.fetchone()
            return result[0] if result else 50000

def deduct_coins(user_id, amount):
    """Deduct coins from user's balance"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Ensure user exists
            cur.execute(
                "INSERT INTO users (user_id, coins) VALUES (%s, %s) "
                "ON CONFLICT (user_id) DO NOTHING",
                (user_id, 50000)
            )
            
            # Deduct coins
            cur.execute(
                "UPDATE users SET coins = coins - %s, updated_at = CURRENT_TIMESTAMP "
                "WHERE user_id = %s AND coins >= %s RETURNING coins",
                (amount, user_id, amount)
            )
            result = cur.fetchone()
            conn.commit()
            
            if result:
                return result[0]
            return None  # Insufficient funds

def update_daily_cooldown(user_id):
    """Update user's daily claim timestamp"""
    ph_timezone = pytz.timezone('Asia/Manila')
    current_time = datetime.now(ph_timezone)
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET last_daily = %s, updated_at = CURRENT_TIMESTAMP "
                "WHERE user_id = %s",
                (current_time, user_id)
            )
            conn.commit()

def get_daily_cooldown(user_id):
    """Get user's last daily claim timestamp"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT last_daily FROM users WHERE user_id = %s", (user_id,))
            result = cur.fetchone()
            return result[0] if result else None

# Rate Limiting Functions
def add_rate_limit_entry(user_id):
    """Add a rate limit entry for a user"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rate_limit (user_id, timestamp) VALUES (%s, CURRENT_TIMESTAMP)",
                (user_id,)
            )
            conn.commit()

def is_rate_limited(user_id, limit=5, period_seconds=60):
    """Check if user is rate limited"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM rate_limit "
                "WHERE user_id = %s AND timestamp > NOW() - INTERVAL '%s seconds'",
                (user_id, period_seconds)
            )
            count = cur.fetchone()[0]
            return count >= limit

def clear_old_rate_limits():
    """Clean up old rate limit entries (older than 1 hour)"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rate_limit WHERE timestamp < NOW() - INTERVAL '1 hour'")
            conn.commit()

# Conversation History Functions
def add_to_conversation(channel_id, is_user, content):
    """Add a message to the conversation history"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO message_history (channel_id, is_user, content) VALUES (%s, %s, %s)",
                (channel_id, is_user, content)
            )
            conn.commit()

def get_conversation_history(channel_id, limit=10):
    """Get recent conversation history for a channel"""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                "SELECT is_user, content FROM message_history "
                "WHERE channel_id = %s ORDER BY timestamp DESC LIMIT %s",
                (channel_id, limit)
            )
            # Return in reverse order (oldest first)
            return reversed(cur.fetchall())

def clear_conversation_history(channel_id):
    """Clear conversation history for a channel"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM message_history WHERE channel_id = %s", (channel_id,))
            conn.commit()

# Blackjack Game Functions
def save_blackjack_game(user_id, player_hand, dealer_hand, bet, game_state):
    """Save blackjack game state"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO blackjack_games (user_id, player_hand, dealer_hand, bet, game_state) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET "
                "player_hand = %s, dealer_hand = %s, bet = %s, game_state = %s, last_updated = CURRENT_TIMESTAMP",
                (user_id, player_hand, dealer_hand, bet, game_state, 
                 player_hand, dealer_hand, bet, game_state)
            )
            conn.commit()

def get_blackjack_game(user_id):
    """Get blackjack game state"""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                "SELECT player_hand, dealer_hand, bet, game_state FROM blackjack_games WHERE user_id = %s",
                (user_id,)
            )
            return cur.fetchone()

def delete_blackjack_game(user_id):
    """Delete blackjack game state"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM blackjack_games WHERE user_id = %s", (user_id,))
            conn.commit()

# Leaderboard Functions
def get_leaderboard(limit=10):
    """Get top users by balance"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, coins FROM users ORDER BY coins DESC LIMIT %s",
                (limit,)
            )
            return cur.fetchall()