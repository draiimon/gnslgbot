import asyncio
import discord
import os
import io
import time
import json
import threading
import subprocess
import speech_recognition as sr
from discord.ext import commands
import edge_tts
from pydub import AudioSegment

class SpeechRecognitionCog(commands.Cog):
    """Cog for handling speech recognition and voice interactions"""
    
    def __init__(self, bot):
        self.bot = bot
        self.listening_guilds = set()  # Set of guild IDs that are listening
        self.recognizer = sr.Recognizer()
        self.voice_clients = {}  # guild_id: voice_client
        self.tts_queue = {}  # guild_id: list of messages to speak
        self.listening_tasks = {}  # guild_id: asyncio task
        self.temp_dir = "temp_audio"
        
        # Make sure temp directory exists
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Default voice settings
        self.default_voice = "en-US-GuyNeural"
        self.user_voice_prefs = {}  # user_id: "male" or "female"
        
        # Get Groq client from the bot (assuming it's stored there)
        self.get_ai_response = None  # This will be set when the cog is loaded
        
        print("✅ Speech Recognition Cog initialized with voice command support")
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Called when the cog is ready"""
        # Try to get the get_ai_response method from ChatCog
        print("🔍 Looking for AI response handler in cogs...")
        for cog_name, cog in self.bot.cogs.items():
            print(f"  - Checking cog: {cog_name}, type: {type(cog).__name__}")
            if hasattr(cog, 'get_ai_response'):
                self.get_ai_response = cog.get_ai_response
                print(f"✅ Found AI response handler in {cog_name}")
                break
        
        if not self.get_ai_response:
            print("❌ Could not find AI response handler - AI responses won't work!")
    
    @commands.command()
    async def listen(self, ctx, *, question: str = None):
        """Start listening for voice commands in your current voice channel or ask a direct question"""
        if not ctx.author.voice:
            await ctx.send("**TANGA KA!** You need to be in a voice channel first!")
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
        self.listening_guilds.add(ctx.guild.id)
        if ctx.guild.id not in self.tts_queue:
            self.tts_queue[ctx.guild.id] = []
        
        # DIRECT QUESTION MODE - Process the question immediately if provided with the command
        if question:
            # Process the question directly
            await self.handle_voice_command(ctx.guild.id, ctx.author.id, question)
            return
        
        # LISTENING MODE - If no question was provided, start listening mode
        # Inform user
        await ctx.send(f"🎤 **GAME NA!** I'm now in **{voice_channel.name}**! Just type your message and I'll respond!")
        
        # Start listening for audio (in a separate task)
        if ctx.guild.id in self.listening_tasks and not self.listening_tasks[ctx.guild.id].done():
            self.listening_tasks[ctx.guild.id].cancel()
        
        # Create a new listening task for this guild
        self.listening_tasks[ctx.guild.id] = asyncio.create_task(self.start_listening_for_speech(ctx))
        
        # Speak a welcome message
        await self.speak_message(ctx.guild.id, "Ginslog Bot is now listening! Just type your message in chat and I'll respond!")
    
    async def start_listening_for_speech(self, ctx):
        """Listen for voice commands using a Discord-compatible approach"""
        guild_id = ctx.guild.id
        
        # Set up the voice channel
        voice_channel = ctx.author.voice.channel if ctx.author.voice else None
        if not voice_channel:
            return
            
        # Log that we're starting to listen
        print(f"🎧 Starting voice listening in {voice_channel.name} for guild {guild_id}")
        
        # Inform channel we're ready for voice commands - SIMPLIFIED MODE
        await ctx.send("🎤 **GINSLOG BOT IS READY!** Just type your messages in this channel and I'll respond!")
        
        # In listening mode, just keep the task alive to maintain the connection
        while guild_id in self.listening_guilds:
            try:
                # Just keep the task alive and monitor the voice channel
                await asyncio.sleep(60)
            except Exception as e:
                print(f"⚠️ Error in listening task: {e}")
                await asyncio.sleep(10)
        
        print(f"🛑 Stopped listening in guild {guild_id}")
    
    @commands.command()
    async def stoplisten(self, ctx):
        """Stop listening for voice commands"""
        if ctx.guild.id in self.listening_guilds:
            # Clean up resources
            self.listening_guilds.discard(ctx.guild.id)
            
            # Cancel the listening task
            if ctx.guild.id in self.listening_tasks:
                try:
                    self.listening_tasks[ctx.guild.id].cancel()
                    print(f"🛑 Cancelled listening task for guild {ctx.guild.id}")
                except:
                    pass
            
            # Disconnect from voice
            if ctx.guild.id in self.voice_clients:
                await self.voice_clients[ctx.guild.id].disconnect()
                del self.voice_clients[ctx.guild.id]
            
            await ctx.send("🛑 **OKS LANG!** I've stopped listening for voice commands.")
        else:
            await ctx.send("**LOKO KA BA?** I wasn't listening in any channel.")
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for special speech recognition commands"""
        # Skip messages from bots or non-guild messages
        if message.author.bot or not message.guild:
            return
            
        # Check if we're actively listening in this guild
        if message.guild.id not in self.listening_guilds:
            return
        
        # SIMPLIFIED APPROACH - Direct processing of any message in channels where listening is active
        # This makes it much easier for users to interact
        
        # Option 1: If user is using old format with !listen transcript, still support it
        if message.content.startswith("!listen transcript "):
            # Extract the simulated transcript
            transcript = message.content[18:].strip()
            
            # Handle it like a voice command
            if "ginslog bot" in transcript.lower():
                # Extract the command (remove bot name)
                command = transcript.lower().replace("ginslog bot", "").strip()
                if command:
                    await self.handle_voice_command(message.guild.id, message.author.id, command)
                    
        # Option 2: SIMPLIFIED - Just process any normal message as a voice command directly
        # This makes it much easier for users since they can just type normally
        else:
            # Treat any message as a voice command when in listening mode
            command = message.content.strip()
            if command and not command.startswith(self.bot.command_prefix):  # Skip actual bot commands
                await self.handle_voice_command(message.guild.id, message.author.id, command)
    
    async def handle_voice_command(self, guild_id, user_id, command):
        """Process a voice command from a user"""
        print(f"🗣️ Processing voice command from user {user_id}: '{command}'")
        
        # First, check if we have the AI response handler
        if not self.get_ai_response:
            print("❌ ERROR: No AI response handler available!")
            await self.speak_message(guild_id, "Sorry, I can't process AI responses right now. The AI handler is not connected properly.")
            return
        else:
            print("✅ AI response handler is available")
        
        # Get the guild and channel
        guild = self.bot.get_guild(guild_id)
        if not guild:
            print(f"❌ ERROR: Could not find guild with ID {guild_id}")
            return
        
        # Find a suitable text channel to send response
        text_channel = None
        for channel in guild.text_channels:
            # Try to find a suitable channel with bot permissions
            perms = channel.permissions_for(guild.me)
            if perms.send_messages:
                text_channel = channel
                break
        
        if not text_channel:
            print("❌ ERROR: Could not find a suitable text channel to respond in")
            await self.speak_message(guild_id, "I can't find a text channel to respond in.")
            return
        
        # Get the member
        member = guild.get_member(int(user_id))
        if not member:
            print(f"❌ ERROR: Could not find member with ID {user_id}")
            return
        
        # Send acknowledgment message
        await text_channel.send(f"🎤 **Voice command from {member.display_name}:** {command}")
        await text_channel.send("🔄 Generating AI response...")
        
        # Start processing indicator
        processing_message = await self.speak_message(guild_id, "Thinking about your question...")
        
        # Create conversation context for AI
        conversation = [
            {"is_user": True, "content": command}
        ]
        
        # Get AI response
        try:
            print(f"🧠 Generating AI response for command: '{command}'")
            response = await self.get_ai_response(conversation)
            print(f"✅ AI response generated: '{response[:50]}...'")
            
            # Send response to text channel
            await text_channel.send(f"🤖 **AI Response:** {response}")
            
            # Speak the response
            await self.speak_message(guild_id, response)
        except Exception as e:
            error_message = f"Error generating response: {str(e)}"
            print(f"❌ AI ERROR: {error_message}")
            import traceback
            traceback.print_exc()
            await text_channel.send(f"❌ **ERROR:** {error_message}")
            await self.speak_message(guild_id, "Sorry, I encountered an error processing your request.")
    
    async def speak_message(self, guild_id, message):
        """Use TTS to speak a message in the voice channel using in-memory processing"""
        if guild_id not in self.voice_clients or not self.voice_clients[guild_id].is_connected():
            return
        
        # Add to the queue
        self.tts_queue[guild_id].append(message)
        
        # Process the queue if we're not already speaking
        if not self.voice_clients[guild_id].is_playing():
            await self.process_tts_queue(guild_id)
            
        return message  # Return for callback tracking
    
    async def process_tts_queue(self, guild_id):
        """Process messages in the TTS queue using in-memory approach"""
        if guild_id not in self.tts_queue or not self.tts_queue[guild_id]:
            return
        
        # Get the next message
        message = self.tts_queue[guild_id].pop(0)
        
        # Generate TTS audio directly in memory
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
            
            # Generate TTS audio in memory
            tts = edge_tts.Communicate(text=message, voice=voice, rate="+10%", volume="+30%")
            
            # Create buffer to hold audio data
            audio_buffer = io.BytesIO()
            
            # Stream audio data directly to memory
            async for audio_chunk in tts.stream():
                if audio_chunk["type"] == "audio":
                    audio_buffer.write(audio_chunk["data"])
                    
            # Reset buffer position for reading
            audio_buffer.seek(0)
            
            # Create a pydub AudioSegment from the buffer
            audio_segment = AudioSegment.from_file(audio_buffer, format="mp3")
            
            # Convert to WAV format with Discord-compatible settings
            audio_segment = audio_segment.set_frame_rate(48000).set_channels(2)
            
            # Export to a new buffer as WAV
            output_buffer = io.BytesIO()
            audio_segment.export(output_buffer, format="wav")
            output_buffer.seek(0)
            
            # Create custom audio source
            source = discord.PCMAudio(output_buffer)
            
            # Play the TTS message
            self.voice_clients[guild_id].play(
                source,
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    self.after_speaking(e, guild_id, None), 
                    self.bot.loop
                )
            )
            
            print(f"✅ Speaking message: {message[:50]}...")
            
        except Exception as e:
            print(f"⚠️ Error generating TTS: {e}")
            import traceback
            traceback.print_exc()
            
            # Process next message if any
            if self.tts_queue[guild_id]:
                await self.process_tts_queue(guild_id)
    
    async def after_speaking(self, error, guild_id, _):
        """Called after a TTS message has finished playing"""
        if error:
            print(f"⚠️ Error in TTS playback: {error}")
        
        # Process next message if any
        if guild_id in self.tts_queue and self.tts_queue[guild_id]:
            await self.process_tts_queue(guild_id)

def setup(bot):
    """Add the cog to the bot"""
    bot.add_cog(SpeechRecognitionCog(bot))
    print("✅ Speech Recognition Cog loaded")