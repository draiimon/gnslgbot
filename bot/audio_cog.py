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
        
        # Get channel object
        channel = ctx.author.voice.channel
        if not channel:
            return await ctx.send("**GAGO, DI KO MAHANAP VOICE CHANNEL MO!**")
        
        # Simple processing message
        processing_msg = await ctx.send("**SANDALI LANG!** Hinahanap ko yung last audio...")
        
        try:
            # Get latest audio from database
            latest_audio = get_latest_audio_tts()
            
            if not latest_audio or not latest_audio[1]:
                await processing_msg.delete()
                return await ctx.send("**WALA PA AKONG NAGSASALITA!** Wala pang audio sa database!")
            
            audio_id = latest_audio[0]
            audio_data = latest_audio[1]
            
            # Save to unique file for this replay
            replay_filename = f"temp_audio/replay_{ctx.message.id}.mp3"
            with open(replay_filename, "wb") as f:
                f.write(audio_data)
            
            # Verify file exists and has content
            if not os.path.exists(replay_filename) or os.path.getsize(replay_filename) == 0:
                raise Exception("Failed to create audio file from database")
            
            # Create discord.py audio source
            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(replay_filename)
            )
            source.volume = 1.0  # Standard volume
            
            # Join the voice channel with minimal code
            if ctx.voice_client:
                # If already in a voice channel
                if ctx.voice_client.channel != channel:
                    await ctx.voice_client.disconnect()
                    await asyncio.sleep(0.5)
                    voice = await channel.connect()
                else:
                    voice = ctx.voice_client
            else:
                # Not in any voice channel
                voice = await channel.connect()
            
            # Make sure we're not already playing
            if voice.is_playing():
                voice.stop()
            
            # Delete processing message
            await processing_msg.delete()
            
            # Play with simple callback to clean up file
            def after_playback(error):
                if error:
                    print(f"Replay error: {error}")
                # Try to clean up the file
                try:
                    if os.path.exists(replay_filename):
                        os.remove(replay_filename)
                except Exception as e:
                    print(f"Error cleaning up replay file: {e}")
            
            # Play the audio
            voice.play(source, after=after_playback)
            
            # Send confirmation message
            await ctx.send(f"🔊 **REPLAY:** Audio ID: {audio_id}", delete_after=10)
            
        except Exception as e:
            print(f"⚠️ REPLAY ERROR: {e}")
            
            # Clean up processing message
            try:
                await processing_msg.delete()
            except:
                pass
            
            # Make sure to clean up voice
            try:
                if ctx.voice_client:
                    await ctx.voice_client.disconnect()
            except:
                pass
            
            # Simple error message
            await ctx.send(f"**ERROR:** {str(e)}", delete_after=10)
    
    @commands.command(name="vc")
    async def vc(self, ctx, *, message: str):
        """Final attempt at text-to-speech with super basic approach"""
        # Check if the user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Only check for voice channel validity
        channel = ctx.author.voice.channel
        if not channel:
            return await ctx.send("**GAGO, DI KO MAHANAP VOICE CHANNEL MO!**")
        
        try:
            # Just generate TTS with most basic approach
            tts = gTTS(text=message, lang='tl', slow=False)
            
            # Save with a unique name in the temp directory
            filename = f"temp_audio/speech_{ctx.message.id}.mp3"
            tts.save(filename)
            
            # Verify the file was created
            if not os.path.exists(filename):
                raise Exception("Failed to create audio file")
            
            # Store this audio in the database for backup
            with open(filename, "rb") as file:
                audio_data = file.read()
                audio_id = store_audio_tts(ctx.author.id, message, audio_data)
            
            try:
                # Join the voice channel only if we're not already in it
                # Handle the voice client with absolute minimum code
                if ctx.voice_client:
                    # If already in a voice channel
                    if ctx.voice_client.channel != channel:
                        await ctx.voice_client.disconnect()
                        await asyncio.sleep(0.5)
                        voice = await channel.connect()
                    else:
                        voice = ctx.voice_client
                else:
                    # Not in any voice channel
                    voice = await channel.connect()
                
                # Create discord.py audio source - create this AFTER successful voice connection
                source = discord.PCMVolumeTransformer(
                    discord.FFmpegPCMAudio(source=filename)
                )
                source.volume = 1.0  # Standard volume
                
                # Make sure we're not already playing
                if voice.is_playing():
                    voice.stop()
                
                # Super simple playback with minimal settings and basic error handler
                def play_callback(error):
                    if error:
                        print(f'Player error: {error}')
                    # Clean up the file after playing
                    try:
                        os.remove(filename)
                    except:
                        pass
                
                voice.play(source, after=play_callback)
            except Exception as voice_error:
                print(f"Voice connection error: {voice_error}")
                raise Exception(f"Voice error: {voice_error}")
            
            # Send success message
            await ctx.send(f"🔊 **SPEAKING:** {message}", delete_after=10)
            
        except Exception as e:
            # Clean error handling
            print(f"⚠️ TTS ERROR: {e}")
            
            # Make sure to try to clean up
            try:
                if ctx.voice_client:
                    await ctx.voice_client.disconnect()
            except:
                pass
            
            # Simple error message to user
            await ctx.send(f"**ERROR:** {str(e)}", delete_after=10)

def setup(bot):
    """Add cog to bot"""
    bot.add_cog(AudioCog(bot))