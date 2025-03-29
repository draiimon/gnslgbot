import discord
from discord.ext import commands
import asyncio
import os
import datetime
import random
import logging
from urllib.parse import urlparse
import random

# Import for TTS
import edge_tts

# Import database functions for TTS storage
from bot.database import (
    store_audio_tts,
    get_latest_audio_tts,
    cleanup_old_audio_tts,
    is_rate_limited,
    add_rate_limit_entry
)

class AudioQueue:
    """A simple queue system for audio playback"""
    def __init__(self):
        self.queue = []
        self.current = None
        self.is_playing = False
        self.loop = False
    
    def add(self, item):
        """Add item to queue"""
        self.queue.append(item)
    
    def next(self):
        """Get next item from queue"""
        if not self.queue:
            self.current = None
            return None
        
        self.current = self.queue.pop(0)
        return self.current
    
    def clear(self):
        """Clear the queue"""
        self.queue = []
        self.current = None
    
    def is_empty(self):
        """Check if queue is empty"""
        return len(self.queue) == 0
    
    def get_queue(self):
        """Get all items in queue"""
        return self.queue

class AudioCog(commands.Cog):
    """Audio commands cog for Discord TTS and music playback (No Lavalink Required)"""
    
    def __init__(self, bot):
        self.bot = bot
        
        # Create temp directory if it doesn't exist
        self.temp_dir = "temp_audio"
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Dictionary to store voice clients and queues per guild
        self.guild_audio_data = {}
    
    def get_guild_data(self, guild_id):
        """Get or create guild audio data"""
        if guild_id not in self.guild_audio_data:
            self.guild_audio_data[guild_id] = {
                "queue": AudioQueue(),
                "last_channel": None
            }
        return self.guild_audio_data[guild_id]
    
    async def cog_load(self):
        """Initialize audio systems"""
        print("Initializing Direct Discord Audio System...")
        print("✅ Audio Cog loaded with 2025 TTS implementation")
    
    async def cog_unload(self):
        """Clean up when cog is unloaded"""
        # Disconnect all voice clients
        for guild in self.bot.guilds:
            if guild.voice_client:
                await guild.voice_client.disconnect()
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Track voice channel changes"""
        # Don't take action on bot movement
        if member.id == self.bot.user.id:
            return
        
        # Auto-join logic (when user joins an empty channel)
        if before.channel is None and after.channel is not None:
            # Count human members in the channel
            members_in_channel = len([m for m in after.channel.members if not m.bot])
            
            # If just one human (the person who joined)
            if members_in_channel == 1:
                # Check if we're already in a voice channel in this guild
                try:
                    voice_client = after.channel.guild.voice_client
                    if voice_client and voice_client.channel:
                        return  # Already connected
                except:
                    # Not connected, so we can join
                    try:
                        channel = after.channel
                        await channel.connect()
                        print(f"Auto-joined voice channel: {after.channel.name}")
                    except Exception as e:
                        print(f"Error auto-joining channel: {e}")
    
    @commands.command(name="joinvc")
    async def joinvc(self, ctx):
        """Join a voice channel using direct Discord voice client"""
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Get the user's channel
        channel = ctx.author.voice.channel
        print(f"Attempting to join channel: {channel.name} (ID: {channel.id})")
        
        try:
            # Check if already in a voice channel
            voice_client = ctx.guild.voice_client
            if voice_client and voice_client.channel and voice_client.channel.id == channel.id:
                return await ctx.send("**BOBO!** NASA VOICE CHANNEL MO NA AKO!")
            elif voice_client:
                print(f"Already connected to a different channel, disconnecting from {voice_client.channel.name}")
                await voice_client.disconnect()
            
            # Connect with direct Discord voice client
            print("Connecting with direct Discord voice client...")
            voice_client = await channel.connect()
            
            # Store channel for future reference
            guild_data = self.get_guild_data(ctx.guild.id)
            guild_data["last_channel"] = channel
            
            await ctx.send(f"**SIGE!** PAPASOK NA KO SA {channel.name}!")
            print(f"Successfully connected to {channel.name} with direct Discord voice client")
            
        except Exception as e:
            error_message = f"**ERROR:** {str(e)}"
            print(f"Error joining voice channel: {e}")
            import traceback
            traceback.print_exc()
            await ctx.send(error_message[:1900])  # Discord message length limit
    
    @commands.command(name="leavevc")
    async def leavevc(self, ctx):
        """Leave the voice channel"""
        try:
            voice_client = ctx.guild.voice_client
            if not voice_client or not voice_client.channel:
                return await ctx.send("**TANGA!** WALA AKO SA VOICE CHANNEL!")
            
            await voice_client.disconnect()
            
            # Clear guild data
            if ctx.guild.id in self.guild_audio_data:
                guild_data = self.guild_audio_data[ctx.guild.id]
                guild_data["queue"].clear()
            
            await ctx.send("**AYOS!** UMALIS NA KO!")
            
        except Exception as e:
            await ctx.send(f"**ERROR:** {str(e)}")
            print(f"Error leaving voice channel: {e}")
    
    # Custom PCM audio source that directly reads from WAV file
    class PCMStream(discord.AudioSource):
        def __init__(self, filename):
            import wave
            self.file = wave.open(filename, "rb")
            self.closed = False
            
        def read(self):
            # Read smaller buffer size (1920 bytes) for lower memory usage
            if self.closed:
                return b''
            return self.file.readframes(960)  # 960 samples = 1920 bytes for 16-bit stereo
            
        def is_opus(self):
            return False  # This is PCM, not Opus
            
        def cleanup(self):
            if not self.closed:
                self.file.close()
                self.closed = True
    
    @commands.command(name="vc")
    async def vc(self, ctx, *, message: str):
        """Text-to-speech using Edge TTS with direct Discord playback (2025 Method)"""
        # Check if user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Check rate limiting
        if is_rate_limited(ctx.author.id):
            return await ctx.send(f"**TEKA LANG {ctx.author.mention}!** Ang bilis mo mag-type! Hinay-hinay lang!")
        
        add_rate_limit_entry(ctx.author.id)
        
        # Send processing message
        processing_msg = await ctx.send("**SANDALI LANG!** Ginagawa ko pa yung audio...")
        
        try:
            # Generate TTS using edge_tts
            print(f"Generating Edge TTS for message: '{message}'")
            mp3_filename = f"{self.temp_dir}/tts_{ctx.message.id}.mp3"
            
            # Create Edge TTS communicator - use Tagalog/Filipino voice
            # Options: fil-PH-AngeloNeural (male), fil-PH-BlessicaNeural (female)
            # If these fail, fallback to en-US-JennyNeural or en-US-ChristopherNeural
            tts = edge_tts.Communicate(text=message, voice="fil-PH-BlessicaNeural")
            
            # Generate MP3 audio using Edge TTS API
            await tts.save(mp3_filename)
            print(f"Edge TTS file generated successfully: {mp3_filename}")
            
            # Verify file exists and has content
            if not os.path.exists(mp3_filename):
                raise Exception("Failed to generate Edge TTS file - file does not exist")
            
            if os.path.getsize(mp3_filename) == 0:
                raise Exception("Failed to generate Edge TTS file - file is empty")
                
            print(f"Edge TTS file saved: {mp3_filename} ({os.path.getsize(mp3_filename)} bytes)")
            
            # Store in database
            with open(mp3_filename, "rb") as f:
                audio_data = f.read()
                audio_id = store_audio_tts(ctx.author.id, message, audio_data)
                print(f"Stored Edge TTS in database with ID: {audio_id}")
            
            # Connect to the voice channel
            voice_channel = ctx.author.voice.channel
            
            try:
                # Get existing voice client or create a new one
                voice_client = ctx.voice_client
                if not voice_client:
                    print(f"Connecting to voice channel: {voice_channel.name}")
                    voice_client = await voice_channel.connect()
                elif voice_client.channel.id != voice_channel.id:
                    print(f"Moving to different voice channel: {voice_channel.name}")
                    await voice_client.move_to(voice_channel)
                
                # Create audio source from the MP3 file
                audio_source = discord.FFmpegPCMAudio(mp3_filename)
                
                # Apply volume transformer to normalize the audio
                audio = discord.PCMVolumeTransformer(audio_source, volume=1.0)
                
                # Play the audio file
                voice_client.play(audio)
                print(f"Playing TTS audio directly through Discord voice client: {mp3_filename}")
                
                # Success message
                await processing_msg.delete()
                await ctx.send(f"🔊 **SPEAKING:** {message}", delete_after=10)
                
                # Wait for the audio to finish playing
                while voice_client.is_playing():
                    await asyncio.sleep(0.5)
                
                # Don't disconnect - let the bot stay in channel 
                # We purposely avoid disconnecting to minimize join/leave spam
                
            except Exception as play_error:
                print(f"Discord playback error: {play_error}")
                import traceback
                traceback.print_exc()
                
                # If classic method fails, try with FFmpeg disabled (fallback)
                try:
                    # Fallback to using our PCMStream method
                    voice_client = ctx.voice_client
                    if not voice_client:
                        voice_client = await voice_channel.connect()
                    
                    # Convert MP3 to WAV with proper format for Discord
                    from pydub import AudioSegment
                    wav_filename = f"{self.temp_dir}/tts_wav_{ctx.message.id}.wav"
                    
                    # Convert using pydub with optimized settings
                    audio = AudioSegment.from_mp3(mp3_filename)
                    audio = audio.set_frame_rate(48000).set_channels(2)
                    audio.export(wav_filename, format="wav")
                    
                    # Use our custom PCM streaming
                    source = self.PCMStream(wav_filename)
                    voice_client.play(source)
                    
                    # Success message for fallback method
                    await processing_msg.delete()
                    await ctx.send(f"🔊 **SPEAKING (Fallback Mode):** {message}", delete_after=10)
                    
                    # Wait for playback to finish
                    while voice_client.is_playing():
                        await asyncio.sleep(0.5)
                    
                    # Clean up WAV file
                    try:
                        os.remove(wav_filename)
                    except:
                        pass
                        
                except Exception as fallback_error:
                    # Both methods failed
                    print(f"Fallback playback also failed: {fallback_error}")
                    
                    # Even if playback fails, we've still generated the TTS
                    await processing_msg.delete()
                    await ctx.send(f"🔊 **TTS GENERATED:** {message}\n\n(Audio generated but couldn't be played. Error: {str(play_error)[:100]}...)", delete_after=15)
                
            # Clean up the files once we're done
            try:
                os.remove(mp3_filename)
                print(f"Removed temporary file: {mp3_filename}")
            except Exception as e:
                print(f"Error removing file: {e}")
            
            # Clean up old database entries
            cleanup_old_audio_tts(keep_count=20)
            print("Cleaned up old TTS entries")
            
        except Exception as e:
            print(f"⚠️ EDGE TTS ERROR: {e}")
            import traceback
            traceback.print_exc()
            
            # Try to delete processing message
            try:
                await processing_msg.delete()
            except:
                pass
            
            # Send error message (truncate if too long)
            error_msg = f"**ERROR:** {str(e)}"
            await ctx.send(error_msg[:1900], delete_after=15)
    
    @commands.command(name="replay")
    async def replay(self, ctx):
        """Replay last TTS message from database using direct Discord playback (2025 Method)"""
        # Check if user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Get the latest audio entry
        audio_data = get_latest_audio_tts()
        if not audio_data:
            return await ctx.send("**WALA AKONG MAALALA!** Wala pa akong na-save na audio.")
        
        audio_id, audio_bytes = audio_data
        
        # Send processing message
        processing_msg = await ctx.send("**SANDALI LANG!** Ire-replay ko pa yung huling audio...")
        
        try:
            # Save audio to temp file
            mp3_filename = f"{self.temp_dir}/replay_{ctx.message.id}.mp3"
            
            with open(mp3_filename, "wb") as f:
                f.write(audio_bytes)
                
            print(f"Saved replay audio to file: {mp3_filename}")
            
            # Connect to the voice channel
            voice_channel = ctx.author.voice.channel
            
            try:
                # Get existing voice client or create a new one
                voice_client = ctx.voice_client
                if not voice_client:
                    print(f"Connecting to voice channel: {voice_channel.name}")
                    voice_client = await voice_channel.connect()
                elif voice_client.channel.id != voice_channel.id:
                    print(f"Moving to different voice channel: {voice_channel.name}")
                    await voice_client.move_to(voice_channel)
                
                # Create audio source from the MP3 file
                audio_source = discord.FFmpegPCMAudio(mp3_filename)
                
                # Apply volume transformer to normalize the audio
                audio = discord.PCMVolumeTransformer(audio_source, volume=1.0)
                
                # Play the audio file
                voice_client.play(audio)
                print(f"Playing replay audio directly through Discord voice client: {mp3_filename}")
                
                # Success message
                await processing_msg.delete()
                await ctx.send(f"🔊 **REPLAYING:** Last TTS message", delete_after=10)
                
                # Wait for the audio to finish playing
                while voice_client.is_playing():
                    await asyncio.sleep(0.5)
                
                # Don't disconnect - let the bot stay in channel
                
            except Exception as play_error:
                print(f"Discord replay error: {play_error}")
                import traceback
                traceback.print_exc()
                
                # If classic method fails, try with FFmpeg disabled (fallback)
                try:
                    # Fallback to using our PCMStream method
                    voice_client = ctx.voice_client
                    if not voice_client:
                        voice_client = await voice_channel.connect()
                    
                    # Convert MP3 to WAV with proper format for Discord
                    from pydub import AudioSegment
                    wav_filename = f"{self.temp_dir}/replay_wav_{ctx.message.id}.wav"
                    
                    # Convert using pydub with optimized settings
                    audio = AudioSegment.from_mp3(mp3_filename)
                    audio = audio.set_frame_rate(48000).set_channels(2)
                    audio.export(wav_filename, format="wav")
                    
                    # Use our custom PCM streaming
                    source = self.PCMStream(wav_filename)
                    voice_client.play(source)
                    
                    # Success message for fallback method
                    await processing_msg.delete()
                    await ctx.send(f"🔊 **REPLAYING (Fallback Mode):** Last TTS message", delete_after=10)
                    
                    # Wait for playback to finish
                    while voice_client.is_playing():
                        await asyncio.sleep(0.5)
                    
                    # Clean up WAV file
                    try:
                        os.remove(wav_filename)
                    except:
                        pass
                        
                except Exception as fallback_error:
                    # Both methods failed
                    print(f"Fallback replay also failed: {fallback_error}")
                    await processing_msg.delete()
                    await ctx.send(f"⚠️ **ERROR:** Could not replay TTS message: {str(play_error)[:100]}...", delete_after=15)
                
            # Clean up the files once we're done
            try:
                os.remove(mp3_filename)
                print(f"Removed temporary file: {mp3_filename}")
            except Exception as e:
                print(f"Error removing file: {e}")
            
        except Exception as e:
            print(f"⚠️ REPLAY ERROR: {e}")
            import traceback
            traceback.print_exc()
            
            # Try to delete processing message
            try:
                await processing_msg.delete()
            except:
                pass
            
            # Send error message (truncate if too long)
            error_msg = f"**ERROR:** {str(e)}"
            await ctx.send(error_msg[:1900], delete_after=15)

    @commands.command(name="play")
    async def play(self, ctx, *, query: str):
        """Play a youtube url using youtube_dl and FFmpeg"""
        # Check if user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
            
        # Send searching message
        await ctx.send(f"🔍 Searching for: {query}")
        
        # This is a placeholder since we're not implementing full YouTube support
        # Without Lavalink, YouTube playback requires youtube_dl or yt-dlp
        # which would need additional code and dependencies
        await ctx.send("**SORRY!** YouTube playback isn't implemented in the pure Discord version yet. Use g!vc for text-to-speech instead!")

def setup(bot):
    bot.add_cog(AudioCog(bot))