import os
import discord
from discord.ext import commands, tasks
from bot.config import Config
from bot.cog import ChatCog
from bot.speech_recognition_cog import SpeechRecognitionCog
from bot.enhanced_music_cog import EnhancedMusicCog  # Using the enhanced version
from bot.optimized_audio_cog import OptimizedMusicCog  # New YouTube and Spotify parser
from bot.lavalink_music_cog import LavalinkMusicCog  # No-download solution using Lavalink
from flask import Flask
import threading
import datetime
import random
import pytz  # For timezone support
from bot.database import init_db, init_audio_tts_table

# Initialize bot with command prefix and remove default help command
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=Config.COMMAND_PREFIX, 
                   intents=intents,
                   help_command=None)  # Removed default help command

# Global variables for tracking greetings
last_morning_greeting_date = None
last_night_greeting_date = None
maintenance_mode = False  # Global flag for maintenance mode

@bot.event
async def on_ready():
    """Called when the bot is ready"""
    print(f'✅ Logged in as {bot.user.name} ({bot.user.id})')
    print('------')

    # Initialize the database and audio TTS table
    init_db()
    init_audio_tts_table()
    
    # Ensure cogs are loaded in the correct order
    # Always load ChatCog first, since other cogs depend on it
    chat_cog = None
    if not bot.get_cog("ChatCog"):
        chat_cog = ChatCog(bot)
        await bot.add_cog(chat_cog)
        print("ChatCog initialized")
        print("✅ ChatCog loaded")
    else:
        chat_cog = bot.get_cog("ChatCog")
        print("ChatCog already loaded")
        
    # Audio Cog has been replaced by the enhanced options
    # if not bot.get_cog("AudioCog"):
    #    audio_cog = AudioCog(bot)
    #    await bot.add_cog(audio_cog)
    #    print("✅ Audio Cog loaded with 2025 TTS implementation (Optimized for Replit)")
        
    # Load new speech recognition cog with direct access to ChatCog's AI response method
    if not bot.get_cog("SpeechRecognitionCog"):
        speech_cog = SpeechRecognitionCog(bot)
        # Directly set the get_ai_response method
        if chat_cog:
            speech_cog.get_ai_response = chat_cog.get_ai_response
            print("✅ Manually connected AI response handler from ChatCog to SpeechRecognitionCog")
        await bot.add_cog(speech_cog)
        print("✅ Speech Recognition Cog loaded with voice command support")
    
    # Load enhanced music cog if not already loaded
    if not bot.get_cog("EnhancedMusicCog"):
        enhanced_music_cog = EnhancedMusicCog(bot)
        await bot.add_cog(enhanced_music_cog)
        print("🔊 Enhanced Music Cog loaded with Edge TTS and local audio support")
    
    # Load the optimized music cog with YouTube and Spotify parsing
    if not bot.get_cog("OptimizedMusicCog"):
        optimized_music_cog = OptimizedMusicCog(bot)
        await bot.add_cog(optimized_music_cog)
        print("🎵 Optimized Music Cog loaded with YouTube and Spotify parsing - NO API BLOCKS!")
        
    # Load the Lavalink music cog for streaming (no downloads)
    if not bot.get_cog("LavalinkMusicCog"):
        lavalink_music_cog = LavalinkMusicCog(bot)
        await bot.add_cog(lavalink_music_cog)
        print("🎧 Lavalink Music Cog loaded - NO DOWNLOAD STREAMING MODE!")
        
        # Display the streaming mode status clearly at startup
        if hasattr(lavalink_music_cog, 'lavalink_connected') and lavalink_music_cog.lavalink_connected:
            print("✅ Lavalink connection successful - Using advanced streaming")
        else:
            print("⚠️ Lavalink connection failed - Using reliable fallback YouTube parser")
            print("💡 Pro: More reliable in Replit environment")
            print("💡 Pro: No external server dependencies")
        
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
    global last_morning_greeting_date, last_night_greeting_date, maintenance_mode
    
    # Check if maintenance mode is enabled
    if maintenance_mode:
        print("Automated greetings disabled during maintenance")
        return
    
    # If not in maintenance mode, run the greetings code
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
