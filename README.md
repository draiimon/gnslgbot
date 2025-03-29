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

### Music Commands (YouTube)
- `g!ytplay <query>` - Play a song from YouTube (URL or search query)
- `g!ytplay <spotify URL>` - Play a song from Spotify (converted to YouTube)
- `g!ytskip` - Skip the current song
- `g!ytstop` - Stop playing and clear the queue
- `g!ytqueue` - Show the current queue
- `g!ytvolume <0-100>` - Set the volume
- `g!ytloop` - Toggle loop for current song
- `g!ytloopqueue` - Toggle loop for the entire queue
- `g!ytremove <index>` - Remove a song from the queue
- `g!ytleave` - Leave the voice channel

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
- `g!setupnn` - Set up automatic nickname formatting according to user roles
- `g!maintenance <on/off>` - Toggle maintenance mode (disables automated features)

## Docker Deployment

1. Build and run the Docker container:
```bash
# Build the Docker image
docker build -t ginsilog-bot .

# Run the container
docker run --env-file .env -d --name ginsilog-bot ginsilog-bot
```

2. Using Docker Compose:
```bash
# Start the bot using docker-compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the bot
docker-compose down
```

## Deployment on Render

1. Fork/Clone this repository to your GitHub account

2. Create a new Web Service on Render:
   - Connect your GitHub repository
   - Choose "Docker" as the environment
   - Set the branch to deploy from
   - Leave the build command empty (it will use the Dockerfile automatically)

3. Add Environment Variables in Render:
   - Add `DISCORD_TOKEN` (from Discord Developer Portal)
   - Add `GROQ_API_KEY` (from Groq Cloud Console)
   - Add `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` (from Spotify Developer Dashboard)
   - Add `DATABASE_URL` (from your PostgreSQL database provider)

4. Deploy the service and your bot will be online!

You can also use the `render.yaml` file in this repository to deploy directly from your GitHub repository to Render with all the necessary configuration.

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

### Nickname Formatting System

The bot includes an automatic nickname formatting system that:
- Converts members' names to a bold Unicode font format
- Adds role-specific emojis to nicknames based on the member's highest role
- Automatically updates nicknames when roles change
- Continuously scans and updates all nicknames every 10 seconds
- Handles special permissions for server owners and high-role users
- Can be enabled server-wide with the `g!setupnn` command (admin only)

## License

MIT License

## Creator

Created by Mason Calix 2025