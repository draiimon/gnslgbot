import os
import discord
from discord.ext import commands
from bot.config import Config
from bot.cog import ChatCog
from flask import Flask
import threading

# Initialize Flask app
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

# Start Flask in a separate thread
def run_web():
    port = int(os.environ.get("PORT", 8080))  # Default to 8080
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web).start()  # Start the Flask server

# Initialize bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=Config.COMMAND_PREFIX, 
                   intents=intents,
                   help_command=None)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    print(f'Bot ID: {bot.user.id}')
    print('------')

    await bot.add_cog(ChatCog(bot))

def main():
    if not Config.DISCORD_TOKEN:
        print("Error: Discord token not found in environment variables")
        return

    if not Config.GROQ_API_KEY:
        print("Error: Groq API key not found in environment variables")
        return

    try:
        bot.run(Config.DISCORD_TOKEN)
    except Exception as e:
        print(f"Error running bot: {e}")

if __name__ == "__main__":
    main()
