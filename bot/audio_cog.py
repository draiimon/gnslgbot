import discord
from discord.ext import commands
from gtts import gTTS
import io
import os
import asyncio
import time
import random
import wavelink
from wavelink.tracks import Playable, YouTubeTrack
from wavelink.ext import spotify
from typing import Optional, Union
import datetime
import re
import math
from urllib.parse import urlparse
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
        self.now_playing = None
        self.is_playing = False
        self.loop = False
        
    async def do_next(self):
        """Play the next track in queue"""
        if self.loop and self.now_playing:
            await self.play(self.now_playing)
            return

        # Check if queue is empty
        if self.queue.is_empty:
            self.now_playing = None
            return
        
        # Get next track and play it
        track = self.queue.get()
        self.now_playing = track
        
        # Play using wavelink
        await self.play(track)
    
    async def add_tracks(self, ctx, tracks):
        """Add tracks to the queue with user feedback"""
        if not tracks:
            await ctx.send("**WALA AKONG NAKITANG KANTA!** Try mo nga ulit.", delete_after=15)
            return
        
        # Single track received
        if isinstance(tracks, wavelink.tracks.YouTubeTrack):
            self.queue.put(tracks)
            await ctx.send(f"**ADDED TO QUEUE:** {tracks.title}", delete_after=15)
            
        # Playlist received
        elif isinstance(tracks, wavelink.tracks.YouTubePlaylist):
            # Handle a playlist
            await ctx.send(f"**ADDED PLAYLIST:** {len(tracks.tracks)} tracks from '{tracks.name}'", delete_after=15)
            for track in tracks.tracks:
                self.queue.put(track)
                
        # List of tracks
        elif isinstance(tracks, list):
            if len(tracks) == 1:
                track = tracks[0]
                self.queue.put(track)
                await ctx.send(f"**ADDED TO QUEUE:** {track.title}", delete_after=15)
            else:
                # Handling a list of tracks
                await ctx.send(f"**ADDED TO QUEUE:** {len(tracks)} tracks", delete_after=15)
                for track in tracks:
                    self.queue.put(track)
        
        # Start playing if not already playing
        if not self.is_playing:
            await self.do_next()
            
class AudioCog(commands.Cog):
    """Cog for handling voice channel interactions and TTS using Wavelink/Lavalink"""

    def __init__(self, bot):
        self.bot = bot
        self.temp_dir = "temp_audio"
        # Create temp directory if it doesn't exist
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
        
        # Track nodes
        self.wavelink_connected = False
        self.node = None
        self.players = {}

    async def cog_load(self):
        """Initialize wavelink and connect to nodes"""
        print("Initializing Wavelink...")
        
        # Setup Wavelink nodes
        try:
            # Create our node - using Wavelink 2.6.3 API
            self.node = wavelink.Node(
                uri='http://localhost:2333',
                password='youshallnotpass',
                id="main-node",
                secure=False
            )
            
            # Connect to our node with wavelink 2.6.3 API
            await wavelink.NodePool.connect(client=self.bot, nodes=[self.node])
            self.wavelink_connected = True
            print("✅ Connected to Lavalink node!")
            
            # Setup track end event handling
            self.bot.add_listener(self.on_wavelink_track_end, "on_wavelink_track_end")
            
        except Exception as e:
            print(f"❌ ERROR: Could not connect to Lavalink node: {e}")
            self.wavelink_connected = False
        
        print("✅ Audio Cog loaded")
        
    async def on_wavelink_track_end(self, player: wavelink.Player, track: Playable, reason):
        """Called when a track finishes playing"""
        # Handle only our MusicPlayer instances
        if not isinstance(player, MusicPlayer):
            return
            
        player.is_playing = False
        
        # Play next track in queue if there is one
        if not player.queue.is_empty:
            await player.do_next()
        else:
            player.now_playing = None

    async def cog_unload(self):
        """Clean up when cog is unloaded"""
        # Disconnect all players gracefully
        try:
            for guild_id, player in wavelink.NodePool.get_node().players.items():
                try:
                    await player.disconnect()
                except:
                    pass
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
                    player = after.channel.guild.voice_client
                    if player and player.channel:
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
        print(f"Attempting to join channel: {channel.name} (ID: {channel.id})")
        
        try:
            # Check if wavelink is working
            if not self.wavelink_connected:
                return await ctx.send("**ERROR:** Wavelink/Lavalink is not connected! Please try again later.")
                
            # Check if already in a voice channel
            player = ctx.guild.voice_client
            if player and player.channel and player.channel.id == channel.id:
                return await ctx.send("**BOBO!** NASA VOICE CHANNEL MO NA AKO!")
            elif player:
                print(f"Already connected to a different channel, disconnecting from {player.channel.name}")
                await player.disconnect()
            
            print("Creating new wavelink player...")
            # Connect to the user's channel with more debug info
            try:
                # Special handling for wavelink 2.6.3
                player = await channel.connect(cls=wavelink.Player)
                await ctx.send(f"**SIGE!** PAPASOK NA KO SA {channel.name}!")
                print(f"Successfully connected to {channel.name}")
                return
            except Exception as connect_error:
                print(f"Detailed connect error: {connect_error}")
                # Try alternative method
                try:
                    print("Trying alternative connection method...")
                    # Try direct connection without wavelink
                    player = await channel.connect()
                    await ctx.send(f"**CONNECTED!** But not using Wavelink. Some features may not work.")
                    print(f"Connected to {channel.name} without Wavelink")
                    return
                except Exception as alt_error:
                    print(f"Alternative connection failed: {alt_error}")
                    raise Exception(f"Failed to connect: {connect_error} | Alt error: {alt_error}")
            
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
            player = ctx.guild.voice_client
            if not player or not player.channel:
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
            return await ctx.send("**ERROR:** Wavelink/Lavalink is not connected yet! Try again later.")
        
        # Check rate limiting
        if is_rate_limited(ctx.author.id):
            return await ctx.send(f"**TEKA LANG {ctx.author.mention}!** Ang bilis mo mag-type! Hinay-hinay lang!")
        
        add_rate_limit_entry(ctx.author.id)
        
        # Send processing message
        processing_msg = await ctx.send("**SANDALI LANG!** Ginagawa ko pa yung audio...")
        
        try:
            # Generate TTS
            print(f"Generating TTS for message: '{message}'")
            tts = gTTS(text=message, lang='tl', slow=False)
            
            # Create a unique filename for this TTS request
            filename = f"{self.temp_dir}/tts_{ctx.message.id}.mp3"
            print(f"Saving TTS to file: {filename}")
            
            # Save to file
            tts.save(filename)
            
            # Verify file exists
            if not os.path.exists(filename):
                raise Exception("Failed to generate audio file - file does not exist")
            
            if os.path.getsize(filename) == 0:
                raise Exception("Failed to generate audio file - file is empty")
                
            print(f"TTS file generated successfully: {filename} ({os.path.getsize(filename)} bytes)")
            
            # Store in database
            with open(filename, "rb") as f:
                audio_data = f.read()
                audio_id = store_audio_tts(ctx.author.id, message, audio_data)
                print(f"Stored TTS in database with ID: {audio_id}")
            
            # Get or create the player with comprehensive error handling
            print("Getting or creating voice client...")
            try:
                player = ctx.guild.voice_client
                if not player or not player.channel:
                    print(f"Not connected to voice, joining {ctx.author.voice.channel.name}")
                    # Try to connect
                    try:
                        player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
                    except Exception as connect_error:
                        print(f"Error connecting with wavelink.Player: {connect_error}")
                        # Try regular connection if wavelink fails
                        player = await ctx.author.voice.channel.connect()
                        print("Connected with regular player instead of wavelink.Player")
                else:
                    print(f"Already connected to {player.channel.name}")
            except Exception as vc_error:
                raise Exception(f"Failed to connect to voice channel: {vc_error}")
            
            # Play the track using Lavalink (local file)
            try:
                print("Attempting to play audio through Lavalink...")
                # Check if we have a node
                try:
                    node = wavelink.NodePool.get_node()
                    if not node:
                        raise Exception("No Lavalink node available")
                    print(f"Using node: {node}")
                except Exception as node_error:
                    raise Exception(f"Lavalink node error: {node_error}")
                
                # Get filename as url and encode the path
                local_url = f"local:/{os.path.abspath(filename)}"
                print(f"Local URL: {local_url}")

                # Get track from the Node directly with proper query - FIXED for wavelink 2.6.3
                print(f"Fetching track from node...")
                # The first parameter must be the class, second is the query
                result = await node.get_tracks(wavelink.tracks.Playable, local_url)
                
                if not result:
                    raise Exception("Failed to load audio file - no tracks returned")
                    
                print(f"Got tracks: {len(result)} tracks")
                track = result[0]
                
                # Play the track
                print(f"Playing track: {track}")
                await player.play(track)
                
                # Delete the processing message
                await processing_msg.delete()
                
                # Send success message
                await ctx.send(f"🔊 **SPEAKING:** {message}", delete_after=10)
                
                # Clean up the file after playing (delay slightly to ensure it's being played)
                await asyncio.sleep(0.5)
                try:
                    os.remove(filename)
                    print(f"Removed temporary file: {filename}")
                except Exception as e:
                    print(f"Error removing file: {e}")
                
                # Clean up old database entries
                cleanup_old_audio_tts(keep_count=20)
                print("Cleaned up old TTS entries")
                
            except Exception as play_error:
                print(f"Detailed play error: {play_error}")
                import traceback
                traceback.print_exc()
                raise Exception(f"Error playing audio: {play_error}")
            
        except Exception as e:
            print(f"⚠️ TTS ERROR: {e}")
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
        """Replay last TTS message from database using Wavelink"""
        # Check if user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Check if wavelink is working
        if not self.wavelink_connected:
            return await ctx.send("**ERROR:** Wavelink/Lavalink is not connected yet! Try again later.")
        
        # Get the latest audio entry
        audio_data = get_latest_audio_tts()
        if not audio_data:
            return await ctx.send("**WALA AKONG MAALALA!** Wala pa akong na-save na audio.")
        
        audio_id, audio_bytes = audio_data
        
        # Send processing message
        processing_msg = await ctx.send("**SANDALI LANG!** Ire-replay ko pa yung huling audio...")
        
        try:
            # Save audio to temp file
            filename = f"{self.temp_dir}/replay_{ctx.message.id}.mp3"
            with open(filename, "wb") as f:
                f.write(audio_bytes)
                
            print(f"Saved replay audio to file: {filename}")
            
            # Get or create the player
            try:
                player = ctx.guild.voice_client
                if not player or not player.channel:
                    # Try to connect
                    player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
            except Exception as vc_error:
                raise Exception(f"Failed to connect to voice channel: {vc_error}")
            
            # Play the track using Lavalink
            try:
                # Get a node
                node = wavelink.NodePool.get_node()
                if not node:
                    raise Exception("No Lavalink node available")
                
                # Get local file URL
                local_url = f"local:/{os.path.abspath(filename)}"
                print(f"Local URL: {local_url}")

                # Get track from the Node directly with proper query - FIXED for wavelink 2.6.3
                print(f"Fetching track from node...")
                # The first parameter must be the class, second is the query
                result = await node.get_tracks(wavelink.tracks.Playable, local_url)
                
                if not result:
                    raise Exception("Failed to load audio file - no tracks returned")
                
                track = result[0]
                
                # Play the track
                await player.play(track)
                
                # Delete the processing message
                await processing_msg.delete()
                
                # Send success message
                await ctx.send(f"🔊 **REPLAYING:** Last message", delete_after=10)
                
                # Clean up the file after playing
                await asyncio.sleep(0.5)
                try:
                    os.remove(filename)
                except Exception as e:
                    print(f"Error removing file: {e}")
                
            except Exception as play_error:
                raise Exception(f"Error playing audio: {play_error}")
            
        except Exception as e:
            # Try to delete processing message
            try:
                await processing_msg.delete()
            except:
                pass
            
            # Send error message
            error_msg = f"**ERROR:** {str(e)}"
            await ctx.send(error_msg[:1900], delete_after=15)
    
    @commands.command(name="play")
    async def play(self, ctx, *, query: str):
        """Play a song or add it to the queue (g!play <song name or URL>)"""
        # Check if the user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Check if wavelink is working
        if not self.wavelink_connected:
            return await ctx.send("**ERROR:** Wavelink/Lavalink is not connected! Please try again later.")
        
        # Send searching message
        search_msg = await ctx.send(f"**HINAHANAP KO PA:** {query}")
        
        # Get or create the player
        channel = ctx.author.voice.channel
        
        try:
            player = ctx.voice_client
            
            # Create a new player if we don't have one
            if not player or not player.is_connected:
                # Create MusicPlayer instance instead of a regular Wavelink player
                player = await channel.connect(cls=MusicPlayer)
                print(f"Created new MusicPlayer in {channel.name}")
            
            # Check if we need to move the player
            elif player.channel.id != channel.id:
                await player.move_to(channel)
                print(f"Moved player to {channel.name}")
            
            # Cast to MusicPlayer if needed
            if not isinstance(player, MusicPlayer):
                # Disconnect and reconnect with the right player type
                await player.disconnect()
                player = await channel.connect(cls=MusicPlayer)
                print("Reconnected with MusicPlayer class")
                
            player.is_playing = True
            
            # Detect if it's a URL or a search query
            is_url = bool(re.match(r'https?://', query))
            print(f"Query type: {'URL' if is_url else 'Search term'}")
            
            if is_url:
                # Direct URL to a song/playlist - FIXED for wavelink 2.6.3
                # The first parameter must be the class, second is the query
                tracks = await wavelink.NodePool.get_node().get_tracks(wavelink.tracks.Playable, query)
                
                # Check if it's a playlist - using keyword argument format for get_playlist
                playlist = await wavelink.NodePool.get_node().get_playlist(query=query, cls=wavelink.YouTubePlaylist)
                
                if playlist:
                    # Handle YouTube playlist
                    await player.add_tracks(ctx, playlist)
                elif tracks:
                    # Handle single track
                    await player.add_tracks(ctx, tracks)
                else:
                    await ctx.send(f"**ERROR:** Couldn't find anything for: {query}", delete_after=10)
                    
            else:
                # Search for a song on YouTube - FIXED for wavelink 2.6.3
                # The first parameter must be the class, second is the query
                tracks = await wavelink.NodePool.get_node().get_tracks(wavelink.tracks.YouTubeTrack, f"ytsearch:{query}")
                await player.add_tracks(ctx, tracks)
                
            # Remove the search message
            await search_msg.delete()
                
        except Exception as e:
            await search_msg.delete()
            error_msg = f"**ERROR:** {str(e)}"
            print(f"Error in play command: {e}")
            import traceback
            traceback.print_exc()
            await ctx.send(error_msg[:1900], delete_after=15)
            
    @commands.command(name="skip")
    async def skip(self, ctx):
        """Skip the current song"""
        player = ctx.voice_client
        
        if not player or not isinstance(player, MusicPlayer):
            return await ctx.send("**ERROR:** Not playing any music right now.", delete_after=10)
            
        # Check if something is playing
        if not player.now_playing:
            return await ctx.send("**TANGA!** WALA NAMANG TUMUTUGTOG!", delete_after=10)
            
        # Skip the current song
        await player.stop()
        await ctx.send("**NILAKTAWAN KO NA YUNG KANTA NA YAN!**", delete_after=10)
        
    @commands.command(name="queue")
    async def queue(self, ctx):
        """Show the current song queue"""
        player = ctx.voice_client
        
        if not player or not isinstance(player, MusicPlayer):
            return await ctx.send("**ERROR:** Not playing any music right now.", delete_after=10)
            
        # Check if the queue is empty
        if player.queue.is_empty and not player.now_playing:
            return await ctx.send("**WALA PANG LAMAN ANG QUEUE!** Use **g!play** to add songs.", delete_after=15)
            
        # Create a nice embed for the queue
        embed = discord.Embed(
            title="🎵 Music Queue",
            color=Config.EMBED_COLOR_PRIMARY
        )
        
        # Add now playing
        if player.now_playing:
            embed.add_field(
                name="📀 Currently Playing",
                value=f"**{player.now_playing.title}**\n"
                      f"Duration: {format_time(player.now_playing.duration)}\n"
                      f"Requested by: <@{player.now_playing.requester.id}>",
                inline=False
            )
        
        # Add queue items
        if not player.queue.is_empty:
            queue_list = ""
            for i, track in enumerate(player.queue._queue, start=1):
                if i <= 10:  # Show only first 10 songs to avoid large embeds
                    queue_list += f"**{i}.** {track.title} ({format_time(track.duration)})\n"
            
            if len(player.queue) > 10:
                queue_list += f"\n... and {len(player.queue) - 10} more songs"
                
            embed.add_field(
                name="⏱️ Up Next",
                value=queue_list or "The queue is empty.",
                inline=False
            )
        
        await ctx.send(embed=embed, delete_after=30)
    
    @commands.command(name="pause")
    async def pause(self, ctx):
        """Pause the current song"""
        player = ctx.voice_client
        
        if not player or not isinstance(player, MusicPlayer):
            return await ctx.send("**ERROR:** Not playing any music right now.", delete_after=10)
            
        # Check if already paused
        if player.is_paused:
            return await ctx.send("**TANGA!** NASA PAUSE NA NGA EH!", delete_after=10)
            
        # Pause the player
        await player.pause()
        await ctx.send("**⏸️ HININTO KO MUNA!**", delete_after=10)
    
    @commands.command(name="resume")
    async def resume(self, ctx):
        """Resume the current song"""
        player = ctx.voice_client
        
        if not player or not isinstance(player, MusicPlayer):
            return await ctx.send("**ERROR:** Not playing any music right now.", delete_after=10)
            
        # Check if paused
        if not player.is_paused:
            return await ctx.send("**GAGO!** HINDI NAMAN NASA PAUSE!", delete_after=10)
            
        # Resume the player
        await player.resume()
        await ctx.send("**▶️ TULOY ULIT ANG KANTA!**", delete_after=10)
    
    @commands.command(name="stop")
    async def stop(self, ctx):
        """Stop playing and clear the queue"""
        player = ctx.voice_client
        
        if not player or not isinstance(player, MusicPlayer):
            return await ctx.send("**ERROR:** Not playing any music right now.", delete_after=10)
            
        # Clear the queue and stop playing
        player.queue.clear()
        await player.stop()
        player.now_playing = None
        player.is_playing = False
        
        await ctx.send("**⏹️ TUMIGIL NA AKO! INALIS KO NA RIN LAHAT NG SONGS SA QUEUE!**", delete_after=10)
    
    @commands.command(name="nowplaying", aliases=["np"])
    async def nowplaying(self, ctx):
        """Show information about the current song"""
        player = ctx.voice_client
        
        if not player or not isinstance(player, MusicPlayer) or not player.now_playing:
            return await ctx.send("**WALA NAMANG TUMUTUGTOG NGAYON!**", delete_after=10)
            
        # Get current track
        track = player.now_playing
        
        # Create embed with track info
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**{track.title}**",
            color=Config.EMBED_COLOR_PRIMARY,
            url=track.uri
        )
        
        # Add thumbnail if it's a YouTube track
        if hasattr(track, 'thumbnail'):
            embed.set_thumbnail(url=track.thumbnail)
            
        # Track info
        if hasattr(track, 'author'):
            embed.add_field(name="Artist", value=track.author, inline=True)
            
        # Duration and position
        duration = format_time(track.duration)
        position = format_time(player.position)
        
        # Progress bar
        progress = ""
        if track.duration > 0:
            progress = generate_progress_bar(player.position, track.duration)
            
        embed.add_field(
            name="Duration",
            value=f"`{position} {progress} {duration}`",
            inline=False
        )
        
        # Add requester if available
        if hasattr(track, 'requester'):
            embed.set_footer(text=f"Requested by {track.requester.name}")
            
        await ctx.send(embed=embed, delete_after=30)


def format_time(ms):
    """Format milliseconds to MM:SS"""
    if not ms:
        return "0:00"
        
    seconds = int(ms / 1000)
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes}:{seconds:02d}"


def generate_progress_bar(position, duration, length=15):
    """Generate a text progress bar"""
    if not duration:
        return "▱" * length
        
    ratio = position / duration
    played = round(ratio * length)
    remaining = length - played
    
    progress_bar = "▰" * played + "▱" * remaining
    return progress_bar


def setup(bot):
    """Add cog to bot"""
    cog = AudioCog(bot)
    bot.add_cog(cog)
    print("✅ AudioCog loaded")