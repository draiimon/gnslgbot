import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration class
class Config:
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    GROQ_API_KEY = os.getenv('GROQ_API_KEY')
    SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
    SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
    COMMAND_PREFIX = 'g!'  

    # Channel IDs
    RULES_CHANNEL_ID = 1345727358015115385
    ANNOUNCEMENTS_CHANNEL_ID = 1345727358015115389
    AUTO_MESSAGE_CHANNEL_ID = 1345727358015115389  # Updated to use the announcements channel
    GREETINGS_CHANNEL_ID = 1345727358149328952  # Channel for morning/night greetings
    JOCKIE_MUSIC_USER_ID = 411916947773587456  
    
    # Greetings settings
    GOOD_MORNING_HOUR = 8  # 8:00 AM
    GOOD_NIGHT_HOUR = 22   # 10:00 PM

    # Rate limiting settings
    RATE_LIMIT_MESSAGES = 5  
    RATE_LIMIT_PERIOD = 60   

    # Conversation memory settings
    MAX_CONTEXT_MESSAGES = 10  # Increased for better conversation memory and coherence

    # Groq API settings
    GROQ_MODEL = "mistral-saba-24b"  # Using exactly Mistral-SABA-24B as requested
    MAX_TOKENS = 200  # Keep this to ensure concise responses
    TEMPERATURE = 0.7  # Lowered to be much more coherent and human-like

    # Bot personality settings
    BOT_LANGUAGE = "Tagalog"  
    BOT_PERSONALITY = "Aggressively Rude and Insulting"  # Added personality descriptor
    BOT_CREATOR = "Mason Calox 2025"
    
    # UI settings
    EMBED_COLOR_PRIMARY = 0xFF5733  # Bright orange-red
    EMBED_COLOR_SUCCESS = 0x33FF57  # Bright green
    EMBED_COLOR_ERROR = 0xFF3357    # Bright red
    EMBED_COLOR_INFO = 0x3357FF     # Bright blue
    
    # Lavalink settings - using a public Lavalink server
    LAVALINK_HOST = os.getenv('LAVALINK_HOST', 'lavalink.lexnet.cc')
    LAVALINK_PORT = int(os.getenv('LAVALINK_PORT', '443'))
    LAVALINK_PASSWORD = os.getenv('LAVALINK_PASSWORD', 'lexn3tl4v4')
    LAVALINK_SECURE = True  # Use SSL for this server
    
    # Alternative Lavalink servers (fallbacks)
    ALT_LAVALINK_SERVERS = [
        {
            'host': 'lavalink2.lexnet.cc',
            'port': 443, 
            'password': 'lexn3tl4v4',
            'secure': True
        },
        {
            'host': 'lavalink.devamop.in',
            'port': 443,
            'password': 'DevamOP',
            'secure': True
        },
        {
            'host': 'lava.link',
            'port': 80,
            'password': 'anything as a password',
            'secure': False
        }
    ]
