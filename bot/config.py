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
    
    # Unicode map for text conversion - bold font style
    UNICODE_MAP = {
        'A': '𝐀', 'B': '𝐁', 'C': '𝐂', 'D': '𝐃', 'E': '𝐄', 'F': '𝐅', 'G': '𝐆', 'H': '𝐇', 
        'I': '𝐈', 'J': '𝐉', 'K': '𝐊', 'L': '𝐋', 'M': '𝐌', 'N': '𝐍', 'O': '𝐎', 'P': '𝐏', 
        'Q': '𝐐', 'R': '𝐑', 'S': '𝐒', 'T': '𝐓', 'U': '𝐔', 'V': '𝐕', 'W': '𝐖', 'X': '𝐗', 
        'Y': '𝐘', 'Z': '𝐙',
        'a': '𝐚', 'b': '𝐛', 'c': '𝐜', 'd': '𝐝', 'e': '𝐞', 'f': '𝐟', 'g': '𝐠', 'h': '𝐡', 
        'i': '𝐢', 'j': '𝐣', 'k': '𝐤', 'l': '𝐥', 'm': '𝐦', 'n': '𝐧', 'o': '𝐨', 'p': '𝐩', 
        'q': '𝐪', 'r': '𝐫', 's': '𝐬', 't': '𝐭', 'u': '𝐮', 'v': '𝐯', 'w': '𝐰', 'x': '𝐱', 
        'y': '𝐲', 'z': '𝐳', 
        '0': '0', '1': '1', '2': '2', '3': '3', '4': '4', 
        '5': '5', '6': '6', '7': '7', '8': '8', '9': '9',
        ' ': ' ', '_': '_', '-': '-', '.': '.', ',': ',', '!': '!', '?': '?'
    }
    
    # Role IDs and Emojis - centralized configuration
    # This avoids duplicated data in cog.py
    ROLE_EMOJI_MAP = {
        705770837399306332: "👑",  # Owner
        1345727357662658603: "🌿",  # 𝐇𝐈𝐆𝐇
        1345727357645885448: "🍆",  # 𝐊𝐄𝐊𝐋𝐀𝐑𝐒
        1345727357645885449: "💦",  # 𝐓𝐀𝐌𝐎𝐃𝐄𝐑𝐀𝐓𝐎𝐑
        1345727357645885442: "🚀",  # 𝐀𝐒𝐀 𝐒𝐏𝐀𝐂𝐄𝐒𝐇𝐈𝐏
        1345727357612195890: "🌸",  # 𝐕𝐀𝐕𝐀𝐈𝐇𝐀𝐍
        1345727357612195889: "💪",  # 𝐁𝐎𝐒𝐒𝐈𝐍𝐆
        1345727357612195887: "☁️",  # 𝐁𝐖𝐈𝐒𝐈𝐓𝐀
        1345727357645885446: "🍑",  # 𝐁𝐎𝐓 𝐒𝐈 𝐁𝐇𝐈𝐄
        1345727357612195885: "🛑",  # 𝐁𝐎𝐁𝐎
    }
    
    ROLE_NAMES = {
        705770837399306332: "Owner",
        1345727357662658603: "𝐇𝐈𝐆𝐇",
        1345727357645885448: "𝐊𝐄𝐊𝐋𝐀𝐑𝐒",
        1345727357645885449: "𝐓𝐀𝐌𝐎𝐃𝐄𝐑𝐀𝐓𝐎𝐑",
        1345727357645885442: "𝐀𝐒𝐀 𝐒𝐏𝐀𝐂𝐄𝐒𝐇𝐈𝐏",
        1345727357612195890: "𝐕𝐀𝐕𝐀𝐈𝐇𝐀𝐍",
        1345727357612195889: "𝐁𝐎𝐒𝐒𝐈𝐍𝐆",
        1345727357612195887: "𝐁𝐖𝐈𝐒𝐈𝐓𝐀",
        1345727357645885446: "𝐁𝐎𝐓 𝐒𝐈 𝐁𝐇𝐈𝐄",
        1345727357612195885: "𝐁𝐎𝐁𝐎",
    }
    
    # Bots to ignore in nickname formatting
    BOTS_TO_IGNORE = [
        411916947773587456,  # Jockie Music
        294882584201003009,  # Sesh
        234395307759108106,  # Groovy
        235088799074484224,  # Rhythm 
        472911936951156740,  # Queue
        547905866255433758,  # Ear Tensifier
    ]
    
    # Admin role IDs for setupnn command permission
    ADMIN_ROLE_IDS = [
        1345727357662658603,  # 𝐇𝐈𝐆𝐇
        1345727357645885449,  # 𝐓𝐀𝐌𝐎𝐃𝐄𝐑𝐀𝐓𝐎𝐑
        1345727357645885448,  # 𝐊𝐄𝐊𝐋𝐀𝐑𝐒
    ]
    
    # UI settings
    EMBED_COLOR_PRIMARY = 0xFF5733  # Bright orange-red
    EMBED_COLOR_SUCCESS = 0x33FF57  # Bright green
    EMBED_COLOR_ERROR = 0xFF3357    # Bright red
    EMBED_COLOR_INFO = 0x3357FF     # Bright blue
    
    # Lavalink settings - using a known reliable Lavalink server (March 2025)
    LAVALINK_HOST = os.getenv('LAVALINK_HOST', 'lavalink.devamop.in')
    LAVALINK_PORT = int(os.getenv('LAVALINK_PORT', '443'))
    LAVALINK_PASSWORD = os.getenv('LAVALINK_PASSWORD', 'DevamOP')
    LAVALINK_SECURE = True  # Use SSL for this server
    
    # Alternative Lavalink servers (fallbacks)
    ALT_LAVALINK_SERVERS = [
        # March 2025 - Updated and tested server list
        {
            'host': 'lavalink4u.herokuapp.com',
            'port': 443,
            'password': 'passwords',
            'secure': True
        },
        {
            'host': 'lavalink.oops.wtf',
            'port': 2000,
            'password': 'www.freelavalink.herokuapp.com',
            'secure': False
        },
        {
            'host': 'lavalinkau.xtremebot.xyz',
            'port': 10232,
            'password': 'alivecapital12',
            'secure': False
        }
    ]
