import discord
from discord.ext import commands
from gtts import gTTS
import io
import os
import asyncio
import time
import random
from pydub import AudioSegment
from .config import Config
from .database import add_rate_limit_entry, is_rate_limited

class AudioCog(commands.Cog):
    """Cog for handling voice channel interactions and TTS"""

    def __init__(self, bot):
        self.bot = bot
        self.temp_dir = "temp_audio"
        # Create temp directory if it doesn't exist
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
        
        # For tracking voice connections
        self.voice_connections = {}

    async def cog_load(self):
        """Initialize cog resources"""
        print("✅ Audio Cog loaded")

    async def cog_unload(self):
        """Clean up when cog is unloaded"""
        # Disconnect from all voice channels
        for voice_client in self.bot.voice_clients:
            try:
                await voice_client.disconnect()
            except:
                pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Automatically connect to voice channels when a user joins"""
        # If the bot is disconnecting, don't do anything
        if member.id == self.bot.user.id and after.channel is None:
            return
        
        # If the member is joining a voice channel
        if before.channel is None and after.channel is not None:
            # Get all members in the channel
            members_in_channel = len([m for m in after.channel.members if not m.bot])
            
            # If there are only 1-2 members (the joining user plus possibly the bot)
            if members_in_channel == 1:
                # Check if the bot is already in any voice channel in this guild
                bot_voice = member.guild.voice_client
                
                # If bot is not in any voice channel, join the user's channel
                if bot_voice is None:
                    try:
                        # This will automatically disconnect from any other voice channels in other guilds
                        await after.channel.connect()
                        print(f"Auto-joined voice channel: {after.channel.name}")
                    except Exception as e:
                        print(f"Error auto-joining channel: {e}")
    
    @commands.command(name="joinvc")
    async def joinvc(self, ctx):
        """Join a voice channel"""
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        if ctx.voice_client and ctx.voice_client.channel == ctx.author.voice.channel:
            return await ctx.send("**BOBO!** NASA VOICE CHANNEL NA AKO!")
        
        try:
            # Disconnect from current channel if connected
            if ctx.voice_client:
                await ctx.voice_client.disconnect()
            
            # Connect to the user's channel
            await ctx.author.voice.channel.connect()
            await ctx.send(f"**SIGE!** PAPASOK NA KO SA {ctx.author.voice.channel.name}!")
        except Exception as e:
            await ctx.send(f"**ERROR:** {str(e)}")
            print(f"Error joining voice channel: {e}")
    
    @commands.command(name="leavevc")
    async def leavevc(self, ctx):
        """Leave the voice channel"""
        if not ctx.voice_client:
            return await ctx.send("**TANGA!** WALA AKO SA VOICE CHANNEL!")
        
        try:
            await ctx.voice_client.disconnect()
            await ctx.send("**AYOS!** UMALIS NA KO!")
        except Exception as e:
            await ctx.send(f"**ERROR:** {str(e)}")
            print(f"Error leaving voice channel: {e}")
    
    @commands.command(name="vc")
    async def vc(self, ctx, *, message: str):
        """Text-to-speech in voice channel with extremely simplified approach"""
        # Check if the user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Check rate limiting
        if is_rate_limited(ctx.author.id, limit=Config.RATE_LIMIT_MESSAGES, period_seconds=Config.RATE_LIMIT_PERIOD):
            return await ctx.send(f"**Huy {ctx.author.mention}!** Ang bilis mo naman magtype! Sandali lang muna, naglo-load pa ako!")
        
        # Add to rate limit
        add_rate_limit_entry(ctx.author.id)
        
        # Create a simple random filename - Use the current directory to avoid path issues
        unique_id = f"{int(time.time())}_{random.randint(1000, 9999)}"
        temp_mp3 = f"temp_tts.mp3"  # Use a fixed filename to avoid path issues
        
        # Processing message
        processing_msg = None
        
        try:
            # First make sure we're connected to voice
            try:
                # Always disconnect first to ensure a clean connection
                if ctx.voice_client:
                    await ctx.voice_client.disconnect()
                    await asyncio.sleep(1)  # Longer wait to ensure complete disconnection
                
                # Connect to the user's channel - this must succeed before continuing
                voice_client = await ctx.author.voice.channel.connect()
                if not voice_client:
                    raise Exception("Failed to connect to voice channel")
                
                # Send processing message
                processing_msg = await ctx.send("**ANTAY KA MUNA!** Ginagawa ko pa yung audio...")
                
                # Generate TTS with explicit lang setting
                tts = gTTS(text=message, lang='tl', slow=False)  # Default to Tagalog
                
                # Save directly to the main directory (avoid subdirectories)
                tts.save(temp_mp3)
                
                # Verify file exists and has content
                if not os.path.exists(temp_mp3):
                    raise Exception("Audio file not found after generation")
                
                if os.path.getsize(temp_mp3) == 0:
                    raise Exception("Generated audio file is empty")
                    
                # Report successful file creation
                print(f"✅ Created TTS file: {temp_mp3} (size: {os.path.getsize(temp_mp3)} bytes)")
                
                # Remove processing message if it exists
                try:
                    if processing_msg:
                        await processing_msg.delete()
                except Exception:
                    pass
                finally:
                    processing_msg = None
                
                # Define cleanup function
                def after_playing(error):
                    if error:
                        print(f"Audio playback error: {error}")
                    
                # Simple FFmpeg source with minimal options
                audio_source = discord.FFmpegPCMAudio(temp_mp3)
                
                # Play the audio
                voice_client.play(audio_source, after=after_playing)
                
                # Send confirmation message
                await ctx.send(f"🔊 **SINABI KO NA:** {message}", delete_after=10)
                
            except Exception as e:
                print(f"Voice connection error: {e}")
                # Try to always clean up the voice connection
                try:
                    if ctx.voice_client:
                        await ctx.voice_client.disconnect()
                except:
                    pass
                raise Exception(f"Voice connection error: {str(e)}")
            
        except Exception as e:
            error_msg = str(e)
            print(f"⚠️ TTS ERROR: {error_msg}")
            
            # Clean up processing message with proper error handling
            if processing_msg:
                try:
                    await processing_msg.delete()
                except:
                    pass
            
            # Send appropriate error message
            await ctx.send(f"**PUTANGINA MAY ERROR:** {error_msg}", delete_after=15)

def setup(bot):
    """Add cog to bot"""
    bot.add_cog(AudioCog(bot))