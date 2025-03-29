import discord
from discord.ext import commands
from gtts import gTTS
import io
import os
import asyncio
import time
import random
import wavelink
from typing import Optional, Union
from wavelink.ext import spotify
import datetime
import re
from .config import Config
from .database import (
    add_rate_limit_entry, 
    is_rate_limited, 
    store_audio_tts, 
    get_latest_audio_tts, 
    get_audio_tts_by_id,
    cleanup_old_audio_tts
)

class MusicPlayer(wavelink.Player):
    """Custom player class with queue functionality"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue = asyncio.Queue()
        self.now_playing = None
        self.is_playing = False
        self.loop = False
        
    async def play_next(self):
        """Play the next track in queue"""
        if self.loop and self.now_playing:
            await self.play(self.now_playing)
            return

        # Check if queue is empty
        if self.queue.empty():
            self.now_playing = None
            return
        
        # Get next track and play it
        track = await self.queue.get()
        self.now_playing = track
        
        # Play using wavelink
        await self.play(track)
    
    async def add_tracks(self, ctx, tracks):
        """Add tracks to the queue with user feedback"""
        if not tracks:
            await ctx.send("**WALA AKONG NAKITANG KANTA!** Try mo nga ulit.", delete_after=15)
            return
        
        # Single track received
        if isinstance(tracks, wavelink.Track):
            await self.queue.put(tracks)
            await ctx.send(f"**ADDED TO QUEUE:** {tracks.title}", delete_after=15)
            
        # Multiple tracks - could be playlist
        elif hasattr(tracks, '__iter__'):
            if len(tracks) == 1:
                track = tracks[0]
                await self.queue.put(track)
                await ctx.send(f"**ADDED TO QUEUE:** {track.title}", delete_after=15)
            else:
                # Handling a playlist
                await ctx.send(f"**ADDED PLAYLIST:** {len(tracks)} tracks", delete_after=15)
                for track in tracks:
                    await self.queue.put(track)
        
        # Start playing if not already playing
        if not self.is_playing:
            await self.play_next()
            
class AudioCog(commands.Cog):
    """Cog for handling voice channel interactions and TTS using Wavelink/Lavalink"""

    def __init__(self, bot):
        self.bot = bot
        self.temp_dir = "temp_audio"
        # Create temp directory if it doesn't exist
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
        
        # Track nodes and players
        self.wavelink_connected = False
        self.node = None
        self.players = {}

    async def cog_load(self):
        """Initialize wavelink and connect to nodes"""
        print("Initializing Wavelink...")
        
        # Setup Wavelink nodes
        try:
            # Get local Lavalink node
            self.node = wavelink.Node(
                uri='http://localhost:2333',
                password='youshallnotpass'
            )
            await wavelink.NodePool.connect(client=self.bot, nodes=[self.node])
            self.wavelink_connected = True
            print("✅ Connected to Lavalink node!")
            
            # Setup track end event handling
            self.bot.add_listener(self.on_wavelink_track_end, "on_wavelink_track_end")
            
        except Exception as e:
            print(f"❌ ERROR: Could not connect to Lavalink node: {e}")
            self.wavelink_connected = False
        
        print("✅ Audio Cog loaded")
        
    async def on_wavelink_track_end(self, player: wavelink.Player, track: wavelink.Track, reason):
        """Called when a track finishes playing"""
        # Handle only our MusicPlayer instances
        if not isinstance(player, MusicPlayer):
            return
            
        player.is_playing = False
        
        # Play next track in queue if there is one
        if not player.queue.empty():
            await player.play_next()
        else:
            player.now_playing = None

    async def cog_unload(self):
        """Clean up when cog is unloaded"""
        # Disconnect all players gracefully
        for player in wavelink.NodePool.get_node().players.values():
            try:
                await player.disconnect()
            except:
                pass

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
                    player = wavelink.NodePool.get_node().get_player(member.guild.id)
                    if player.is_connected():
                        return  # Already connected
                except:
                    # Not connected, so we can join
                    try:
                        channel = after.channel
                        await channel.connect(cls=wavelink.Player)
                        print(f"Auto-joined voice channel: {after.channel.name}")
                    except Exception as e:
                        print(f"Error auto-joining channel: {e}")

    @commands.command(name="joinvc")
    async def joinvc(self, ctx):
        """Join a voice channel using Wavelink"""
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Get the user's channel
        channel = ctx.author.voice.channel
        
        try:
            # Check if already in a voice channel
            try:
                player = wavelink.NodePool.get_node().get_player(ctx.guild.id)
                if player and player.channel == channel:
                    return await ctx.send("**BOBO!** NASA VOICE CHANNEL MO NA AKO!")
                elif player:
                    await player.disconnect()
            except:
                pass
                
            # Connect to the user's channel
            player = await channel.connect(cls=wavelink.Player)
            await ctx.send(f"**SIGE!** PAPASOK NA KO SA {channel.name}!")
            
        except Exception as e:
            await ctx.send(f"**ERROR:** {str(e)}")
            print(f"Error joining voice channel: {e}")
    
    @commands.command(name="leavevc")
    async def leavevc(self, ctx):
        """Leave the voice channel"""
        try:
            player = wavelink.NodePool.get_node().get_player(ctx.guild.id)
            if not player or not player.is_connected():
                return await ctx.send("**TANGA!** WALA AKO SA VOICE CHANNEL!")
            
            await player.disconnect()
            await ctx.send("**AYOS!** UMALIS NA KO!")
            
        except Exception as e:
            await ctx.send(f"**ERROR:** {str(e)}")
            print(f"Error leaving voice channel: {e}")
    
    @commands.command(name="vc")
    async def vc(self, ctx, *, message: str):
        """Text-to-speech using Wavelink/Lavalink"""
        # Check if user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Check if wavelink is working
        if not self.wavelink_connected:
            return await ctx.send("**ERROR:** Wavelink/Lavalink is not connected!")
        
        # Check rate limiting
        if is_rate_limited(ctx.author.id):
            return await ctx.send(f"**TEKA LANG {ctx.author.mention}!** Ang bilis mo mag-type! Hinay-hinay lang!")
        
        add_rate_limit_entry(ctx.author.id)
        
        # Send processing message
        processing_msg = await ctx.send("**SANDALI LANG!** Ginagawa ko pa yung audio...")
        
        try:
            # Generate TTS
            tts = gTTS(text=message, lang='tl', slow=False)
            
            # Create a unique filename for this TTS request
            filename = f"temp_audio/tts_{ctx.message.id}.mp3"
            
            # Save to file
            tts.save(filename)
            
            # Verify file exists
            if not os.path.exists(filename) or os.path.getsize(filename) == 0:
                raise Exception("Failed to generate audio file")
            
            # Store in database
            with open(filename, "rb") as f:
                audio_data = f.read()
                audio_id = store_audio_tts(ctx.author.id, message, audio_data)
            
            # Get or create the player
            try:
                player = wavelink.NodePool.get_node().get_player(ctx.guild.id)
                if not player or not player.is_connected():
                    player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
            except Exception as connect_error:
                raise Exception(f"Voice connection error: {connect_error}")
            
            # Create a playable track from local file
            track = await wavelink.LocalTrack.search(filename)
            
            # Play the track
            await player.play(track)
            
            # Delete the processing message
            await processing_msg.delete()
            
            # Send success message
            await ctx.send(f"🔊 **SPEAKING:** {message}", delete_after=10)
            
            # Clean up the file after playing
            try:
                os.remove(filename)
            except Exception as e:
                print(f"Error removing file: {e}")
            
            # Clean up old database entries
            cleanup_old_audio_tts(keep_count=20)
            
        except Exception as e:
            print(f"⚠️ TTS ERROR: {e}")
            
            # Try to delete processing message
            try:
                await processing_msg.delete()
            except:
                pass
            
            # Send error message
            await ctx.send(f"**ERROR:** {str(e)}", delete_after=10)
    
    @commands.command(name="replay")
    async def replay(self, ctx):
        """Replay last TTS message from database using Wavelink"""
        # Check if user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Check if wavelink is working
        if not self.wavelink_connected:
            return await ctx.send("**ERROR:** Wavelink/Lavalink is not connected!")
        
        # Send processing message
        processing_msg = await ctx.send("**SANDALI LANG!** Hinahanap ko yung audio...")
        
        try:
            # Get latest audio from database
            latest_audio = get_latest_audio_tts()
            
            if not latest_audio or not latest_audio[1]:
                await processing_msg.delete()
                return await ctx.send("**WALA PA AKONG NASABI!** Wala pang audio sa database!")
            
            audio_id = latest_audio[0]
            audio_data = latest_audio[1]
            
            # Save to temporary file
            filename = f"temp_audio/replay_{ctx.message.id}.mp3"
            with open(filename, "wb") as f:
                f.write(audio_data)
            
            # Get or create the player
            try:
                player = wavelink.NodePool.get_node().get_player(ctx.guild.id)
                if not player or not player.is_connected():
                    player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
            except Exception as connect_error:
                raise Exception(f"Voice connection error: {connect_error}")
            
            # Create a playable track from local file
            track = await wavelink.LocalTrack.search(filename)
            
            # Play the track
            await player.play(track)
            
            # Delete the processing message
            await processing_msg.delete()
            
            # Send success message
            await ctx.send(f"🔊 **REPLAY:** Audio ID: {audio_id}", delete_after=10)
            
            # Clean up the file after playing
            try:
                os.remove(filename)
            except Exception as e:
                print(f"Error removing file: {e}")
            
        except Exception as e:
            print(f"⚠️ REPLAY ERROR: {e}")
            
            # Try to delete processing message
            try:
                await processing_msg.delete()
            except:
                pass
            
            # Send error message
            await ctx.send(f"**ERROR:** {str(e)}", delete_after=10)

def setup(bot):
    """Add cog to bot"""
    bot.add_cog(AudioCog(bot))