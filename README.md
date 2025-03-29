# GNSLG Discord Bot with TTS & AI Integration

A Discord bot that combines Text-to-Speech (TTS) capabilities with Groq AI chatbot functionality. Built to provide real-time voice interactions in Discord channels along with aggressive Tagalog AI personality.

## Features

- Ultra-fast Text-to-Speech (TTS) using Edge TTS
- Auto-TTS functionality to automatically read messages in designated channels
- Multi-language voice detection (Tagalog, English, Chinese, Japanese, Korean)
- AI-powered chat responses using Groq's advanced models
- Auto-join voice channels and automatic disconnect after inactivity
- Economy system with games, daily rewards, and leaderboards
- Colorful embeds and aggressive Tagalog personality
- Rate limiting to prevent spam
- PostgreSQL database for data persistence

## Requirements

- Python 3.11+
- PostgreSQL database
- Discord bot token (from Discord Developer Portal)
- Groq API key (from Groq Cloud Console)

### Required Python Packages
- discord.py
- edge-tts
- groq
- PyNaCl
- psycopg2-binary
- pydub
- python-dotenv
- pytz
- flask

## Local Setup

1. Clone the repository:
```bash
git clone <your-repo-url>
cd gnslg-discord-bot
```

2. Install dependencies using Poetry (recommended) or pip:
```bash
# Using Poetry
poetry install

# Using pip
pip install -r requirements.txt
```

3. Set up a PostgreSQL database and get the connection URL

4. Create a `.env` file in the root directory with your API keys:
```
DISCORD_TOKEN=your_discord_token
GROQ_API_KEY=your_groq_api_key
DATABASE_URL=your_postgresql_database_url
```

5. Run the bot:
```bash
python main.py
```

## Commands

### Text-to-Speech Commands
- `g!vc <message>` - Convert text to speech in your current voice channel
- `g!autotts` - Toggle automatic TTS for all messages in the current channel
- `g!replay` - Replay the last TTS message
- `g!joinvc` - Make the bot join your voice channel
- `g!leavevc` - Make the bot leave the voice channel

### AI Chat Commands
- `g!usap <message>` - Chat with the AI assistant
- `g!clear_history` - Clear conversation history

### Economy & Games
- `g!daily` - Claim your daily ₱10,000 pesos
- `g!balance` - Check your current balance
- `g!toss <heads/tails> <bet>` - Bet on coin toss (h/t)
- `g!blackjack <bet>` - Play blackjack
- `g!hit` - Draw a card in Blackjack
- `g!stand` - End your turn in Blackjack
- `g!give <@user> <amount>` - Give coins to another user
- `g!leaderboard` - Display wealth rankings

### Server Management
- `g!announcement <message>` - Make an announcement
- `g!tulong` - Display help information

## Deployment on Render

1. Fork/Clone this repository to your GitHub account

2. Create a new Web Service on Render:
   - Connect your GitHub repository
   - Choose Python 3.11 as the runtime
   - Set the build command: `pip install -r requirements.txt`
   - Set the start command: `python main.py`

3. Add Environment Variables in Render:
   - Add `DISCORD_TOKEN` (from Discord Developer Portal)
   - Add `GROQ_API_KEY` (from Groq Cloud Console)
   - Add `DATABASE_URL` (from your PostgreSQL database provider)
   - The `PORT` variable will be automatically set by Render

4. Deploy the service and your bot will be online!

## Important Notes

- The bot includes a keep-alive Flask server that prevents it from sleeping on free tier hosting
- Environment variables must be properly set for the bot to function
- For Text-to-Speech functionality, the bot requires the following Discord permissions:
  - Connect to voice channels
  - Speak in voice channels
  - Send messages and embeds
  - Add reactions
- Auto-TTS can be toggled on/off for specific channels using the `g!autotts` command
- The bot automatically disconnects from voice channels after 2 minutes of inactivity
- To avoid spam, TTS messages are limited to 200 characters
- The bot can read messages in multiple languages (Tagalog, English, Chinese, Japanese, Korean)
- The PostgreSQL database stores audio data for the replay function, conversation history, and economy data

## License

MIT License

## Creator

Created by Mason Calix 2025