import os
import discord
from discord.ext import commands
from bot.config import Config
from bot.cog import ChatCog

# Initialize bot with command prefix and remove default help command
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=Config.COMMAND_PREFIX, 
                   intents=intents,
                   help_command=None)  # Removed default help command

@bot.event
async def on_ready():
    """Called when the bot is ready"""
    print(f'Logged in as {bot.user.name}')
    print(f'Bot ID: {bot.user.id}')
    print('------')

    # Add the chat cog
    await bot.add_cog(ChatCog(bot))

@bot.event
async def on_command_error(ctx, error):
    """Global error handler"""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("TANGINA MO! WALANG GANYANG COMMAND! BASA BASA DIN PAG MAY TIME! 🤬\nTANGA KA BA? TRY MO `g!tulong` PARA DI KA KAKUPALKUPAL! 😤")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("BOBO! KULANG YUNG COMMAND MO! TYPE MO `g!tulong` PARA MALAMAN MO PAANO GAMITIN! 🤬")
    else:
        await ctx.send(f"PUTANGINA MAY ERROR! TAWAG KA NALANG ULIT MAMAYA! 😫")
        print(f"Error: {error}")

def main():
    """Main function to run the bot"""
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
