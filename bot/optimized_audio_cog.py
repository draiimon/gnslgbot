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
        
        # Create temp directory if it doesn't exist - needed for legacy functions
        self.temp_dir = "temp_audio"
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Clean up any old temporary files on start
        try:
            for file in os.listdir(self.temp_dir):
                try:
                    file_path = os.path.join(self.temp_dir, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        print(f"Cleaned up old temp file: {file}")
                except Exception as e:
                    print(f"Error cleaning up file: {e}")
        except Exception as e:
            print(f"Error accessing temp directory: {e}")
            
        # Dictionary to store voice clients and queues per guild
        self.guild_audio_data = {}
        
        # Dictionary to store user voice gender preferences (m = male, f = female)
        # Default is male (m)
        self.user_voice_preferences = {}
        
        # Track auto-TTS channels
        self.auto_tts_channels = {}  # guild_id -> set of channel_ids
        
        # Track voice inactivity timers for auto-disconnect
        self.voice_inactivity_timers = {}  # guild_id -> timer
        
        # ZERO-LATENCY FFMPEG SETTINGS WITH NORMAL VOICE QUALITY
        # Balances instant response with natural sounding voice
        self.ffmpeg_options = {
            'options': '-ac 2 -ar 48000 -vn -b:a 128k -bufsize 128k',  # Normal voice pitch/quality
            'before_options': '-nostdin -threads 4 -probesize 1k -analyzeduration 0'
        }
        
        # For direct pipe streaming
        self.pipe_ffmpeg_options = {
            'pipe': True,
            'options': '-ac 2 -ar 48000 -f wav -vn -b:a 128k',  # Normal voice settings
            'before_options': '-nostdin'
        }
        
        # Track channels with AutoTTS enabled (guild_id -> set of channels)
        self.auto_tts_channels = {}
        # Track the last time a user has spoken to prevent repeated TTS
        self.last_user_speech = {}
        # Track voice inactivity for auto-disconnect
        self.voice_inactivity_timers = {}
        # Store user voice gender preferences ('m' or 'f')
        self.user_voice_preferences = {}
    
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
    async def on_message(self, message):
        """Process messages for auto-TTS functionality"""
        # Ignore messages from bots
        if message.author.bot:
            return
            
        # Check if auto-TTS is enabled for this channel
        guild_id = message.guild.id if message.guild else None
        channel_id = message.channel.id
        
        if guild_id and channel_id in self.auto_tts_channels.get(guild_id, set()):
            # Channel has auto-TTS enabled, process the message
            await self.process_auto_tts(message)
    
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
    
    # Fast TTS processing method, reused for both vc command and auto-tts
    async def process_tts(self, message_text, voice_channel, user_id, message_id, notify_channel=None):
        """Shared TTS processing logic for faster responses"""
        try:
            # Generate TTS using edge_tts
            print(f"Generating Edge TTS for message: '{message_text}'")
            mp3_filename = f"{self.temp_dir}/tts_{message_id}.mp3"
            
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
            detected_lang = detect_language(message_text)
            
            # Choose appropriate voice based on detected language and user preference
            # Define male and female voices for each language
            voices = {
                "fil": {
                    "m": "fil-PH-AngeloNeural",    # Filipino male
                    "f": "fil-PH-BlessicaNeural"   # Filipino female
                },
                "en": {
                    "m": "en-US-GuyNeural",        # English male
                    "f": "en-US-JennyNeural"       # English female
                },
                "zh": {
                    "m": "zh-CN-YunxiNeural",      # Chinese male
                    "f": "zh-CN-XiaoxiaoNeural"    # Chinese female
                },
                "ja": {
                    "m": "ja-JP-KenjiNeural",      # Japanese male
                    "f": "ja-JP-NanamiNeural"      # Japanese female
                },
                "ko": {
                    "m": "ko-KR-InJoonNeural",     # Korean male
                    "f": "ko-KR-SunHiNeural"       # Korean female
                }
            }
            
            # Get user preference (default to male if not set)
            gender_preference = self.user_voice_preferences.get(user_id, "m")
            
            # Get voice based on detected language and gender preference
            if detected_lang in voices:
                voice = voices[detected_lang][gender_preference]
            else:
                # Default to Filipino if language not supported
                voice = voices["fil"][gender_preference]
            
            print(f"Detected language: {detected_lang}, using {gender_preference} voice: {voice}")
            
            # Use direct text without SSML to ensure compatibility
            # Using faster speech rate with slightly increased volume for normal speed
            tts = edge_tts.Communicate(text=message_text, voice=voice, rate="+10%", volume="+30%")
            
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
                audio_id = store_audio_tts(user_id, message_text, audio_data)
                print(f"Stored Edge TTS in database with ID: {audio_id}")
            
            # Connect to the voice channel
            # Get existing voice client or create a new one
            guild = voice_channel.guild
            voice_client = guild.voice_client
            if not voice_client:
                print(f"Connecting to voice channel: {voice_channel.name}")
                voice_client = await voice_channel.connect()
            elif voice_client.channel.id != voice_channel.id:
                print(f"Moving to different voice channel: {voice_channel.name}")
                await voice_client.move_to(voice_channel)
            
            # Convert MP3 to WAV with proper format for Discord
            from pydub import AudioSegment
            wav_filename = f"{self.temp_dir}/tts_wav_{message_id}.wav"
            
            # Convert using pydub with HIGH QUALITY settings (stereo, highest quality)
            audio = AudioSegment.from_mp3(mp3_filename)
            audio = audio.set_frame_rate(48000).set_channels(2)  # HIGH QUALITY: stereo, highest sample rate
            audio.export(wav_filename, format="wav", parameters=["-q:a", "0"])
            
            # Use our custom PCM streaming
            source = self.PCMStream(wav_filename)
            
            # Check if already playing and wait for it to finish
            if voice_client.is_playing():
                print("Audio already playing, waiting for it to finish first...")
                if notify_channel:
                    await notify_channel.send("**SANDALI LANG!** May pinapatugtog pa ako!", delete_after=5)
                while voice_client.is_playing():
                    await asyncio.sleep(0.5)
            
            # Play the audio
            voice_client.play(source)
            print(f"Playing TTS audio: {message_text}")
            
            # Send confirmation if requested
            if notify_channel:
                await notify_channel.send(f"🔊 **SPEAKING:** {message_text}", delete_after=10)
            
            # Wait for playback to finish
            while voice_client.is_playing():
                await asyncio.sleep(0.5)
            
            # Clean up files
            try:
                os.remove(mp3_filename)
                os.remove(wav_filename)
                print(f"Removed temporary files for TTS ID: {audio_id}")
            except Exception as e:
                print(f"Error removing files: {e}")
            
            # Clean up old database entries
            cleanup_old_audio_tts(keep_count=20)
            
            return True
        except Exception as e:
            print(f"⚠️ TTS PROCESSING ERROR: {e}")
            import traceback
            traceback.print_exc()
            
            if notify_channel:
                error_msg = f"**ERROR:** {str(e)}"
                await notify_channel.send(error_msg[:1900], delete_after=15)
            
            return False
            
    # Auto-TTS feature removed as requested by user
            
    async def process_auto_tts(self, message):
        """Process TTS message automatically when user types in chat (ULTRA FAST)"""
        try:
            # Only process if all conditions are met
            if message.author.voice and len(message.content) > 0 and len(message.content) <= 200:
                # Don't use time-based rate limiting for auto-TTS messages
                # Just let all messages through, Discord's own rate limiting will prevent abuse
                # The only check we need is to make sure the bot doesn't speak its own confirmation messages
                if message.content.startswith('🔊'):
                    print(f"Skipping TTS for bot confirmation message")
                    return False
                
                # Update last speech time (using current timestamp)
                self.last_user_speech[message.author.id] = datetime.datetime.now()
                voice_channel = message.author.voice.channel
                
                # Detect language for detailed logging
                tagalog_markers = ['ako', 'ikaw', 'ang', 'nga', 'ng', 'sa', 'mga', 'naman', 'hindi', 'ito', 'lang', 'na', 'mo', 'ko', 'ba', 'po', 'ka', 'si', 'ni']
                tagalog_count = sum(1 for word in message.content.lower().split() if word in tagalog_markers)
                is_tagalog = tagalog_count >= 1 or 'ang' in message.content.lower() or 'ng ' in message.content.lower()
                detected_lang = "Tagalog" if is_tagalog else "English"
                
                # For ultra-fast TTS, we'll use direct streaming without file storage
                # New format: user's message directly without adding "said:" (much cleaner)
                tts_message = f"{message.content}"
                
                asyncio.create_task(
                    self.process_tts_direct(
                        tts_message, 
                        voice_channel, 
                        message.author.id,
                        message.id
                    )
                )
                print(f"Auto TTS: {message.author.name} -> '{message.content}' (Detected: {detected_lang})")
                return True
        except Exception as e:
            print(f"Auto TTS error: {e}")
        return False
        
    async def process_tts_direct(self, message_text, voice_channel, user_id, message_id):
        """ZERO-LATENCY TTS with real-time pipe streaming - 2025 implementation"""
        try:
            # PARALLEL EXECUTION: Start voice connection and TTS generation simultaneously
            # This is the key to absolute zero latency - we prepare both at the same time
            
            # STEP 1: Start voice connection task immediately
            voice_task = asyncio.create_task(self._ensure_voice_connection(voice_channel))
            
            # STEP 2: Simultaneously detect language for proper voice selection 
            # Enhanced with more accurate Tagalog detection
            tagalog_markers = ['ako', 'ikaw', 'ang', 'nga', 'ng', 'sa', 'mga', 'naman', 'hindi', 'ito', 'lang', 'na', 'mo', 'ko', 'ba', 'po', 'ka', 'si', 'ni']
            is_tagalog = any(word in message_text.lower().split() for word in tagalog_markers)
            # Additional check - count Tagalog markers for higher accuracy
            tagalog_count = sum(1 for word in message_text.lower().split() if word in tagalog_markers)
            is_definitely_tagalog = tagalog_count >= 2 or 'ang' in message_text.lower() or 'ng ' in message_text.lower()
            
            # STEP 3: Configure TTS with ultra-clear voice settings
            # Select voice based on detected language and user preference
            # Get user preference (default to male if not set)
            gender_preference = self.user_voice_preferences.get(user_id, "m")
            
            # Choose voice based on language and gender preference
            if is_tagalog or is_definitely_tagalog:
                # Filipino voices
                voice = "fil-PH-AngeloNeural" if gender_preference == "m" else "fil-PH-BlessicaNeural"
            else:
                # English voices
                voice = "en-US-GuyNeural" if gender_preference == "m" else "en-US-JennyNeural"
            
            # Configure TTS with the selected voice and enhanced settings
            # Using faster speech rate with slightly increased volume
            tts = edge_tts.Communicate(text=message_text, voice=voice, rate="+10%", volume="+30%")
            
            # STEP 4: IN-MEMORY TTS PROCESSING - No temporary files!
            # Get voice client from connection task first to avoid delays
            voice_client = await voice_task
            
            # Wait if already playing audio - prevent overlap (with short check intervals)
            if voice_client.is_playing():
                # Use shorter sleep intervals for faster response
                while voice_client.is_playing():
                    await asyncio.sleep(0.1)  # Check more frequently
            
            # STEP 5: DIRECT STREAMING - Generate audio and pipe directly to Discord
            # Log what we're doing for debugging
            detected_lang = "Tagalog" if is_tagalog or is_definitely_tagalog else "English"
            gender_type = "male" if gender_preference == "m" else "female"
            print(f"⚡️ ULTRA-FAST TTS: '{message_text}' (Detected: {detected_lang}, Using {gender_type} voice: {voice})")
            
            # Create a buffer to hold audio data in memory
            import io
            audio_buffer = io.BytesIO()
            
            # Stream the TTS data directly to our buffer
            async for audio_chunk in tts.stream():
                if audio_chunk["type"] == "audio":
                    audio_buffer.write(audio_chunk["data"])
            
            # Reset buffer position for reading
            audio_buffer.seek(0)
            
            # Set up FFmpeg to process the in-memory audio data
            import subprocess
            ffmpeg_cmd = ["ffmpeg", "-i", "pipe:0", "-ac", "2", "-ar", "48000", "-f", "wav", "pipe:1"]
            
            # Execute FFmpeg process with both stdin and stdout as pipes
            ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd, 
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, 
                stderr=subprocess.DEVNULL
            )
            
            # Feed our audio buffer to FFmpeg's stdin and get processed audio from stdout
            processed_audio, _ = ffmpeg_process.communicate(audio_buffer.read())
            
            # Create a BytesIO object for the processed audio
            processed_buffer = io.BytesIO(processed_audio)
            
            # Create a custom audio source from the processed data
            audio_source = discord.PCMAudio(processed_buffer)
            
            # Play the audio with minimal buffering for instant response
            voice_client.play(audio_source, after=lambda e: self.start_inactivity_timer(voice_client.guild.id, e))
            
        except Exception as e:
            print(f"⚠️ DIRECT TTS ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    async def _ensure_voice_connection(self, voice_channel):
        """Ensure voice connection exists and return voice client"""
        guild = voice_channel.guild
        voice_client = guild.voice_client
        
        if not voice_client:
            print(f"Connecting to voice channel: {voice_channel.name}")
            voice_client = await voice_channel.connect()
        elif voice_client.channel.id != voice_channel.id:
            print(f"Moving to different voice channel: {voice_channel.name}")
            await voice_client.move_to(voice_channel)
            
        return voice_client
    
    def cleanup_direct_tts(self, filename, error):
        """Clean up temporary file after direct TTS playback - LEGACY function kept for backward compatibility"""
        if error:
            print(f"Error in direct TTS playback: {error}")
        
        # If filename exists, remove it
        try:
            if filename and os.path.exists(filename):
                os.remove(filename)
                print(f"Removed direct TTS file: {filename}")
        except Exception as e:
            print(f"Error removing direct TTS file: {e}")
            
        # Start inactivity timer - extract guild id if possible
        try:
            # Get all voice clients
            for guild in self.bot.guilds:
                if guild.voice_client and guild.voice_client.is_connected():
                    guild_id = guild.id
                    self.start_inactivity_timer(guild_id, error)
        except Exception as e:
            print(f"Error setting up auto-disconnect: {e}")
            
    def start_inactivity_timer(self, guild_id, error=None):
        """Start timer to disconnect after period of inactivity"""
        if error:
            print(f"Error in direct TTS playback: {error}")
        
        try:
            # Cancel any existing timer
            if guild_id in self.voice_inactivity_timers:
                try:
                    self.voice_inactivity_timers[guild_id].cancel()
                except:
                    pass
            
            # Create and start a simple timer to disconnect after 120 seconds
            try:
                # Use a safer way to start the timer
                async def auto_disconnect_task():
                    try:
                        # Wait 2 minutes before disconnecting
                        await asyncio.sleep(120)
                        
                        # Get the current guild and voice client state at disconnect time
                        current_guild = self.bot.get_guild(guild_id)
                        if current_guild and current_guild.voice_client:
                            if current_guild.voice_client.is_connected() and not current_guild.voice_client.is_playing():
                                await current_guild.voice_client.disconnect()
                                print(f"Auto-disconnected from voice in {current_guild.name} due to 2 minutes of inactivity")
                    except Exception as e:
                        print(f"Error in auto-disconnect task: {e}")
                        
                # Schedule using the bot's loop instead of trying to get the current loop
                # This is safer and prevents threading issues
                self.voice_inactivity_timers[guild_id] = self.bot.loop.create_task(auto_disconnect_task())
                print(f"Started inactivity timer for guild ID: {guild_id}")
            except Exception as timer_error:
                print(f"Error starting disconnect timer: {timer_error}")
        except Exception as e:
            print(f"Error setting up auto-disconnect: {e}")
    
    @commands.command(name="vc", aliases=["say", "speak"])
    async def vc(self, ctx, *, message: str):
        """Text-to-speech using Edge TTS with INSTANT Discord playback (Ultra Fast 2025 Method)"""
        # Check if user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Send quick acknowledgment - immediately add reaction to show we're working
        await ctx.message.add_reaction("🔊")
        
        # ULTRA-FAST: Skip database, process directly
        # This makes response much faster with no delay
        asyncio.create_task(
            self.process_tts_direct(
                message, 
                ctx.author.voice.channel, 
                ctx.author.id,
                ctx.message.id
            )
        )
    
    @commands.command(name="autotts")
    async def auto_tts(self, ctx):
        """Toggle automatic TTS for all messages in the current channel"""
        guild_id = ctx.guild.id
        channel_id = ctx.channel.id
        
        # Initialize dictionary for this guild if needed
        if guild_id not in self.auto_tts_channels:
            self.auto_tts_channels[guild_id] = set()
            
        # Toggle auto-TTS for this channel
        if channel_id in self.auto_tts_channels[guild_id]:
            # Disable auto-TTS
            self.auto_tts_channels[guild_id].remove(channel_id)
            await ctx.send(f"**AUTO TTS DISABLED!** Hindi ko na automatic bibigkasin ang mga messages sa channel na ito.", delete_after=10)
        else:
            # Enable auto-TTS  
            self.auto_tts_channels[guild_id].add(channel_id)
            await ctx.send(f"**AUTO TTS ENABLED!** Automatic kong bibigkasin lahat ng messages sa channel na ito. Type normally!", delete_after=10)
        
        print(f"Auto TTS {'enabled' if channel_id in self.auto_tts_channels.get(guild_id, set()) else 'disabled'} for channel {ctx.channel.name}")
        
    @commands.command(name="resetvc")
    async def reset_vc(self, ctx):
        """Force reset all voice connections and clear audio queue"""
        # Disconnect from all voice channels
        try:
            voice_client = ctx.guild.voice_client
            if voice_client:
                await voice_client.disconnect()
                await ctx.send("**RESET COMPLETE!** Inalis ko ang sarili ko sa voice channel.", delete_after=10)
            else:
                await ctx.send("**TANGA!** Wala naman ako sa voice channel!", delete_after=10)
                
            # Also clear any guild data
            if ctx.guild.id in self.guild_audio_data:
                self.guild_audio_data[ctx.guild.id]["queue"].clear()
                
            # Clear any temporary files
            try:
                for filename in os.listdir(self.temp_dir):
                    if filename.startswith("tts_"):
                        try:
                            os.remove(os.path.join(self.temp_dir, filename))
                            print(f"Cleaned up file: {filename}")
                        except:
                            pass
            except:
                pass
                
            print(f"Voice connections reset for guild: {ctx.guild.name}")
            
        except Exception as e:
            await ctx.send(f"**ERROR:** {str(e)}", delete_after=10)
            print(f"Error resetting voice connections: {e}")
        
    @commands.command(name="change", aliases=["voice"])
    async def change_voice(self, ctx, voice_type: str):
        """Change your TTS voice gender (f = female, m = male)"""
        voice_type = voice_type.lower()
        if voice_type not in ["f", "m"]:
            return await ctx.send("**INVALID!** Use 'f' for female voice or 'm' for male voice.")
        
        # Update user preference
        self.user_voice_preferences[ctx.author.id] = voice_type
        
        # Confirm the change
        gender_name = "female" if voice_type == "f" else "male"
        await ctx.send(f"**VOICE CHANGED!** Your TTS voice is now set to **{gender_name}**.")
        print(f"User {ctx.author.name} changed voice preference to {gender_name}")
    
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
        
        audio_id, audio_bytes, message = audio_data
        
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
                # Display the original message that was converted to speech
                display_message = message[:100] + "..." if len(message) > 100 else message
                await ctx.send(f"🔊 **REPLAYING:** \"{display_message}\"", delete_after=10)
                
                # Wait for playback to finish
                while voice_client.is_playing():
                    await asyncio.sleep(0.5)
                
                # Clean up WAV file
                try:
                    os.remove(wav_filename)
                except:
                    pass
                    
            except Exception as pcm_error:
                # If PCM method fails, try pipe-based FFmpeg streaming (ZERO LATENCY)
                try:
                    print(f"PCM method failed: {pcm_error}, trying direct pipe streaming...")
                    voice_client = ctx.voice_client
                    if not voice_client:
                        voice_client = await voice_channel.connect()
                    
                    # PIPE-BASED STREAMING: Ultra-fast real-time audio playback
                    # Set up FFmpeg command for direct pipe streaming - with normal voice settings
                    import subprocess
                    ffmpeg_cmd = ["ffmpeg", "-i", mp3_filename, "-ac", "2", "-ar", "48000", "-f", "wav", "pipe:1"]
                    
                    # Execute FFmpeg as a process with pipe to stdout
                    ffmpeg_process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                    
                    # Create audio source directly from pipe (zero file I/O latency)
                    audio_source = discord.FFmpegPCMAudio(ffmpeg_process.stdout, pipe=True, **{
                        'options': '-ac 2 -ar 48000',  # Normal voice settings - avoid chipmunk
                        'before_options': '-nostdin'
                    })
                    
                    # Play the audio directly from pipe
                    voice_client.play(audio_source)
                    print(f"Playing replay audio with optimized FFmpeg settings: {mp3_filename}")
                    
                    # Success message
                    await processing_msg.delete()
                    # Display the original message that was converted to speech
                    display_message = message[:100] + "..." if len(message) > 100 else message
                    await ctx.send(f"🔊 **REPLAYING (FFmpeg Mode):** \"{display_message}\"", delete_after=10)
                    
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