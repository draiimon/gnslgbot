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

                # Get track from the Node directly with proper query
                print(f"Fetching track from node...")
                result = await node.get_tracks(query=local_url)
                
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
        
        # Send processing message
        processing_msg = await ctx.send("**SANDALI LANG!** Hinahanap ko yung audio...")
        
        try:
            # Get latest audio from database
            print("Fetching latest audio from database...")
            latest_audio = get_latest_audio_tts()
            
            if not latest_audio or not latest_audio[1]:
                await processing_msg.delete()
                return await ctx.send("**WALA PA AKONG NASABI!** Wala pang audio sa database!")
            
            audio_id = latest_audio[0]
            audio_data = latest_audio[1]
            print(f"Found audio with ID: {audio_id}, size: {len(audio_data)} bytes")
            
            # Save to temporary file
            filename = f"{self.temp_dir}/replay_{ctx.message.id}.mp3"
            print(f"Saving audio to temporary file: {filename}")
            with open(filename, "wb") as f:
                f.write(audio_data)
            
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

                # Get track from the Node directly with proper query
                print(f"Fetching track from node...")
                result = await node.get_tracks(query=local_url)
                
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
                await ctx.send(f"🔊 **REPLAY:** Audio ID: {audio_id}", delete_after=10)
                
                # Clean up the file after playing (delay slightly to ensure it's being played)
                await asyncio.sleep(0.5)
                try:
                    os.remove(filename)
                    print(f"Removed temporary file: {filename}")
                except Exception as e:
                    print(f"Error removing file: {e}")
                
            except Exception as play_error:
                print(f"Detailed play error: {play_error}")
                import traceback
                traceback.print_exc()
                raise Exception(f"Error playing audio: {play_error}")
            
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
        """Play a song or add it to the queue (g!play <song name or URL>)"""
        # Check if user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Check if wavelink is working
        if not self.wavelink_connected:
            return await ctx.send("**ERROR:** Wavelink/Lavalink is not connected!")
        
        # Send searching message
        search_msg = await ctx.send(f"**SANDALI LANG!** Hinahanap ko pa: `{query}`...")
        
        try:
            # Get or create player for this guild
            player = ctx.guild.voice_client
            
            # If player doesn't exist or isn't connected, create a new MusicPlayer
            if not player or not player.channel:
                player = await ctx.author.voice.channel.connect(cls=MusicPlayer)
            elif not isinstance(player, MusicPlayer):
                # If we have a regular player but not a MusicPlayer, disconnect and make a MusicPlayer
                await player.disconnect()
                player = await ctx.author.voice.channel.connect(cls=MusicPlayer)
            
            # Process the search query - determine if URL or search term
            is_url = bool(re.match(r'https?://', query))
            
            if is_url:
                # Direct URL to a song/playlist
                tracks = await wavelink.NodePool.get_node().get_tracks(query=query)
                
                # Check if it's a playlist
                playlist = await wavelink.NodePool.get_node().get_playlist(query=query, cls=wavelink.YouTubePlaylist)
                if playlist:
                    # It's a playlist
                    await player.add_tracks(ctx, playlist)
                else:
                    # Just tracks
                    await player.add_tracks(ctx, tracks)
            else:
                # Search for the song on YouTube - fix keyword arguments error
                # In wavelink 2.6.3, search doesn't accept keyword arguments
                tracks = await wavelink.YouTubeTrack.search(query)
                await player.add_tracks(ctx, tracks)
            
            # Delete the searching message
            await search_msg.delete()
            
            # Mark as playing to avoid auto-play confusion
            player.is_playing = True
            
        except Exception as e:
            print(f"⚠️ PLAY ERROR: {e}")
            
            # Try to delete search message
            try:
                await search_msg.delete()
            except:
                pass
            
            # Send error message
            await ctx.send(f"**ERROR:** {str(e)}", delete_after=10)

    @commands.command(name="skip")
    async def skip(self, ctx):
        """Skip the current song"""
        player = ctx.guild.voice_client
        
        if not player or not player.channel:
            return await ctx.send("**TANGA!** WALA AKO SA VOICE CHANNEL!")
            
        if not isinstance(player, MusicPlayer):
            return await ctx.send("**ERROR:** Hindi ko ma-skip ng hindi naka-setup sa Music Player!")
            
        if player.queue.is_empty and not player.now_playing:
            return await ctx.send("**WALA NAMAN AKONG PINAPATUGTOG!** Wala akong ise-skip!")
        
        # Skip current track
        await player.stop()
        await ctx.send("**SIGE!** NAKA-SKIP NA YUNG KANTA!")
        
    @commands.command(name="queue", aliases=["q"])
    async def queue(self, ctx):
        """Show the current song queue"""
        player = ctx.guild.voice_client
        
        if not player or not player.channel or not isinstance(player, MusicPlayer):
            return await ctx.send("**TANGA!** WALA AKONG PINAPATUGTOG!")
            
        if player.queue.is_empty and not player.now_playing:
            return await ctx.send("**WALANG LAMAN YUNG QUEUE!** Bakit di ka mag-request?")
        
        # Create embed for queue
        embed = discord.Embed(
            title="🎵 CURRENT QUEUE 🎵",
            color=Config.EMBED_COLOR_PRIMARY
        )
        
        # Add now playing
        if player.now_playing:
            embed.add_field(
                name="**NOW PLAYING:**",
                value=f"**{player.now_playing.title}**\n" \
                      f"Duration: {datetime.timedelta(milliseconds=player.now_playing.length)}",
                inline=False
            )
        
        # Get queue items and add to embed 
        # Use wavelink 2.6.3 Queue API
        upcoming = list(player.queue._queue)  # This is actually a deque in 2.6.3
        
        if upcoming:
            # Only show first 10 tracks to avoid massive messages
            shown_tracks = upcoming[:10]
            hidden_count = len(upcoming) - 10 if len(upcoming) > 10 else 0
            
            queue_text = []
            for i, track in enumerate(shown_tracks, start=1):
                queue_text.append(
                    f"**{i}.** {track.title} ({datetime.timedelta(milliseconds=track.length)})"
                )
            
            queue_text = "\n".join(queue_text)
            if hidden_count > 0:
                queue_text += f"\n\n*And {hidden_count} more songs...*"
            
            embed.add_field(
                name="**UP NEXT:**",
                value=queue_text,
                inline=False
            )
            
        # Send the embed
        await ctx.send(embed=embed)
        
    @commands.command(name="pause")
    async def pause(self, ctx):
        """Pause the current song"""
        player = ctx.guild.voice_client
        
        if not player or not player.channel:
            return await ctx.send("**TANGA!** WALA AKO SA VOICE CHANNEL!")
        
        if not player.is_playing and not player.is_paused:
            return await ctx.send("**WALA NAMAN AKONG PINAPATUGTOG!** Anong i-pause ko?")
            
        if player.is_paused:
            return await ctx.send("**NAKAHINTO NA NGA GAGO!** Naka-pause na!")
            
        await player.pause()
        await ctx.send("**⏸️ PAUSED:** Hininto ko muna. Type `g!resume` to continue.")
        
    @commands.command(name="resume")
    async def resume(self, ctx):
        """Resume the current song"""
        player = ctx.guild.voice_client
        
        if not player or not player.channel:
            return await ctx.send("**TANGA!** WALA AKO SA VOICE CHANNEL!")
        
        if not player.is_paused:
            return await ctx.send("**NAGPAPATUGTOG NAMAN AKO!** Di naman naka-pause!")
            
        await player.resume()
        await ctx.send("**▶️ RESUMING:** Tuloy ang tugtugan!")
        
    @commands.command(name="stop")
    async def stop(self, ctx):
        """Stop playing and clear the queue"""
        player = ctx.guild.voice_client
        
        if not player or not player.channel:
            return await ctx.send("**TANGA!** WALA AKO SA VOICE CHANNEL!")
        
        if not isinstance(player, MusicPlayer):
            await player.disconnect()
            return await ctx.send("**STOP:** Umalis na ako sa voice channel.")
            
        # Clear the queue if it's a MusicPlayer
        player.queue.clear()
            
        # Stop playback
        await player.stop()
        
        # Reset state
        player.is_playing = False
        player.now_playing = None
        
        await ctx.send("**⏹️ STOPPED:** Inalis ko na lahat ng kanta sa queue.")
        
    @commands.command(name="nowplaying", aliases=["np"])
    async def nowplaying(self, ctx):
        """Show information about the current song"""
        player = ctx.guild.voice_client
        
        if not player or not player.channel or not isinstance(player, MusicPlayer):
            return await ctx.send("**TANGA!** WALA AKONG PINAPATUGTOG!")
            
        if not player.now_playing:
            return await ctx.send("**WALA AKONG PINAPATUGTOG NGAYON!** Bakit di ka mag-request?")
            
        track = player.now_playing
        
        # Create a nice embed with track info
        embed = discord.Embed(
            title="🎵 NOW PLAYING 🎵",
            description=f"**{track.title}**",
            color=Config.EMBED_COLOR_PRIMARY
        )
        
        # Add thumbnail if available (YouTube tracks have this)
        if hasattr(track, 'thumbnail') and track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
            
        # Add track info
        if track.uri:
            embed.add_field(name="Link", value=f"[Click Here]({track.uri})", inline=True)
            
        # Add duration and format a progress bar
        duration = track.length
        position = player.position
        
        def format_time(ms):
            """Format milliseconds to MM:SS"""
            seconds = ms // 1000
            minutes = seconds // 60
            seconds %= 60
            return f"{minutes:02d}:{seconds:02d}"
        
        # Create progress bar
        if duration > 0:  # Avoid division by zero
            bar_length = 20
            progress = int(bar_length * (position / duration))
            progress_bar = "▬" * progress + "🔘" + "▬" * (bar_length - progress - 1)
            
            time_text = f"{format_time(position)} / {format_time(duration)}"
            embed.add_field(
                name="Progress", 
                value=f"{progress_bar}\n{time_text}", 
                inline=False
            )
        
        await ctx.send(embed=embed)
        
def setup(bot):
    """Add cog to bot"""
    bot.add_cog(AudioCog(bot))