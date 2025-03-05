import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    GROQ_API_KEY = os.getenv('GROQ_API_KEY')
    COMMAND_PREFIX = 'g!'

    # Channel IDs 
    RULES_CHANNEL_ID = 1345727358015115385
    ANNOUNCEMENTS_CHANNEL_ID = 1345727358015115389
    AUTO_MESSAGE_CHANNEL_ID = 1345727363341746194
    JOCKIE_MUSIC_USER_ID = 411916947773587456

    # Rate limiting settings
    RATE_LIMIT_MESSAGES = 5
    RATE_LIMIT_PERIOD = 60

    # Conversation memory settings
    MAX_CONTEXT_MESSAGES = 5

    # Groq API settings
    GROQ_MODEL = "mixtral-8x7b-32768"
    MAX_TOKENS = 800
    TEMPERATURE = 1.4

    # Bot personality settings
    BOT_LANGUAGE = "Tagalog"
    BOT_CREATOR = "Mason Calix 2025"
