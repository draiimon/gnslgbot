import os
import discord
from discord.ext import commands
from bot.config import Config
from bot.cog import ChatCog
from flask import Flask
import threading

# Initialize bot with command prefix and remove default help command
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=Config.COMMAND_PREFIX, 
                   intents=intents,
                   help_command=None)  # Removed default help command

@bot.event
async def on_ready():
    """Called when the bot is ready"""
    print(f'✅ Logged in as {bot.user.name} ({bot.user.id})')
    print('------')

    # Ensure cog is loaded
    if not bot.get_cog("ChatCog"):
        await bot.add_cog(ChatCog(bot))
        print("✅ ChatCog loaded")

@bot.event
async def on_command_error(ctx, error):
    """Global error handler"""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ WALANG GANYANG COMMAND! BASA BASA DIN PAG MAY TIME! 🤬\nTRY MO `g!tulong` PARA DI KA KAKUPALKUPAL! 😤")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("⚠️ BOBO! KULANG YUNG COMMAND MO! TYPE MO `g!tulong` PARA MALAMAN MO PAANO GAMITIN! 🤬")
    else:
        await ctx.send(f"⚠️ PUTANGINA MAY ERROR! TAWAG KA NALANG ULIT MAMAYA! 😫")
        print(f"⚠️ Error: {error}")

def run_flask():
    """Runs a dummy Flask server to keep Render active"""
    app = Flask(__name__)

    @app.route('/')
    def home():
        return "✅ Bot is running!"

    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

def main():
    """Main function to run the bot"""
    if not Config.DISCORD_TOKEN:
        print("❌ Error: Discord token not found in environment variables")
        return

    if not Config.GROQ_API_KEY:
        print("❌ Error: Groq API key not found in environment variables")
        return

    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Run the bot
    try:
        bot.run(Config.DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ Error running bot: {e}")

if __name__ == "__main__":
    main()
