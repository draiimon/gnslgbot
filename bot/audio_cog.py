import discord
from discord.ext import commands
from gtts import gTTS
import io
import os
import asyncio
import time
import random
from .config import Config
from .database import (
    add_rate_limit_entry, 
    is_rate_limited, 
    store_audio_tts, 
    get_latest_audio_tts, 
    get_audio_tts_by_id,
    cleanup_old_audio_tts
)

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
            
    @commands.command(name="replay")
    async def replay(self, ctx):
        """Replay the last TTS message from database"""
        # Check if the user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Check rate limiting
        if is_rate_limited(ctx.author.id, limit=Config.RATE_LIMIT_MESSAGES, period_seconds=Config.RATE_LIMIT_PERIOD):
            return await ctx.send(f"**Huy {ctx.author.mention}!** Ang bilis mo naman magtype! Sandali lang muna, naglo-load pa ako!")
        
        # Add to rate limit
        add_rate_limit_entry(ctx.author.id)
        
        # Temporary file for FFmpeg playback
        temp_mp3 = "temp_tts.mp3"
        
        # Processing message
        processing_msg = None
        
        try:
            # First make sure we're connected to voice
            try:
                # Always disconnect first to ensure a clean connection
                if ctx.voice_client:
                    await ctx.voice_client.disconnect()
                    await asyncio.sleep(1)  # Wait for disconnection to complete
                
                # Connect to the user's channel - this must succeed before continuing
                voice_client = await ctx.author.voice.channel.connect()
                if not voice_client:
                    raise Exception("Failed to connect to voice channel")
                
                # Send processing message
                processing_msg = await ctx.send("**ANTAY KA MUNA!** Kinukuha ko yung last audio...")
                
                # Get latest audio from database
                latest_audio = get_latest_audio_tts()
                
                if not latest_audio or not latest_audio[1]:
                    raise Exception("No previous TTS audio found in database")
                
                audio_id = latest_audio[0]
                audio_data = latest_audio[1]
                
                # Save to temporary file for playback
                with open(temp_mp3, "wb") as f:
                    f.write(audio_data)
                
                # Verify file exists and has content
                if not os.path.exists(temp_mp3) or os.path.getsize(temp_mp3) == 0:
                    raise Exception("Failed to create audio file from database")
                
                print(f"✅ Loaded TTS audio from database with ID: {audio_id}")
                
                # Remove processing message if it exists
                try:
                    if processing_msg:
                        await processing_msg.delete()
                except Exception:
                    pass
                finally:
                    processing_msg = None
                
                # Define cleanup function - no need to delete the file as we'll reuse it
                def after_playing(error):
                    if error:
                        print(f"Audio playback error: {error}")
                
                # Simple FFmpeg source with minimal options
                audio_source = discord.FFmpegPCMAudio(
                    temp_mp3,
                    before_options="-nostdin",  # Avoid stdin interactions
                    options="-vn"  # Skip video processing
                )
                
                # Play the audio
                voice_client.play(audio_source, after=after_playing)
                
                # Send confirmation message
                await ctx.send(f"🔊 **REPLAY:** Audio ID: {audio_id}", delete_after=10)
                
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
            print(f"⚠️ REPLAY ERROR: {error_msg}")
            
            # Clean up processing message with proper error handling
            if processing_msg:
                try:
                    await processing_msg.delete()
                except:
                    pass
            
            # Send appropriate error message
            await ctx.send(f"**PUTANGINA MAY ERROR:** {error_msg}", delete_after=15)
    
    @commands.command(name="vc")
    async def vc(self, ctx, *, message: str):
        """Text-to-speech in voice channel using database storage"""
        # Check if the user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Check rate limiting
        if is_rate_limited(ctx.author.id, limit=Config.RATE_LIMIT_MESSAGES, period_seconds=Config.RATE_LIMIT_PERIOD):
            return await ctx.send(f"**Huy {ctx.author.mention}!** Ang bilis mo naman magtype! Sandali lang muna, naglo-load pa ako!")
        
        # Add to rate limit
        add_rate_limit_entry(ctx.author.id)
        
        # Temporary file for FFmpeg playback (required by Discord.py)
        temp_mp3 = "temp_tts.mp3"
        
        # Processing message
        processing_msg = None
        
        try:
            # Send processing message first
            processing_msg = await ctx.send("**ANTAY KA MUNA!** Ginagawa ko pa yung audio...")
            
            # Generate TTS with explicit lang setting
            tts = gTTS(text=message, lang='tl', slow=False)  # Default to Tagalog
            
            # Create a BytesIO object to get the binary data directly
            audio_io = io.BytesIO()
            tts.write_to_fp(audio_io)
            audio_data = audio_io.getvalue()
            
            # Store the audio in the database
            audio_id = store_audio_tts(ctx.author.id, message, audio_data)
            
            if not audio_id:
                raise Exception("Failed to store audio in database")
            
            print(f"✅ Stored TTS audio in database with ID: {audio_id}")
            
            # Save a temporary copy for FFmpeg to use
            with open(temp_mp3, "wb") as f:
                f.write(audio_data)
            
            # Verify file exists and has content
            if not os.path.exists(temp_mp3) or os.path.getsize(temp_mp3) == 0:
                raise Exception("Generated audio file is empty or missing")
            
            print(f"✅ Created temporary TTS file: {temp_mp3} (size: {os.path.getsize(temp_mp3)} bytes)")
            
            # COMPLETELY DIFFERENT APPROACH
            try:
                # Create a fixed unique filename based on the message ID
                temp_file_path = f"temp_audio/tts_{ctx.message.id}.mp3"
                
                # Save to the unique file
                with open(temp_file_path, "wb") as f:
                    f.write(audio_data)
                
                # For voice connection, use a much simpler approach
                voice_client = None
                
                # If already connected to the right channel, use it
                if ctx.voice_client and ctx.voice_client.channel == ctx.author.voice.channel:
                    voice_client = ctx.voice_client
                else:
                    # If connected to wrong channel or not connected
                    if ctx.voice_client:
                        await ctx.voice_client.disconnect()
                    
                    # Simple connect with no extras
                    voice_client = await ctx.author.voice.channel.connect()
                
                # Define a simpler callback function
                def after_playing(error):
                    if error:
                        print(f"Audio playback error: {error}")
                    try:
                        # Clean up the temp file after playing
                        if os.path.exists(temp_file_path):
                            os.remove(temp_file_path)
                    except Exception as cleanup_error:
                        print(f"Error cleaning up temp file: {cleanup_error}")
                
                # Create the simplest possible audio source
                audio_source = discord.FFmpegPCMAudio(source=temp_file_path)
                
                # Make sure we're not already playing something
                if voice_client.is_playing():
                    voice_client.stop()
                
                # Play the audio with minimal options
                voice_client.play(audio_source, after=after_playing)
                
                # Delete processing message
                if processing_msg:
                    await processing_msg.delete()
                
                # Send confirmation message
                await ctx.send(f"🔊 **SINABI KO NA** (ID: {audio_id}): {message}", delete_after=10)
                
                # Clean up old database entries
                cleanup_old_audio_tts(keep_count=20)
                
            except Exception as voice_error:
                print(f"Voice connection/playback error: {voice_error}")
                if processing_msg:
                    await processing_msg.delete()
                await ctx.send(f"**MAY PROBLEMA SA VOICE:** {str(voice_error)}", delete_after=10)
        
        except Exception as e:
            error_msg = str(e)
            print(f"⚠️ TTS ERROR: {error_msg}")
            
            # Clean up processing message
            if processing_msg:
                try:
                    await processing_msg.delete()
                except:
                    pass
            
            # Send error message
            await ctx.send(f"**PUTANGINA MAY ERROR:** {error_msg}", delete_after=15)

def setup(bot):
    """Add cog to bot"""
    bot.add_cog(AudioCog(bot))