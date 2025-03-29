import asyncio
import discord
import os
import time
import tempfile
import wave
from pydub import AudioSegment
import speech_recognition as sr
from discord.ext import commands
import edge_tts

class SpeechRecognitionCog(commands.Cog):
    """Cog for handling speech recognition and voice interactions"""
    
    def __init__(self, bot):
        self.bot = bot
        self.listening_channels = {}  # guild_id: voice_channel
        self.recognizer = sr.Recognizer()
        self.voice_clients = {}  # guild_id: voice_client
        self.processing_audio = {}  # guild_id: boolean flag
        self.tts_queue = {}  # guild_id: list of messages to speak
        
        # Default voice settings
        self.default_voice = "en-US-GuyNeural"
        self.user_voice_prefs = {}  # user_id: "male" or "female"
        
        # Get Groq client from the bot (assuming it's stored there)
        self.get_ai_response = None  # This will be set when the cog is loaded
        
        print("✅ Speech Recognition Cog initialized")
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Called when the cog is ready"""
        # Try to get the get_ai_response method from ChatCog
        for cog in self.bot.cogs.values():
            if hasattr(cog, 'get_ai_response'):
                self.get_ai_response = cog.get_ai_response
                print("✅ Found AI response handler in ChatCog")
                break
        
        if not self.get_ai_response:
            print("❌ Could not find AI response handler")
    
    @commands.command()
    async def listen(self, ctx):
        """Start listening for voice commands in your current voice channel"""
        if not ctx.author.voice:
            await ctx.send("You need to be in a voice channel first!")
            return
        
        # Connect to the voice channel
        voice_channel = ctx.author.voice.channel
        if ctx.guild.id in self.voice_clients:
            # Already connected, just move to the new channel if needed
            if self.voice_clients[ctx.guild.id].channel.id != voice_channel.id:
                await self.voice_clients[ctx.guild.id].move_to(voice_channel)
        else:
            # Connect to new channel
            voice_client = await voice_channel.connect()
            self.voice_clients[ctx.guild.id] = voice_client
        
        # Start listening
        self.listening_channels[ctx.guild.id] = voice_channel
        self.processing_audio[ctx.guild.id] = False
        self.tts_queue[ctx.guild.id] = []
        
        await ctx.send(f"🎤 I'm now listening in **{voice_channel.name}**! Say something after mentioning me by name.")
        
        # Start the audio processing loop
        asyncio.create_task(self.process_voice_audio(ctx.guild.id))
    
    @commands.command()
    async def stoplisten(self, ctx):
        """Stop listening for voice commands"""
        if ctx.guild.id in self.listening_channels:
            # Clean up resources
            if ctx.guild.id in self.voice_clients:
                await self.voice_clients[ctx.guild.id].disconnect()
                del self.voice_clients[ctx.guild.id]
            
            del self.listening_channels[ctx.guild.id]
            self.processing_audio[ctx.guild.id] = False
            
            await ctx.send("🛑 I've stopped listening for voice commands.")
        else:
            await ctx.send("I wasn't listening in any channel.")
    
    async def process_voice_audio(self, guild_id):
        """Main loop to process voice audio from the guild"""
        if guild_id not in self.voice_clients:
            return
        
        # Create a sink to receive audio
        self.voice_clients[guild_id].start_recording(
            discord.sinks.WaveSink(),
            self.recording_finished,
            guild_id
        )
        
        # Let user know the bot is ready
        await self.speak_message(guild_id, "I'm ready to listen. Just say my name followed by your question.")
    
    def recording_finished(self, sink, guild_id):
        """Callback for when recording has finished"""
        # Process the recorded audio
        if guild_id in self.processing_audio and self.processing_audio[guild_id]:
            return  # Already processing
        
        self.processing_audio[guild_id] = True
        
        # Get the audio data
        recorded_users = [
            (user_id, audio)
            for user_id, audio in sink.audio_data.items()
        ]
        
        if not recorded_users:
            self.processing_audio[guild_id] = False
            return
        
        # Process each user's audio
        for user_id, audio_data in recorded_users:
            try:
                # Save to temporary file
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                    filename = f.name
                    f.write(audio_data.file.read())
                
                # Convert to format suitable for recognition
                sound = AudioSegment.from_wav(filename)
                sound = sound.set_channels(1)  # Mono
                sound = sound.set_frame_rate(16000)  # 16kHz
                sound.export(filename, format="wav")
                
                # Recognize speech
                with sr.AudioFile(filename) as source:
                    audio = self.recognizer.record(source)
                    try:
                        text = self.recognizer.recognize_google(audio)
                        if text and "ginslog bot" in text.lower():  # Replace with your bot's name
                            # Extract the actual command (remove bot's name)
                            command = text.lower().replace("ginslog bot", "").strip()
                            if command:
                                asyncio.create_task(self.handle_voice_command(guild_id, user_id, command))
                    except sr.UnknownValueError:
                        pass  # No speech detected
                    except sr.RequestError as e:
                        print(f"Could not request results; {e}")
                
                # Clean up
                os.unlink(filename)
            except Exception as e:
                print(f"Error processing audio: {e}")
        
        self.processing_audio[guild_id] = False
        
        # Continue listening
        if guild_id in self.voice_clients and self.voice_clients[guild_id].is_connected():
            self.voice_clients[guild_id].start_recording(
                discord.sinks.WaveSink(),
                self.recording_finished,
                guild_id
            )
    
    async def handle_voice_command(self, guild_id, user_id, command):
        """Process a voice command from a user"""
        if not self.get_ai_response:
            await self.speak_message(guild_id, "Sorry, I can't process AI responses right now.")
            return
        
        # Get the guild and channel
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        
        # Find a suitable text channel to send response
        text_channel = None
        for channel in guild.text_channels:
            # Try to find the channel where the listen command was issued
            # or fallback to the first text channel with bot permissions
            perms = channel.permissions_for(guild.me)
            if perms.send_messages:
                text_channel = channel
                break
        
        if not text_channel:
            await self.speak_message(guild_id, "I can't find a text channel to respond in.")
            return
        
        # Get the member
        member = guild.get_member(int(user_id))
        if not member:
            return
        
        # Create conversation context for AI
        conversation = [
            {"is_user": True, "content": command}
        ]
        
        # Get AI response
        response = await self.get_ai_response(conversation)
        
        # Send to text channel
        await text_channel.send(f"🎤 **Voice from {member.display_name}:** {command}")
        await text_channel.send(f"🤖 **AI Response:** {response}")
        
        # Speak the response
        await self.speak_message(guild_id, response)
    
    async def speak_message(self, guild_id, message):
        """Use TTS to speak a message in the voice channel"""
        if guild_id not in self.voice_clients or not self.voice_clients[guild_id].is_connected():
            return
        
        # Add to the queue
        self.tts_queue[guild_id].append(message)
        
        # Process the queue if we're not already speaking
        if not self.voice_clients[guild_id].is_playing():
            await self.process_tts_queue(guild_id)
    
    async def process_tts_queue(self, guild_id):
        """Process messages in the TTS queue"""
        if guild_id not in self.tts_queue or not self.tts_queue[guild_id]:
            return
        
        # Get the next message
        message = self.tts_queue[guild_id].pop(0)
        
        # Generate TTS audio file
        try:
            # Detect language (simplified version)
            language = "en"
            tagalog_words = ["ako", "ikaw", "siya", "kami", "tayo", "kayo", "sila", "na", "at", "ang", "mga"]
            if any(word in message.lower() for word in tagalog_words):
                language = "fil"
            
            # Choose voice based on language
            voice = self.default_voice
            if language == "fil":
                voice = "fil-PH-BlessicaNeural"  # Filipino female voice
            
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                filename = f.name
            
            # Generate TTS audio
            tts = edge_tts.Communicate(text=message, voice=voice, rate="+10%", volume="+30%")
            await tts.save(filename)
            
            # Play the TTS message
            audio_source = discord.FFmpegPCMAudio(filename)
            self.voice_clients[guild_id].play(
                audio_source, 
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    self.after_speaking(e, guild_id, filename), 
                    self.bot.loop
                )
            )
        except Exception as e:
            print(f"Error generating TTS: {e}")
            
            # Process next message if any
            if self.tts_queue[guild_id]:
                await self.process_tts_queue(guild_id)
    
    async def after_speaking(self, error, guild_id, filename):
        """Called after a TTS message has finished playing"""
        # Clean up file
        try:
            os.unlink(filename)
        except:
            pass
        
        # Process next message if any
        if guild_id in self.tts_queue and self.tts_queue[guild_id]:
            await self.process_tts_queue(guild_id)

def setup(bot):
    """Add the cog to the bot"""
    bot.add_cog(SpeechRecognitionCog(bot))
    print("✅ Speech Recognition Cog loaded")