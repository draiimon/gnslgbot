import os
import discord
from discord.ext import commands
from flask import Flask
import threading

# Load environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "g!")  # Default prefix if not set

# Flask Web Server (Keeps Render Service Alive)
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))  # Render uses dynamic ports
    app.run(host="0.0.0.0", port=port)

# Start Flask in a separate thread
threading.Thread(target=run_web).start()

# Initialize Discord bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=COMMAND_PREFIX, 
                   intents=intents,
                   help_command=None)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    print(f'Bot ID: {bot.user.id}')
    print('------')

    # Corrected: Do not await here (Cogs should be loaded synchronously)
    bot.add_cog(ChatCog(bot))

@bot.command(name="ping")
async def ping(ctx):
    """Check bot latency"""
    await ctx.send(f"Pong! {round(bot.latency * 1000)}ms")

def main():
    """Main function to run the bot"""
    if not DISCORD_TOKEN:
        print("Error: Discord token not found in environment variables")
        return

    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"Error running bot: {e}")

if __name__ == "__main__":
    main()
