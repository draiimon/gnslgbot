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
        """Text-to-speech in voice channel using direct FFmpeg with improved stability"""
        # Check if the user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Check rate limiting
        if is_rate_limited(ctx.author.id, limit=Config.RATE_LIMIT_MESSAGES, period_seconds=Config.RATE_LIMIT_PERIOD):
            return await ctx.send(f"**Huy {ctx.author.mention}!** Ang bilis mo naman magtype! Sandali lang muna, naglo-load pa ako!")
        
        # Add to rate limit
        add_rate_limit_entry(ctx.author.id)
        
        # Generate unique filename
        unique_id = f"{ctx.author.id}_{int(time.time())}"
        temp_mp3 = f"{self.temp_dir}/tts_{unique_id}.mp3"
        temp_wav = f"{self.temp_dir}/tts_{unique_id}.wav"
        
        # Processing message
        processing_msg = None
        
        try:
            # Send processing message
            processing_msg = await ctx.send("**ANTAY KA MUNA!** Ginagawa ko pa yung audio...")
            
            # Clean up old files (keep only latest 5)
            try:
                files = sorted([f for f in os.listdir(self.temp_dir) if f.startswith("tts_")], 
                             key=lambda x: os.path.getmtime(os.path.join(self.temp_dir, x)))
                if len(files) > 5:
                    for old_file in files[:-5]:
                        try:
                            os.remove(os.path.join(self.temp_dir, old_file))
                            print(f"Cleaned up old file: {old_file}")
                        except Exception as e:
                            print(f"Failed to clean up file {old_file}: {e}")
            except Exception as e:
                print(f"Error during file cleanup: {e}")
            
            # Determine language (default Tagalog, switch to English if needed)
            import re
            words = re.findall(r'\w+', message.lower())
            tagalog_words = ['ang', 'mga', 'na', 'ng', 'sa', 'ko', 'mo', 'siya', 'naman', 'po', 'tayo', 'kami']
            tagalog_count = sum(1 for word in words if word in tagalog_words)
            
            # Use English if message appears to be mostly English
            lang = 'tl'  # Default to Tagalog
            if len(words) > 3 and tagalog_count < 2:
                lang = 'en'
            
            # Generate TTS file (directly to memory to avoid file issues)
            tts = gTTS(text=message, lang=lang, slow=False)
            mp3_fp = io.BytesIO()
            tts.write_to_fp(mp3_fp)
            mp3_fp.seek(0)
            
            # Convert MP3 to WAV using pydub (avoids FFmpeg process issues)
            sound = AudioSegment.from_mp3(mp3_fp)
            sound.export(temp_wav, format="wav")
            
            # Verify file exists
            if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) == 0:
                raise Exception("Failed to generate audio file")
            
            # Delete processing message with error handling for message already deleted
            if processing_msg:
                try:
                    await processing_msg.delete()
                except discord.errors.NotFound:
                    # Message was already deleted or doesn't exist, continue anyway
                    print("Processing message already deleted, continuing")
                except Exception as e:
                    print(f"Error deleting processing message: {e}")
                
            # Connect to voice channel
            try:
                voice_client = ctx.voice_client
                
                # Stop any currently playing audio
                if voice_client and voice_client.is_playing():
                    voice_client.stop()
                    await asyncio.sleep(0.2)  # Brief pause
                
                # Connect to voice channel if not already connected
                if not voice_client:
                    voice_client = await ctx.author.voice.channel.connect()
                elif voice_client.channel != ctx.author.voice.channel:
                    # Move to user's channel if needed
                    await voice_client.disconnect()
                    voice_client = await ctx.author.voice.channel.connect()
                
                # Create standard discord.py FFmpeg PCM audio source
                audio_source = discord.PCMVolumeTransformer(
                    discord.FFmpegPCMAudio(source=temp_wav),
                    volume=0.8
                )
                
                # Play the audio using standard discord.py
                voice_client.play(audio_source, after=lambda e: print(f'Player error: {e}' if e else 'File finished playing'))
                
                # Send confirmation message
                await ctx.send(f"🔊 **SINABI KO NA:** {message}", delete_after=10)
                
                # Schedule file deletion after playing
                def delete_after_play():
                    try:
                        if os.path.exists(temp_wav):
                            os.remove(temp_wav)
                            print(f"Deleted temp WAV file: {temp_wav}")
                    except Exception as e:
                        print(f"Error deleting temp file: {e}")
                
                # Schedule file deletion after the track length
                self.bot.loop.call_later(30, delete_after_play)
                
            except Exception as e:
                print(f"Voice client error: {e}")
                raise e
            
        except Exception as e:
            error_msg = str(e)
            print(f"TTS ERROR: {error_msg}")
            
            # Clean up processing message with proper error handling
            if processing_msg:
                try:
                    await processing_msg.delete()
                except discord.errors.NotFound:
                    # Message was already deleted or doesn't exist, continue anyway
                    print("Processing message already deleted in error handler, continuing")
                except Exception as e:
                    print(f"Error deleting processing message in error handler: {e}")
            
            # Clean up temp files
            try:
                if os.path.exists(temp_wav):
                    os.remove(temp_wav)
                if os.path.exists(temp_mp3):
                    os.remove(temp_mp3)
            except:
                pass
            
            # Send appropriate error message
            if "not found" in error_msg.lower() or "ffmpeg" in error_msg.lower():
                await ctx.send("**ERROR:** Hindi ma-generate ang audio file. Problem sa audio conversion.", delete_after=15)
            elif "lang" in error_msg.lower():
                await ctx.send("**ERROR:** Hindi supported ang language. Try mo mag-English.", delete_after=15)
            else:
                await ctx.send(f"**PUTANGINA MAY ERROR:** {error_msg}", delete_after=15)

def setup(bot):
    """Add cog to bot"""
    bot.add_cog(AudioCog(bot))