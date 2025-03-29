import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration class
class Config:
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    GROQ_API_KEY = os.getenv('GROQ_API_KEY')
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
