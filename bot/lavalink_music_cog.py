import discord
from discord.ext import commands
import asyncio
import re
import os
import random
from typing import Optional, Dict, List, Any, Union
import wavelink
from wavelink.tracks import Playable
from bot.config import Config
from bot.custom_youtube import YouTubeUnblocker, SpotifyUnblocker

# We'll use direct integration with Spotify APIs instead of wavelink.ext.spotify
# since newer versions of wavelink may not have this extension

# Global constants
SPOTIFY_REGEX = r"^(https?://open\.spotify\.com/|spotify:)(track|album|playlist)/([a-zA-Z0-9]+)"
DEFAULT_VOLUME = 50  # Default volume percentage

class MusicPlayer:
    """Class to manage music playback for a specific guild"""
    
    def __init__(self):
        self.queue = []
        self.current = None
        self.position = 0
        self.volume = DEFAULT_VOLUME / 100  # Store as 0-1 value
        self.loop = False
        self.loop_queue = False
        self.text_channel = None
        self.skip_votes = set()
        
    def add(self, track):
        """Add a track to the queue"""
        self.queue.append(track)
        
    def next(self):
        """Get the next track to play based on loop settings"""
        if not self.queue and not self.current:
            return None
            
        # If looping current track
        if self.loop and self.current:
            return self.current
            
        # If queue is empty and not looping the queue
        if not self.queue:
            if self.loop_queue and self.current:
                # Add the current song back to queue in loop queue mode
                self.queue.append(self.current)
            else:
                self.current = None
                return None
        
        # Get next track
        if not self.loop_queue:
            # Normal queue behavior
            self.current = self.queue.pop(0)
        else:
            # Loop queue behavior - move current to end and get next
            if self.current:
                self.queue.append(self.current)
            self.current = self.queue.pop(0)
            
        # Reset skip votes
        self.skip_votes = set()
        
        return self.current
        
    def clear(self):
        """Clear the queue"""
        self.queue = []
        
    def get_queue(self):
        """Get the current queue"""
        queue_list = []
        if self.current:
            queue_list.append(self.current)
        queue_list.extend(self.queue)
        return queue_list
        
    def shuffle(self):
        """Shuffle the queue"""
        random.shuffle(self.queue)


class LavalinkMusicCog(commands.Cog):
    """Advanced music cog using Lavalink for streaming instead of downloading"""
    
    def __init__(self, bot):
        self.bot = bot
        self.players = {}  # Guild ID -> MusicPlayer
        self.spotify_enabled = Config.SPOTIFY_CLIENT_ID and Config.SPOTIFY_CLIENT_SECRET
        self.lavalink_connected = False
        
        # Import the YouTube parser for fallback
        from bot.custom_youtube import YouTubeUnblocker, SpotifyUnblocker
        self.youtube_parser = YouTubeUnblocker()
        self.spotify_parser = SpotifyUnblocker(self.youtube_parser)
        
        # Set up wavelink node when the bot is ready
        bot.loop.create_task(self.connect_nodes())
        
    async def connect_nodes(self):
        """Connect to Lavalink nodes"""
        await self.bot.wait_until_ready()
        
        # Use the primary Lavalink server (now set to Singapore/HK region)
        lavalink_host = Config.LAVALINK_HOST  # Singapore-based server
        lavalink_port = Config.LAVALINK_PORT
        lavalink_password = Config.LAVALINK_PASSWORD
        lavalink_secure = getattr(Config, 'LAVALINK_SECURE', False)  # Default to False if not set
        
        print(f"✓ Connecting to Lavalink server in Asian region at {lavalink_host}:{lavalink_port} (Secure: {lavalink_secure})")
        
        # First try the primary server (Singapore server)
        try:
            # Connect using wavelink 3.x API
            nodes = [
                wavelink.Node(
                    uri=f'{"https" if lavalink_secure else "http"}://{lavalink_host}:{lavalink_port}', 
                    password=lavalink_password
                )
            ]
            await wavelink.Pool.connect(nodes=nodes, client=self.bot)
            self.lavalink_connected = True
            print("✅ Successfully connected to Asia region Lavalink server!")
            return
        except Exception as e:
            print(f"❌ Failed to connect to primary Asia region Lavalink server: {e}")
            print("⚠️ Trying other servers...")
        
        # March 2025 - Updated more reliable servers
        all_servers = [
            # Don't try lavalink.devamop.in again as it's the primary
            {
                'host': 'lavalink4u.herokuapp.com',
                'port': 443,
                'password': 'passwords',
                'secure': True
            },
            {
                'host': 'lavalink.oops.wtf',
                'port': 2000,
                'password': 'www.freelavalink.herokuapp.com',
                'secure': False
            },
            {
                'host': 'lavalinkau.xtremebot.xyz',
                'port': 10232,
                'password': 'alivecapital12',
                'secure': False
            }
        ]
            
        # Try each server directly
        for i, server in enumerate(all_servers):
            try:
                host = server['host']
                port = server['port']
                password = server['password']
                secure = server.get('secure', False)
                
                print(f"🔄 Trying Lavalink server {i+1}: {host}:{port} (Secure: {secure})")
                
                # Create new wavelink nodes
                try:
                    # First, disconnect from any existing nodes
                    try:
                        await wavelink.Pool.disconnect()
                    except:
                        pass  # Ignore any disconnect errors
                    
                    node = wavelink.Node(
                        uri=f'{"https" if secure else "http"}://{host}:{port}', 
                        password=password
                    )
                    
                    await wavelink.Pool.connect(nodes=[node], client=self.bot)
                    self.lavalink_connected = True
                    print(f"✅ Successfully connected to Lavalink server: {host}:{port}")
                    return
                except Exception as connect_error:
                    print(f"❌ Connection error with {host}: {connect_error}")
                    continue
            except Exception as server_error:
                print(f"❌ General error with server: {server_error}")
        
        # If all servers failed
        print("❌ All Lavalink servers failed to connect")
        print("⚠️ The bot will fall back to using the custom YouTube parser for music functionality.")
        self.lavalink_connected = False
        
    def get_player(self, guild_id):
        """Get or create a music player for a guild"""
        if guild_id not in self.players:
            self.players[guild_id] = MusicPlayer()
        return self.players[guild_id]
        
    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        """Event fired when a Lavalink node is ready"""
        print(f"✅ Wavelink node '{node.identifier}' is ready!")
        
    @commands.Cog.listener()
    async def on_wavelink_track_end(self, player: wavelink.Player, track: Playable, reason):
        """Event fired when a track finishes playing"""
        if reason == "FINISHED" or reason == "STOPPED":
            guild_id = player.guild.id
            music_player = self.get_player(guild_id)
            
            # Get the next track based on loop settings
            next_track = music_player.next()
            
            if next_track:
                # Play the next track
                await player.play(next_track)
                
                # Send now playing message
                if music_player.text_channel:
                    await music_player.text_channel.send(f"🎵 Now playing: **{next_track.title}**")
            else:
                # No more tracks in queue
                if music_player.text_channel:
                    await music_player.text_channel.send("✓ Queue finished! Add more songs using `g!play`")
        
    async def join_voice_channel(self, ctx):
        """Join the author's voice channel"""
        if not ctx.author.voice:
            await ctx.send("❌ You need to be in a voice channel first!")
            return None
            
        voice_channel = ctx.author.voice.channel
        
        # Get or create player
        player = ctx.voice_client
        
        # If not connected, connect to the channel
        if not player:
            player = await voice_channel.connect(cls=wavelink.Player)
        # If already connected but to a different channel, move
        elif player.channel.id != voice_channel.id:
            await player.move_to(voice_channel)
            
        # Set the player's volume
        music_player = self.get_player(ctx.guild.id)
        await player.set_volume(int(music_player.volume * 100))
        
        # Store text channel for notifications
        music_player.text_channel = ctx.channel
        
        return player
        
    @commands.command(name="lplay", aliases=["lp"])
    async def lplay(self, ctx, *, query: str = None):
        """Play music from various sources (YouTube, Spotify, SoundCloud, etc.)
        
        Usage:
        g!play <search query>
        g!play <YouTube URL>
        g!play <Spotify URL>
        g!play <SoundCloud URL>
        """
        if not query:
            await ctx.send("❌ Ano ba gusto mong i-play? Mag-specify ka ng URL o search query!")
            return
            
        # Check if user is in a voice channel
        if not ctx.author.voice:
            await ctx.send("❌ Sumali ka muna sa voice channel, tanga!")
            return
            
        # Show "typing" indicator to signal the bot is working
        async with ctx.typing():
            # Join voice channel
            player = await self.join_voice_channel(ctx)
            if not player:
                return
                
            # Get the guild's music player
            music_player = self.get_player(ctx.guild.id)
                
            # Handle Spotify URLs
            spotify_match = re.match(SPOTIFY_REGEX, query)
            
            try:
                # Handle different query types
                if spotify_match:
                    content_type = spotify_match.group(2)
                    content_id = spotify_match.group(3)
                    
                    # Newer wavelink versions handle Spotify URLs directly
                    await ctx.send(f"⏳ Processing Spotify {content_type}... (ito'y maaaring tumagal ng ilang segundo)")
                    
                    try:
                        # Let wavelink handle the Spotify URL resolution
                        tracks = await wavelink.Playable.search(query)
                        
                        if not tracks:
                            # Try to search for the track name instead as fallback
                            if content_type == 'track' and self.spotify_enabled:
                                # Try to get track info from Spotify API
                                import spotipy
                                from spotipy.oauth2 import SpotifyClientCredentials
                                
                                sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
                                    client_id=Config.SPOTIFY_CLIENT_ID,
                                    client_secret=Config.SPOTIFY_CLIENT_SECRET
                                ))
                                
                                track_info = sp.track(content_id)
                                if track_info:
                                    artists = ", ".join([artist["name"] for artist in track_info["artists"]])
                                    search_query = f"{track_info['name']} {artists}"
                                    
                                    # Search on YouTube instead
                                    await ctx.send(f"🔄 Using YouTube to search for: **{search_query}**")
                                    tracks = await wavelink.Playable.search(f"ytsearch:{search_query}")
                            
                        if tracks:
                            if content_type in ['playlist', 'album']:
                                # Limit to 25 tracks to avoid abuse
                                for track in tracks[:25]:
                                    music_player.add(track)
                                
                                await ctx.send(f"✓ Added **{len(tracks[:25])}** tracks from Spotify {content_type}")
                            else:
                                # Single track
                                track = tracks[0]
                                music_player.add(track)
                                await ctx.send(f"✓ Added to queue (from Spotify): **{track.title}**")
                        else:
                            await ctx.send(f"❌ Hindi ma-access ang Spotify {content_type}!")
                            return
                    except Exception as e:
                        await ctx.send(f"❌ Error processing Spotify {content_type}: {str(e)}")
                        print(f"Spotify error: {e}")
                        return
                
                # SoundCloud URL
                elif 'soundcloud.com' in query.lower():
                    tracks = await wavelink.Playable.search(query)
                    if tracks:
                        track = tracks[0]
                        music_player.add(track)
                        await ctx.send(f"✓ Added to queue (from SoundCloud): **{track.title}**")
                    else:
                        await ctx.send("❌ Hindi ma-access ang SoundCloud track!")
                        return
                        
                # Search or play regular URL (YouTube, direct link, etc.)
                else:
                    # Determine if it's a direct URL or a search query
                    if re.match(r'^https?://', query):
                        # It's a URL
                        tracks = await wavelink.Playable.search(query)
                        if tracks:
                            track = tracks[0]
                            music_player.add(track)
                            await ctx.send(f"✓ Added to queue: **{track.title}**")
                        else:
                            await ctx.send("❌ Hindi ma-access ang URL na yan!")
                            return
                    else:
                        # It's a search query - search YouTube
                        await ctx.send(f"🔎 Searching for: **{query}**")
                        tracks = await wavelink.Playable.search(f"ytsearch:{query}")
                        
                        if not tracks:
                            await ctx.send(f"❌ Walang nahanap na results para sa '{query}'")
                            return
                            
                        # Take the first result
                        track = tracks[0]
                        music_player.add(track)
                        await ctx.send(f"✓ Added to queue: **{track.title}**")
                
                # Start playing if not already playing
                if not player.is_playing():
                    # Get the first track from the queue
                    track = music_player.next()
                    if track:
                        await player.play(track)
                        await ctx.send(f"🎵 Now playing: **{track.title}**")
                        
            except Exception as e:
                print(f"Error in play command: {e}")
                
                # If Lavalink is not connected, try using the custom YouTube parser as fallback
                if not self.lavalink_connected:
                    await ctx.send("⚠️ Falling back to custom YouTube parser...")
                    
                    try:
                        # Determine if it's a Spotify URL
                        if spotify_match:
                            content_type = spotify_match.group(2)
                            content_id = spotify_match.group(3)
                            
                            if content_type == 'track':
                                track_info = self.spotify_parser.get_track_info(query)
                                if track_info:
                                    await ctx.send(f"✓ Found on YouTube instead: **{track_info['title']}**")
                                    
                                    # Store track info
                                    music_player.add(track_info)
                                    
                                    # Let the user know we're using a fallback
                                    await ctx.send(f"✓ Added to queue (via YouTube): **{track_info['title']}**")
                                else:
                                    await ctx.send("❌ Could not find the Spotify track on YouTube.")
                                    return
                            else:
                                await ctx.send("❌ Spotify playlists require Lavalink connection, which is currently unavailable.")
                                return
                        
                        # Handle YouTube or general search
                        elif 'youtube.com' in query.lower() or 'youtu.be' in query.lower():
                            # It's a YouTube URL
                            video_id = self.youtube_parser.extract_video_id(query)
                            if video_id:
                                video_info = self.youtube_parser.get_video_info(video_id)
                                if video_info:
                                    # Add to queue
                                    music_player.add(video_info)
                                    await ctx.send(f"✓ Added to queue (via direct parser): **{video_info['title']}**")
                                else:
                                    await ctx.send("❌ Could not get video information.")
                                    return
                            else:
                                await ctx.send("❌ Invalid YouTube URL.")
                                return
                        else:
                            # It's a search query
                            await ctx.send(f"🔎 Searching for: **{query}**")
                            search_results = self.youtube_parser.search_videos(query, max_results=1)
                            
                            if search_results:
                                video_info = search_results[0]
                                # Add to queue
                                music_player.add(video_info)
                                await ctx.send(f"✓ Added to queue: **{video_info['title']}**")
                            else:
                                await ctx.send(f"❌ No results found for '{query}'")
                                return
                        
                        # Start playing if not already playing
                        if not player.is_playing():
                            # Get the first track from the queue
                            track = music_player.next()
                            if track:
                                # Connect to voice channel if not already connected
                                if not ctx.voice_client:
                                    await self.join_voice_channel(ctx)
                                
                                # This is a custom track object, not a wavelink track
                                # We need to handle it differently
                                await ctx.send(f"🎵 Now playing: **{track['title']}**")
                                
                                # Here we would add code to play the track using FFmpeg
                                # But for now, just inform the user that playback isn't implemented
                                await ctx.send("⚠️ Fallback playback not fully implemented. Please check back later.")
                    
                    except Exception as fallback_error:
                        print(f"Error in fallback mode: {fallback_error}")
                        await ctx.send(f"❌ Error in fallback mode: {str(fallback_error)}")
                else:
                    # If Lavalink is available but there was still an error, show the original error
                    await ctx.send(f"❌ Error: {str(e)}")
    
    @commands.command(name="lstop")
    async def lstop(self, ctx):
        """Stop playing and clear the queue"""
        player = ctx.voice_client
        
        if not player or not player.is_playing():
            await ctx.send("❌ Wala naman akong pinapatugtog!")
            return
            
        # Get the guild's music player and clear the queue
        music_player = self.get_player(ctx.guild.id)
        music_player.clear()
        music_player.current = None
        
        # Stop the player
        await player.stop()
        
        await ctx.send("✓ Inistop at ni-clear ang queue!")
    
    @commands.command(name="lskip", aliases=["ls"])
    async def lskip(self, ctx):
        """Skip the current song or vote to skip"""
        player = ctx.voice_client
        
        if not player or not player.is_playing():
            await ctx.send("❌ Wala naman akong pinapatugtog!")
            return
            
        # Get the guild's music player
        guild_id = ctx.guild.id
        music_player = self.get_player(guild_id)
        
        # Check if author is DJ or admin (can force skip)
        is_dj = ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_channels
        
        if is_dj:
            # DJ can force skip
            await ctx.send("✓ Admin/DJ force skipped the current song.")
            await player.stop()
            return
            
        # Get the number of members in voice channel (excluding bots)
        voice_members = [m for m in player.channel.members if not m.bot]
        required_votes = max(2, len(voice_members) // 2)  # At least 2 votes or 50%
        
        # Register vote
        music_player.skip_votes.add(ctx.author.id)
        
        # Check if we have enough votes
        current_votes = len(music_player.skip_votes)
        
        if current_votes >= required_votes:
            await ctx.send(f"✓ Vote skip successful ({current_votes}/{required_votes}).")
            await player.stop()
        else:
            await ctx.send(f"✓ Skip vote added ({current_votes}/{required_votes} needed).")
    
    @commands.command(name="lqueue", aliases=["lq"])
    async def lqueue(self, ctx):
        """Show the current music queue"""
        player = ctx.voice_client
        music_player = self.get_player(ctx.guild.id)
        queue = music_player.get_queue()
        
        if not queue:
            await ctx.send("❌ Walang laman ang queue!")
            return
            
        # Create an embed for the queue
        embed = discord.Embed(
            title="🎵 Music Queue",
            color=0xFF5733
        )
        
        # Add current track
        current = music_player.current
        if current and player.is_playing():
            # Calculate the current position
            position_ms = player.position
            duration_ms = current.duration
            
            # Format as MM:SS
            position_str = f"{position_ms // 60000}:{(position_ms % 60000) // 1000:02d}"
            duration_str = f"{duration_ms // 60000}:{(duration_ms % 60000) // 1000:02d}"
            
            embed.add_field(
                name="Now Playing",
                value=f"**{current.title}** [{position_str}/{duration_str}]",
                inline=False
            )
        
        # Add upcoming tracks
        queue_text = ""
        start_index = 1 if current and player.is_playing() else 0
        
        for i, track in enumerate(queue[start_index:], start=1):
            if i > 10:  # Limit to 10 tracks
                remaining = len(queue) - start_index - 10
                queue_text += f"\n*And {remaining} more...*"
                break
                
            # Format duration as MM:SS
            duration_str = f"{track.duration // 60000}:{(track.duration % 60000) // 1000:02d}"
            queue_text += f"\n**{i}.** {track.title} [{duration_str}]"
        
        if queue_text:
            embed.add_field(
                name="Up Next",
                value=queue_text,
                inline=False
            )
        
        # Add queue status
        embed.set_footer(text=f"Loop: {'✅' if music_player.loop else '❌'} | Loop Queue: {'✅' if music_player.loop_queue else '❌'} | Volume: {int(music_player.volume * 100)}%")
        
        await ctx.send(embed=embed)
    
    @commands.command(name="lpause")
    async def lpause(self, ctx):
        """Pause the current song"""
        player = ctx.voice_client
        
        if not player or not player.is_playing():
            await ctx.send("❌ Wala naman akong pinapatugtog!")
            return
            
        if player.is_paused():
            await ctx.send("❌ Naka-pause na talaga!")
            return
            
        await player.pause()
        await ctx.send("⏸️ Ni-pause ang music.")
    
    @commands.command(name="lresume", aliases=["lunpause"])
    async def lresume(self, ctx):
        """Resume the current song"""
        player = ctx.voice_client
        
        if not player or not player.is_playing():
            await ctx.send("❌ Wala naman akong pinapatugtog!")
            return
            
        if not player.is_paused():
            await ctx.send("❌ Hindi naman naka-pause!")
            return
            
        await player.resume()
        await ctx.send("▶️ Ni-resume ang music.")
    
    @commands.command(name="lvolume", aliases=["lvol", "lv"])
    async def lvolume(self, ctx, volume: int = None):
        """Set the volume (0-100)"""
        player = ctx.voice_client
        music_player = self.get_player(ctx.guild.id)
        
        if volume is None:
            await ctx.send(f"✓ Current volume: **{int(music_player.volume * 100)}%**")
            return
            
        if not 0 <= volume <= 100:
            await ctx.send("❌ Volume ay dapat nasa pagitan ng 0 at 100!")
            return
            
        # Update the stored volume
        music_player.volume = volume / 100
        
        # Update the player's volume if connected
        if player:
            await player.set_volume(volume)
            
        await ctx.send(f"✓ Volume set to **{volume}%**")
    
    @commands.command(name="lloop", aliases=["ll"])
    async def lloop(self, ctx):
        """Toggle loop for the current song"""
        music_player = self.get_player(ctx.guild.id)
        music_player.loop = not music_player.loop
        
        # Turn off loop queue if enabling loop
        if music_player.loop:
            music_player.loop_queue = False
            
        await ctx.send(f"🔂 Song loop: **{'Enabled' if music_player.loop else 'Disabled'}**")
    
    @commands.command(name="lloopqueue", aliases=["llq"])
    async def lloopqueue(self, ctx):
        """Toggle loop for the entire queue"""
        music_player = self.get_player(ctx.guild.id)
        music_player.loop_queue = not music_player.loop_queue
        
        # Turn off single song loop if enabling loop queue
        if music_player.loop_queue:
            music_player.loop = False
            
        await ctx.send(f"🔁 Queue loop: **{'Enabled' if music_player.loop_queue else 'Disabled'}**")
    
    @commands.command(name="lshuffle")
    async def lshuffle(self, ctx):
        """Shuffle the queue"""
        music_player = self.get_player(ctx.guild.id)
        
        if not music_player.queue:
            await ctx.send("❌ Walang laman ang queue!")
            return
            
        music_player.shuffle()
        await ctx.send("🔀 Shuffled the queue!")
    
    @commands.command(name="lnowplaying", aliases=["lnp"])
    async def lnowplaying(self, ctx):
        """Show information about the currently playing song"""
        player = ctx.voice_client
        
        if not player or not player.is_playing():
            await ctx.send("❌ Wala naman akong pinapatugtog!")
            return
            
        music_player = self.get_player(ctx.guild.id)
        track = music_player.current
        
        if not track:
            await ctx.send("❌ Wala naman akong pinapatugtog!")
            return
            
        # Calculate the progress bar
        position_ms = player.position
        duration_ms = track.duration
        bar_length = 20
        
        # Create a progress bar
        if duration_ms > 0:  # Avoid division by zero
            progress = int((position_ms / duration_ms) * bar_length)
            progress_bar = "▬" * progress + "🔘" + "▬" * (bar_length - progress - 1)
        else:
            progress_bar = "▬" * bar_length
            
        # Format times as MM:SS
        position_str = f"{position_ms // 60000}:{(position_ms % 60000) // 1000:02d}"
        duration_str = f"{duration_ms // 60000}:{(duration_ms % 60000) // 1000:02d}"
        
        # Create an embed
        embed = discord.Embed(
            title="Now Playing",
            description=f"**{track.title}**",
            color=0xFF5733
        )
        
        # Add progress bar and times
        embed.add_field(
            name="Progress",
            value=f"{progress_bar}\n{position_str} / {duration_str}",
            inline=False
        )
        
        # Add author
        embed.add_field(
            name="Author", 
            value=track.author, 
            inline=True
        )
        
        # Add source
        source = "YouTube"
        # Check URL to determine source
        if hasattr(track, 'uri') and 'spotify.com' in str(track.uri):
            source = "Spotify"
        elif hasattr(track, 'uri') and 'soundcloud.com' in str(track.uri):
            source = "SoundCloud"
            
        # SoundCloud track check handled via URI above
            
        embed.add_field(
            name="Source", 
            value=source, 
            inline=True
        )
        
        # Set thumbnail if available
        if hasattr(track, 'thumbnail') and track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
            
        await ctx.send(embed=embed)
    
    @commands.command(name="lseek")
    async def lseek(self, ctx, *, time: str):
        """Seek to a specific position in the song (eg. "1:30")"""
        player = ctx.voice_client
        
        if not player or not player.is_playing():
            await ctx.send("❌ Wala naman akong pinapatugtog!")
            return
            
        # Parse the time input (supports MM:SS or seconds)
        try:
            if ":" in time:
                minutes, seconds = time.split(":")
                position_ms = (int(minutes) * 60 + int(seconds)) * 1000
            else:
                position_ms = int(time) * 1000
        except ValueError:
            await ctx.send("❌ Invalid time format! Use MM:SS or seconds.")
            return
            
        # Check if position is valid
        track = self.get_player(ctx.guild.id).current
        if position_ms > track.duration:
            await ctx.send(f"❌ Position too high! Max is {track.duration//60000}:{(track.duration%60000)//1000:02d}")
            return
            
        # Seek to position
        await player.seek(position_ms)
        await ctx.send(f"⏩ Seeked to {position_ms//60000}:{(position_ms%60000)//1000:02d}")
    
    @commands.command(name="ldisconnect", aliases=["ldc", "lleave"])
    async def ldisconnect(self, ctx):
        """Disconnect the bot from voice channel"""
        player = ctx.voice_client
        
        if not player or not player.is_connected():
            await ctx.send("❌ Hindi naman ako naka-connect sa voice channel!")
            return
            
        # Clear the queue
        music_player = self.get_player(ctx.guild.id)
        music_player.clear()
        music_player.current = None
        
        # Disconnect
        await player.disconnect()
        await ctx.send("👋 Umalis ako sa voice channel!")
        
    @commands.command(name="lsoundcloud", aliases=["lsc"])
    async def lsoundcloud(self, ctx, *, query: str):
        """Play music from SoundCloud"""
        # This basically calls the play command but forces SoundCloud search
        if not query.startswith('https://soundcloud.com'):
            # If it's not already a SoundCloud URL, make it a search
            query = f"scsearch:{query}"
        await self.lplay(ctx, query=query)
        
    @commands.command(name="lmusichelp", aliases=["lmhelp"])
    async def lmusichelp(self, ctx):
        """Show help for all music commands"""
        streaming_status = "✅ Advanced streaming mode" if self.lavalink_connected else "⚠️ Basic playback mode (no Lavalink)"
        
        embed = discord.Embed(
            title="🎵 Ginsilog Music Commands",
            description=f"Ang bagong music player ng Ginsilog!\n\n**Status: {streaming_status}**",
            color=0xFF5733
        )
        
        # Playback commands
        embed.add_field(
            name="Playback Commands",
            value=(
                "g!lplay <search/URL> - Magpatugtog ng music (YouTube, Spotify, SoundCloud)\n"
                "g!lstop - Itigil ang music at i-clear ang queue\n"
                "g!lskip - Skip sa susunod na kanta\n"
                "g!lpause - I-pause ang kanta\n"
                "g!lresume - Ituloy ang patugtog\n"
                "g!lseek <time> - Lumipat sa partikular na oras (eg. '1:30')\n"
                "g!ldisconnect - Umalis sa voice channel"
            ),
            inline=False
        )
        
        # Queue commands
        embed.add_field(
            name="Queue Commands",
            value=(
                "g!lqueue - Ipakita ang queue\n"
                "g!lloop - I-loop ang kasalukuyang kanta\n"
                "g!lloopqueue - I-loop ang buong queue\n"
                "g!lshuffle - I-shuffle ang queue\n"
                "g!lnowplaying - Ipakita ang detalye ng kasalukuyang tumutugtog\n"
                "g!lvolume <0-100> - I-adjust ang volume"
            ),
            inline=False
        )
        
        # Special commands
        embed.add_field(
            name="Special Commands",
            value=(
                "g!lsoundcloud <search/URL> - Magpatugtog mula sa SoundCloud\n"
                "g!lmusichelp - Ipakita ang listahan ng mga commands"
            ),
            inline=False
        )
        
        if self.lavalink_connected:
            footer_text = "Music powered by Lavalink - Supports YouTube, Spotify, and SoundCloud"
        else:
            footer_text = "Running in fallback mode - Some features may be limited"
            
        embed.set_footer(text=footer_text)
        await ctx.send(embed=embed)
        

def setup(bot):
    bot.add_cog(LavalinkMusicCog(bot))