# Discord Bot with Groq AI Integration

A Discord bot that uses Groq's AI capabilities to provide intelligent chat responses. The bot supports both chat and voice interactions, along with various server management features.

## Features

- AI-powered chat responses using Groq
- Voice channel interactions
- Server management commands
- Rate limiting for chat interactions
- Conversation memory
- Entertainment features (games)

## Requirements

- Python 3.11+
- Discord.py
- Flask
- Groq API
- PyNaCl
- python-dotenv

## Local Setup

1. Clone the repository:
```bash
git clone <your-repo-url>
cd discord-groq-bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the root directory with your API keys:
```
DISCORD_TOKEN=your_discord_token
GROQ_API_KEY=your_groq_api_key
```

4. Run the bot:
```bash
python main.py
```

## Commands

- `g!usap <message>` - Chat with the AI assistant
- `g!clear` - Clear conversation history
- `g!join` - Join voice channel
- `g!leave` - Leave voice channel
- `g!rules` - Display server rules
- `g!announcement` - Make an announcement
- `g!creator` - Show bot creator information
- `g!game` - Play a number guessing game
- `g!tulong` - Show help information

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
   - The `PORT` variable will be automatically set by Render

4. Deploy the service and your bot will be online!

## Important Notes

- The bot includes a keep-alive Flask server that prevents it from sleeping on free tier hosting
- Environment variables must be properly set for the bot to function
- Make sure your Discord bot has the necessary permissions in your server

## License

MIT License

## Creator

Created by Mason Calix 2025