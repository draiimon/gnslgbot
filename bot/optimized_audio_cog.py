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
        
        # ULTRA-HIGH QUALITY FFMPEG AUDIO SETTINGS FOR 2025
        # These settings provide the absolute best audio quality possible in Discord
        self.ffmpeg_options = {
            'options': '-f opus -ac 2 -ar 48000 -b:a 256k -bufsize 512k -minrate 192k -maxrate 320k -preset medium -application audio -compression_level 10',
            'before_options': '-nostdin -threads 4'
        }
    
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
        print("✅ Audio Cog loaded with 2025 TTS implementation (Optimized for Replit)")
    
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
            # Read larger buffer size for better audio quality
            if self.closed:
                return b''
            return self.file.readframes(960)  # IMPROVED: Using larger frames for better quality
            
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
            
            # Create Edge TTS communicator - using the newest highest quality multilingual voice model
            # Best voices 2025:
            # - fil-PH-AngeloNeural (Filipino male)
            # - fil-PH-BlessicaNeural (Filipino female)
            # - en-US-GuyNeural (English premium)
            # - zh-CN-YunxiNeural (Chinese)
            # - ja-JP-KenjiNeural (Japanese)
            
            # INTELLIGENT VOICE SELECTION BY LANGUAGE DETECTION
            # Choose the most appropriate voice based on the message content
            
            def detect_language(text):
                """
                Simple language detection based on common words and patterns
                Returns the most likely language code for the best voice
                """
                text = text.lower()
                
                # Check for Filipino/Tagalog words and patterns
                tagalog_words = ['ako', 'ikaw', 'siya', 'tayo', 'kami', 'kayo', 'sila', 
                                 'ng', 'sa', 'ang', 'mga', 'naman', 'talaga', 'lang',
                                 'po', 'opo', 'salamat', 'kamusta', 'kumain', 'mahal',
                                 'gago', 'putang', 'tangina', 'bobo', 'tanga']
                
                # Check for English words and patterns
                english_words = ['i', 'you', 'he', 'she', 'we', 'they', 'the', 'a', 'an',
                                'is', 'are', 'was', 'were', 'have', 'has', 'had',
                                'will', 'would', 'could', 'should', 'hello', 'please', 'thank']
                
                # Check for Chinese characters
                chinese_chars = ['的', '一', '是', '不', '了', '在', '人', '有', '我',
                              '他', '这', '中', '大', '来', '上', '国', '个', '到', '说']
                
                # Check for Japanese characters (hiragana, katakana range)
                japanese_pattern = any(
                    ('\u3040' <= char <= '\u309f') or  # Hiragana
                    ('\u30a0' <= char <= '\u30ff')      # Katakana
                    for char in text
                )
                
                # Check for Korean characters
                korean_pattern = any('\uac00' <= char <= '\ud7a3' for char in text)
                
                # Count language indicators
                tagalog_count = sum(word in text for word in tagalog_words)
                english_count = sum(word in text.split() for word in english_words)
                chinese_count = sum(char in text for char in chinese_chars)
                
                # Determine primary language
                language_scores = {
                    "fil": tagalog_count * 2,  # Give Filipino higher weight for our use case
                    "en": english_count,
                    "zh": chinese_count * 3,   # Chinese needs fewer characters to be detected
                    "ja": 10 if japanese_pattern else 0,
                    "ko": 10 if korean_pattern else 0
                }
                
                # Get language with highest score
                primary_language = max(language_scores.items(), key=lambda x: x[1])
                
                # If no strong language detected, default to Filipino
                if primary_language[1] <= 1:
                    return "fil"
                    
                return primary_language[0]
            
            # Detect language
            detected_lang = detect_language(message)
            
            # Choose appropriate voice based on detected language
            voices = {
                "fil": "fil-PH-AngeloNeural",     # Filipino male
                "en": "en-US-GuyNeural",          # English male (premium quality)
                "zh": "zh-CN-YunxiNeural",        # Chinese male (high quality)
                "ja": "ja-JP-KenjiNeural",        # Japanese male
                "ko": "ko-KR-InJoonNeural"        # Korean male
            }
            
            # Get voice based on detected language
            voice = voices.get(detected_lang, "fil-PH-AngeloNeural")  # Default to Filipino if language not supported
            
            print(f"Detected language: {detected_lang}, using voice: {voice}")
            
            # Use direct text without SSML to ensure compatibility
            tts = edge_tts.Communicate(text=message, voice=voice)
            
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
            
            # FALLBACK METHOD FIRST - Use our PCMStream method directly
            # This works even without opus library loaded
            try:
                # Get existing voice client or create a new one
                voice_client = ctx.voice_client
                if not voice_client:
                    print(f"Connecting to voice channel: {voice_channel.name}")
                    voice_client = await voice_channel.connect()
                elif voice_client.channel.id != voice_channel.id:
                    print(f"Moving to different voice channel: {voice_channel.name}")
                    await voice_client.move_to(voice_channel)
                
                # Convert MP3 to WAV with proper format for Discord
                from pydub import AudioSegment
                wav_filename = f"{self.temp_dir}/tts_wav_{ctx.message.id}.wav"
                
                # Convert using pydub with HIGH QUALITY settings (stereo, highest quality)
                audio = AudioSegment.from_mp3(mp3_filename)
                audio = audio.set_frame_rate(48000).set_channels(2)  # HIGH QUALITY: stereo, highest sample rate
                audio.export(wav_filename, format="wav", parameters=["-q:a", "0"])
                
                # Use our custom PCM streaming
                source = self.PCMStream(wav_filename)
                
                # Check if already playing and wait for it to finish
                if voice_client.is_playing():
                    print("Audio already playing, waiting for it to finish first...")
                    await ctx.send("**SANDALI LANG!** May pinapatugtog pa ako!", delete_after=5)
                    while voice_client.is_playing():
                        await asyncio.sleep(0.5)
                
                voice_client.play(source)
                
                # Success message for direct PCM method
                try:
                    await processing_msg.delete()
                except:
                    pass  # Message may have been deleted already
                await ctx.send(f"🔊 **SPEAKING:** {message}", delete_after=10)
                
                # Wait for playback to finish
                while voice_client.is_playing():
                    await asyncio.sleep(0.5)
                
                # Clean up WAV file
                try:
                    os.remove(wav_filename)
                except:
                    pass
                    
            except Exception as pcm_error:
                # If PCM method fails, try FFmpeg with optimized settings
                try:
                    print(f"PCM method failed: {pcm_error}, trying FFmpeg with optimized settings...")
                    voice_client = ctx.voice_client
                    if not voice_client:
                        voice_client = await voice_channel.connect()
                    
                    # Create audio source from the MP3 file with HIGH QUALITY settings
                    # Stereo audio, high bitrate, optimal buffer - for crisp clear audio
                    audio_source = discord.FFmpegPCMAudio(mp3_filename, **self.ffmpeg_options)
                    
                    # Apply volume transformer with lower volume to reduce processing
                    audio = discord.PCMVolumeTransformer(audio_source, volume=1.0)
                    
                    # Check if already playing and wait for it to finish
                    if voice_client.is_playing():
                        print("Audio already playing, waiting for it to finish first...")
                        await ctx.send("**SANDALI LANG!** May pinapatugtog pa ako!", delete_after=5)
                        while voice_client.is_playing():
                            await asyncio.sleep(0.5)
                            
                    # Play the audio file
                    voice_client.play(audio)
                    print(f"Playing TTS audio with optimized FFmpeg settings: {mp3_filename}")
                    
                    # Success message
                    try:
                        await processing_msg.delete()
                    except:
                        pass  # Message may have been deleted already
                    await ctx.send(f"🔊 **SPEAKING (FFmpeg Mode):** {message}", delete_after=10)
                    
                    # Wait for the audio to finish playing
                    while voice_client.is_playing():
                        await asyncio.sleep(0.5)
                    
                except Exception as ffmpeg_error:
                    # Both methods failed
                    print(f"Both PCM and FFmpeg playback failed: {ffmpeg_error}")
                    
                    # Even if playback fails, we've still generated the TTS
                    await processing_msg.delete()
                    await ctx.send(f"🔊 **TTS GENERATED:** {message}\n\n(Audio generated but couldn't be played. Error: {str(pcm_error)[:100]}...)", delete_after=15)
            
            # Clean up the files once we're done
            try:
                os.remove(mp3_filename)
                print(f"Removed temporary file: {mp3_filename}")
            except Exception as e:
                print(f"Error removing file: {e}")
            
            # Clean up old database entries
            cleanup_old_audio_tts(keep_count=20)
            print("✅ Cleaned up old TTS audio data, keeping 20 recent entries")
            
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
            
            # FALLBACK METHOD FIRST - Use our PCMStream method directly
            # This works even without opus library loaded
            try:
                # Get existing voice client or create a new one
                voice_client = ctx.voice_client
                if not voice_client:
                    print(f"Connecting to voice channel: {voice_channel.name}")
                    voice_client = await voice_channel.connect()
                elif voice_client.channel.id != voice_channel.id:
                    print(f"Moving to different voice channel: {voice_channel.name}")
                    await voice_client.move_to(voice_channel)
                
                # Convert MP3 to WAV with proper format for Discord
                from pydub import AudioSegment
                wav_filename = f"{self.temp_dir}/replay_wav_{ctx.message.id}.wav"
                
                # Convert using pydub with HIGH QUALITY settings (stereo, highest quality)
                audio = AudioSegment.from_mp3(mp3_filename)
                audio = audio.set_frame_rate(48000).set_channels(2)  # HIGH QUALITY: stereo, highest sample rate
                audio.export(wav_filename, format="wav", parameters=["-q:a", "0"])
                
                # Use our custom PCM streaming
                source = self.PCMStream(wav_filename)
                
                # Check if already playing and wait for it to finish
                if voice_client.is_playing():
                    print("Audio already playing, waiting for it to finish first...")
                    await ctx.send("**SANDALI LANG!** May pinapatugtog pa ako!", delete_after=5)
                    while voice_client.is_playing():
                        await asyncio.sleep(0.5)
                
                voice_client.play(source)
                
                # Success message for direct PCM method
                try:
                    await processing_msg.delete()
                except:
                    pass  # Message may have been deleted already
                await ctx.send(f"🔊 **REPLAYING LAST MESSAGE**", delete_after=10)
                
                # Wait for playback to finish
                while voice_client.is_playing():
                    await asyncio.sleep(0.5)
                
                # Clean up WAV file
                try:
                    os.remove(wav_filename)
                except:
                    pass
                    
            except Exception as pcm_error:
                # If PCM method fails, try FFmpeg with optimized settings
                try:
                    print(f"PCM method failed: {pcm_error}, trying FFmpeg with optimized settings...")
                    voice_client = ctx.voice_client
                    if not voice_client:
                        voice_client = await voice_channel.connect()
                    
                    # Create audio source from the MP3 file with HIGH QUALITY settings
                    # Stereo audio, high bitrate, optimal buffer - for crisp clear audio
                    audio_source = discord.FFmpegPCMAudio(mp3_filename, **self.ffmpeg_options)
                    
                    # Apply volume transformer with lower volume to reduce processing
                    audio = discord.PCMVolumeTransformer(audio_source, volume=1.0)
                    
                    # Play the audio file
                    voice_client.play(audio)
                    print(f"Playing replay audio with optimized FFmpeg settings: {mp3_filename}")
                    
                    # Success message
                    await processing_msg.delete()
                    await ctx.send(f"🔊 **REPLAYING LAST MESSAGE (FFmpeg Mode)**", delete_after=10)
                    
                    # Wait for the audio to finish playing
                    while voice_client.is_playing():
                        await asyncio.sleep(0.5)
                    
                except Exception as ffmpeg_error:
                    # Both methods failed
                    print(f"Both PCM and FFmpeg playback failed: {ffmpeg_error}")
                    
                    # Even if playback fails, we've still generated the TTS
                    await processing_msg.delete()
                    await ctx.send(f"🔊 **REPLAY GENERATED BUT PLAYBACK FAILED**\n\n(Error: {str(pcm_error)[:100]}...)", delete_after=15)
            
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

def setup(bot):
    """Add cog to bot"""
    bot.add_cog(AudioCog(bot))
    print("✅ NEW AudioCog loaded (No Lavalink Required)")