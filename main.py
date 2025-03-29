import os
import discord
from discord.ext import commands, tasks
from bot.config import Config
from bot.cog import ChatCog
from flask import Flask
import threading
import datetime
import random
import pytz  # For timezone support
import wavelink  # For music playback with Lavalink
import subprocess
import asyncio
from bot.database import init_db, init_audio_tts_table

# Initialize bot with command prefix and remove default help command
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=Config.COMMAND_PREFIX, 
                   intents=intents,
                   help_command=None)  # Removed default help command

# Global variables for tracking greetings
last_morning_greeting_date = None
last_night_greeting_date = None
lavalink_process = None

async def clean_audio_temp():
    """Clean up temporary audio files at startup"""
    # Perform basic cleanup of temp audio files at startup
    try:
        print("Cleaning up temporary audio files...")
        temp_dir = "temp_audio"
        if os.path.exists(temp_dir):
            for file in os.listdir(temp_dir):
                try:
                    file_path = os.path.join(temp_dir, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        print(f"Deleted temp file: {file_path}")
                except Exception as e:
                    print(f"Error deleting temp file: {e}")
        
        # Ensure temp directory exists
        os.makedirs(temp_dir, exist_ok=True)
        print("✅ Temp audio directory ready")
        return True
    except Exception as e:
        print(f"Error in audio cleanup: {e}")
        return False

@bot.event
async def on_ready():
    """Called when the bot is ready"""
    print(f'✅ Logged in as {bot.user.name} ({bot.user.id})')
    print('------')

    # Initialize the database and audio TTS table
    init_db()
    init_audio_tts_table()
    
    # Start Lavalink server
    lavalink_started = await start_lavalink()
    
    # Connect to the Lavalink server with wavelink if started successfully
    if lavalink_started:
        # Connect to Lavalink node
        try:
            node = wavelink.Node(
                uri="http://localhost:2333",
                password="youshallnotpass"
            )
            await wavelink.Pool.connect(nodes=[node], client=bot)
            print("✅ Connected to Lavalink server")
        except Exception as e:
            print(f"⚠️ Failed to connect to Lavalink node: {e}")
    
    # Ensure cogs are loaded
    if not bot.get_cog("ChatCog"):
        await bot.add_cog(ChatCog(bot))
        print("ChatCog initialized")
        print("✅ ChatCog loaded")
    
    # Load optimized audio cog for TTS    
    from bot.optimized_audio_cog import AudioCog as OptimizedAudioCog
    if not bot.get_cog("OptimizedAudioCog"):
        await bot.add_cog(OptimizedAudioCog(bot))
        print("✅ TTS AudioCog loaded (Fast TTS with Edge TTS)")
    
    # Load music cog with Lavalink integration for music playback
    if lavalink_started:
        from bot.audio_cog import AudioCog
        if not bot.get_cog("AudioCog"):
            await bot.add_cog(AudioCog(bot))
            print("✅ Music AudioCog loaded (YouTube/Spotify playback)")
        
    # Start the greetings scheduler
    check_greetings.start()
    print("✅ Greetings scheduler started")
    
    # Send welcome message to a channel if it exists - COMMENTED OUT DURING MAINTENANCE
    # if Config.AUTO_MESSAGE_CHANNEL_ID:
    #     try:
    #         channel = bot.get_channel(Config.AUTO_MESSAGE_CHANNEL_ID)
    #         if channel:
    #             # Create cleaner welcome embed without images
    #             welcome_embed = discord.Embed(
    #                 title="**GNSLG BOT IS NOW ONLINE!**",
    #                 description="**GISING NA ANG PINAKA-KUPAL NA BOT SA DISCORD! PUTANGINA NIYO MGA GAGO! READY NA AKONG MANG-INSULTO!**\n\n" +
    #                            "**Try these commands:**\n" +
    #                            "• `g!usap <message>` - Chat with me (prepare to be insulted!)\n" +
    #                            "• `@GNSLG BOT <message>` - Just mention me and I'll respond!\n" +
    #                            "• `g!daily` - Get free ₱10,000 pesos\n" +
    #                            "• `g!tulong` - See all commands (kung di mo pa alam gago)",
    #                 color=Config.EMBED_COLOR_PRIMARY
    #             )
    #             welcome_embed.set_footer(text="GNSLG BOT | Created by Mason Calix 2025")
    #             
    #             await channel.send(embed=welcome_embed)
    #             print(f"✅ Sent welcome message to channel {Config.AUTO_MESSAGE_CHANNEL_ID}")
    #     except Exception as e:
    #         print(f"❌ Error sending welcome message: {e}")
    print("Welcome message disabled during maintenance")

@tasks.loop(minutes=1)
async def check_greetings():
    """Check if it's time to send good morning or good night greetings"""
    global last_morning_greeting_date, last_night_greeting_date
    
    # DISABLED DURING MAINTENANCE
    print("Automated greetings disabled during maintenance")
    return
    
    # Code below is commented out during maintenance
    """
    # Get current time in Philippines timezone (UTC+8)
    ph_timezone = pytz.timezone('Asia/Manila')
    now = datetime.datetime.now(ph_timezone)
    current_hour = now.hour
    current_date = now.date()
    
    # Get the greetings channel
    channel = bot.get_channel(Config.GREETINGS_CHANNEL_ID)
    if not channel:
        return
    
    # Check if it's time for good morning greeting (8:00 AM)
    if (current_hour == Config.GOOD_MORNING_HOUR and 
            (last_morning_greeting_date is None or last_morning_greeting_date != current_date)):
        
        # Get all online members
        online_members = [member for member in channel.guild.members 
                         if member.status == discord.Status.online and not member.bot]
        
        # If there are online members, mention them
        if online_members:
            mentions = " ".join([member.mention for member in online_members])
            morning_messages = [
                f"**MAGANDANG UMAGA MGA GAGO!** {mentions} GISING NA KAYO! DALI DALI TRABAHO NA!",
                f"**RISE AND SHINE MGA BOBO!** {mentions} TANGINA NIYO GISING NA! PRODUCTIVITY TIME!",
                f"**GOOD MORNING MOTHERFUCKERS!** {mentions} WELCOME TO ANOTHER DAY OF YOUR PATHETIC LIVES!",
                f"**HOY GISING NA!** {mentions} TANGHALI NA GAGO! DALI DALI MAG-TRABAHO KA NA!",
                f"**AYAN! UMAGA NA!** {mentions} BILISAN MO NA! SIBAT NA SA TRABAHO!"
            ]
            await channel.send(random.choice(morning_messages))
            
            # Update last greeting date
            last_morning_greeting_date = current_date
            print(f"✅ Sent good morning greeting at {now}")
    
    # Check if it's time for good night greeting (10:00 PM)
    elif (current_hour == Config.GOOD_NIGHT_HOUR and 
            (last_night_greeting_date is None or last_night_greeting_date != current_date)):
        
        night_messages = [
            "**TULOG NA MGA GAGO!** TANGINANG MGA YAN PUYAT PA MORE! UUBUSIN NIYO BUHAY NIYO SA DISCORD? MAAGA PA PASOK BUKAS!",
            "**GOOD NIGHT MGA HAYOP!** MATULOG NA KAYO WALA KAYONG MAPAPALA SA PAGIGING PUYAT!",
            "**HUWAG NA KAYO MAG-PUYAT GAGO!** MAAWA KAYO SA KATAWAN NIYO! PUTA TULOG NA KAYO!",
            "**10PM NA GAGO!** TULOG NA MGA WALA KAYONG DISIPLINA SA BUHAY! BILIS!",
            "**TANGINANG MGA TO! MAG TULOG NA KAYO!** WALA BA KAYONG TRABAHO BUKAS? UUBUSIN NIYO ORAS NIYO DITO SA DISCORD!"
        ]
        
        await channel.send(random.choice(night_messages))
        
        # Update last greeting date
        last_night_greeting_date = current_date
        print(f"✅ Sent good night greeting at {now}")
    """

@check_greetings.before_loop
async def before_check_greetings():
    await bot.wait_until_ready()

@bot.event
async def on_command_error(ctx, error):
    """Global error handler"""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("**WALANG GANYANG COMMAND!** BASA BASA DIN PAG MAY TIME!\nTRY MO `g!tulong` PARA DI KA KAKUPALKUPAL!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("**BOBO! KULANG YUNG COMMAND MO!** TYPE MO `g!tulong` PARA MALAMAN MO PAANO GAMITIN!")
    elif isinstance(error, commands.CheckFailure) or isinstance(error, commands.errors.CheckFailure):
        # Check which command was attempted
        if ctx.command and ctx.command.name == "g":
            await ctx.send(f"**KUPAL DI KANAMAN ADMIN!!!** {ctx.author.mention} **TANGINA MO!**")
        else:
            await ctx.send(f"**BOBO!** WALA KANG PERMISSION PARA GAMITIN YANG COMMAND NA YAN!")
    else:
        await ctx.send(f"**PUTANGINA MAY ERROR!** TAWAG KA NALANG ULIT MAMAYA!")
        print(f"Error: {error}")

def run_flask():
    """Runs a dummy Flask server to keep Render active"""
    app = Flask(__name__)

    @app.route('/')
    def home():
        return "✅ Bot is running!"

    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

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
