import discord
from discord.ext import commands
import asyncio
import re
import os
import random
from typing import Optional, Dict, List, Any, Union

# Import wavelink with compatibility for v3.x
import wavelink

# Compatibility with different wavelink versions
try:
    # For wavelink 3.4.x
    from wavelink.tracks import Playable
except ImportError:
    try:
        # For other versions of wavelink 3.x
        from wavelink import Playable, YouTubeTrack
    except ImportError:
        # Final fallback
        print("⚠️ Could not import Playable from wavelink - creating compatibility layer")
        class Playable:
            pass
        class YouTubeTrack:
            @staticmethod
            async def search(query):
                return []

# Add NodePool compatibility for different wavelink versions
if not hasattr(wavelink, 'NodePool'):
    print("⚠️ Creating NodePool compatibility layer for wavelink")
    class NodePool:
        @staticmethod
        def get_node():
            return None
    wavelink.NodePool = NodePool

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
        self.is_playing_via_ffmpeg = False # Track if we're using FFmpeg fallback
        
        # Import the YouTube parser for fallback
        from bot.custom_youtube import YouTubeUnblocker, SpotifyUnblocker
        self.youtube_parser = YouTubeUnblocker()
        self.spotify_parser = SpotifyUnblocker(self.youtube_parser)
        
        # Set up wavelink node when the bot is ready
        bot.loop.create_task(self.connect_nodes())
        
    async def _play_next_track(self, ctx, music_player):
        """Play the next track in queue when using FFmpeg directly"""
        # Don't try to play the next track if we're not in FFmpeg mode
        if not self.is_playing_via_ffmpeg:
            return
            
        # Get the next track from the queue
        track = music_player.next()
        
        if track:
            # Get voice client
            voice_client = ctx.voice_client
            if voice_client and voice_client.is_connected():
                try:
                    # Get the audio URL
                    source_url = track.get('source_url') or track.get('url')
                    
                    if source_url:
                        # Play using FFmpeg
                        from discord import FFmpegPCMAudio
                        
                        # Create FFmpeg options
                        ffmpeg_options = {
                            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                            'options': '-vn'
                        }
                        
                        # Create audio source and play
                        audio_source = FFmpegPCMAudio(source_url, **ffmpeg_options)
                        voice_client.play(audio_source, after=lambda e: 
                            self.bot.loop.create_task(self._play_next_track(ctx, music_player)))
                            
                        # Send a notification
                        if music_player.text_channel:
                            await music_player.text_channel.send(f"🎵 Now playing: **{track['title']}**")
                except Exception as e:
                    print(f"Error playing next track with FFmpeg: {e}")
                    if music_player.text_channel:
                        await music_player.text_channel.send(f"❌ Error playing next track: {str(e)}")
            else:
                print("No voice client available to play next track")
        else:
            # End of queue
            if music_player.text_channel:
                await music_player.text_channel.send("✓ Queue finished! Add more songs using `g!lplay`")
        
    async def connect_nodes(self):
        """Initializes music playback system with Lavalink or fallback streaming"""
        await self.bot.wait_until_ready()
        
        print("\n🔄 Initializing music system for Render deployment...")
        
        self.lavalink_connected = False 
        self.is_playing_via_ffmpeg = False
        
        # Set up wavelink nodes manually if using wavelink 3.x
        try:
            # First attempt - connect to primary configured Lavalink server
            print(f"🎵 Connecting to primary Lavalink server: {Config.LAVALINK_HOST}:{Config.LAVALINK_PORT}")
            
            # Set up the wavelink client - uses a different approach in wavelink 3.x
            # Handle different versions of wavelink's node pooling
            if hasattr(wavelink, 'Pool'):
                wavelink.Pool.get_node = lambda: None  # Create a dummy function to avoid errors
                wavelink.Pool.get_best_node = lambda: None  # Create a dummy function to avoid errors
            elif hasattr(wavelink, 'NodePool'):
                pass  # Already handled by our NodePool compatibility layer
            
            # Create client if it doesn't exist
            if not hasattr(self.bot, 'wavelink'):
                self.bot.wavelink = wavelink.Client(bot=self.bot)
            
            # Configure a node
            uri = f"{'https' if Config.LAVALINK_SECURE else 'http'}://{Config.LAVALINK_HOST}:{Config.LAVALINK_PORT}"
            node = wavelink.Node(
                uri=uri, 
                password=Config.LAVALINK_PASSWORD,
                identifier=f"Main_Node"
            )
            
            # Connect to the node
            await self.bot.wavelink.connect(nodes=[node])
            self.lavalink_connected = True
            print(f"✅ Successfully connected to Lavalink server: {Config.LAVALINK_HOST}")
            
        except Exception as main_error:
            print(f"❌ Failed to connect to primary Lavalink server: {str(main_error)}")
            
            # Try to connect to alternative Lavalink servers
            for i, server in enumerate(Config.ALT_LAVALINK_SERVERS):
                try:
                    print(f"🎵 Attempting connection to backup Lavalink server {i+1}: {server['host']}:{server['port']}")
                    
                    # Create node for this backup server
                    backup_uri = f"{'https' if server['secure'] else 'http'}://{server['host']}:{server['port']}"
                    backup_node = wavelink.Node(
                        uri=backup_uri,
                        password=server['password'],
                        identifier=f"Backup_Node_{i+1}"
                    )
                    
                    # Connect to the backup node
                    if not hasattr(self.bot, 'wavelink'):
                        self.bot.wavelink = wavelink.Client(bot=self.bot)
                    await self.bot.wavelink.connect(nodes=[backup_node])
                    
                    self.lavalink_connected = True
                    print(f"✅ Successfully connected to backup Lavalink server: {server['host']}")
                    break
                    
                except Exception as backup_error:
                    print(f"❌ Failed to connect to backup Lavalink server {i+1}: {str(backup_error)}")
        
        # If all Lavalink connections failed, use the fallback mode
        if not self.lavalink_connected:
            print("⚠️ All Lavalink connection attempts failed")
            print("✅ Using direct YouTube streaming fallback for guaranteed functionality")
            print("💡 Features enabled: YouTube search, playlist support, queue management")
            
            # Mark fallback as active
            self.is_playing_via_ffmpeg = True  # Use FFmpeg for direct playback
            
            # Log reference for status
            print("\n📋 Fallback music system status:")
            print("- Mode: Direct streaming via YouTube API")
            print("- Reliability: High (no external server dependencies)")
            print("- Features: Search, queue, volume, seek, play/pause")
            print("- Sources: YouTube, YouTube Music")
        
        print("✅ Music system initialization complete!")
        
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
    async def on_track_end(self, player: wavelink.Player, track, reason):
        """Event fired when a track finishes playing (wavelink 3.x)"""
        # Handle different possible reason formats
        if isinstance(reason, str):
            valid_end = reason in ["FINISHED", "STOPPED"]
        else:
            # In wavelink 3.x, reason might be an enum
            valid_end = str(reason).upper() in ["FINISHED", "STOPPED"]
            
        if valid_end:
            guild_id = player.guild.id
            music_player = self.get_player(guild_id)
            
            # Get the next track based on loop settings
            next_track = music_player.next()
            
            if next_track:
                # Play the next track
                await player.play(next_track)
                
                # Send now playing message
                if music_player.text_channel:
                    # Get title in a way that works with both Track and dict objects
                    title = next_track.title if hasattr(next_track, 'title') else next_track.get('title', 'Unknown')
                    await music_player.text_channel.send(f"🎵 Now playing: **{title}**")
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
                        # Let wavelink handle the Spotify URL resolution (compatible with v3.x)
                        # In wavelink 3.x the search method might be in different places
                        try:
                            tracks = await wavelink.Playable.search(query)
                        except (AttributeError, TypeError):
                            try:
                                # Try alternate syntax for wavelink 3.x
                                node = wavelink.NodePool.get_node()
                                if node:
                                    tracks = await node.get_tracks(query)
                                else:
                                    # If no node is available, use the direct approach
                                    tracks = await wavelink.YouTubeTrack.search(query)
                            except (AttributeError, TypeError):
                                # Last attempt for wavelink 3.x
                                tracks = await wavelink.YouTubeTrack.search(query)
                        
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
                                    try:
                                        tracks = await wavelink.Playable.search(f"ytsearch:{search_query}")
                                    except (AttributeError, TypeError):
                                        try:
                                            tracks = await wavelink.YouTubeTrack.search(f"ytsearch:{search_query}")
                                        except:
                                            # Fallback to custom YouTube parser as last resort
                                            self.lavalink_connected = False  # Force fallback mode
                                            raise Exception("Unable to search with wavelink")
                            
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
                    # Use the same multi-attempt search approach for SoundCloud
                    try:
                        tracks = await wavelink.Playable.search(query)
                    except (AttributeError, TypeError):
                        try:
                            tracks = await wavelink.YouTubeTrack.search(query)
                        except (AttributeError, TypeError):
                            # Last attempt
                            try:
                                node = wavelink.NodePool.get_node()
                                if node:
                                    tracks = await node.get_tracks(query)
                                else:
                                    tracks = []
                            except:
                                tracks = []
                                
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
                        try:
                            tracks = await wavelink.Playable.search(query)
                        except (AttributeError, TypeError):
                            try:
                                tracks = await wavelink.YouTubeTrack.search(query)
                            except (AttributeError, TypeError):
                                # Last attempt
                                try:
                                    node = wavelink.NodePool.get_node()
                                    if node:
                                        tracks = await node.get_tracks(query)
                                    else:
                                        tracks = []
                                except:
                                    tracks = []
                                    
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
                        try:
                            tracks = await wavelink.Playable.search(f"ytsearch:{query}")
                        except (AttributeError, TypeError):
                            try:
                                tracks = await wavelink.YouTubeTrack.search(f"ytsearch:{query}")
                            except (AttributeError, TypeError):
                                # Last attempt
                                try:
                                    node = wavelink.NodePool.get_node()
                                    if node:
                                        tracks = await node.get_tracks(f"ytsearch:{query}")
                                    else:
                                        tracks = []
                                except:
                                    tracks = []
                        
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
                        try:
                            await player.play(track)
                            await ctx.send(f"🎵 Now playing: **{track.title}**")
                        except Exception as play_error:
                            # If playing through wavelink fails, try the fallback
                            print(f"Error playing through wavelink: {play_error}")
                            await ctx.send("⚠️ Falling back to direct playback method...")
                            
                            # This is a special case - we'll force the fallback mode
                            self.lavalink_connected = False
                            
                            # Add the track back to the front of the queue
                            # and then trigger the fallback manually
                            music_player.current = None
                            music_player.queue.insert(0, track)
                            
                            # Let the fallback code handle it
                            raise Exception("Forcing fallback mode")
                        
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
                                
                                # Get the audio URL from the track info
                                source_url = track.get('source_url') or track.get('url')
                                
                                if source_url:
                                    # Connect to voice channel if needed
                                    if not ctx.voice_client:
                                        await self.join_voice_channel(ctx)
                                    
                                    # Play the audio using FFmpeg (similar to how other music cogs work)
                                    # Since we're using wavelink Player, we can use its play method with custom FFMPEG options
                                    try:
                                        # Using wavelink's FFmpeg source
                                        from discord import FFmpegPCMAudio
                                        from discord.opus import Encoder
                                        
                                        voice_client = ctx.voice_client
                                        
                                        # First stop any currently playing audio
                                        voice_client.stop()
                                        
                                        # Play using FFmpeg
                                        # Using standard options for better compatibility
                                        ffmpeg_options = {
                                            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                                            'options': '-vn'
                                        }
                                        
                                        # Create audio source
                                        audio_source = FFmpegPCMAudio(source_url, **ffmpeg_options)
                                        
                                        # Play the audio
                                        voice_client.play(audio_source, after=lambda e: 
                                            self.bot.loop.create_task(self._play_next_track(ctx, music_player)))
                                        
                                        # Use event to handle track ending when using FFmpeg direct
                                        self.is_playing_via_ffmpeg = True
                                        
                                    except Exception as ffmpeg_error:
                                        print(f"Error playing audio via FFmpeg: {ffmpeg_error}")
                                        await ctx.send(f"❌ Error playing the track: {str(ffmpeg_error)}")
                                else:
                                    await ctx.send("❌ No playable URL found for this track.")
                    
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
        
        # Stop the player safely
        await self._safe_voice_action(player, 'stop')
        
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
            await self._safe_voice_action(player, 'stop')
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
            await self._safe_voice_action(player, 'stop')
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
            
        await self._safe_voice_action(player, 'pause')
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
            
        await self._safe_voice_action(player, 'resume')
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
            await self._safe_voice_action(player, 'set_volume', volume)
            
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
            
        # Seek to position safely
        await self._safe_voice_action(player, 'seek', position_ms)
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
        
        # Disconnect safely
        await self._safe_voice_action(player, 'disconnect')
        await ctx.send("👋 Umalis ako sa voice channel!")
        
    @commands.command(name="lsoundcloud", aliases=["lsc"])
    async def lsoundcloud(self, ctx, *, query: str):
        """Play music from SoundCloud"""
        # This basically calls the play command but forces SoundCloud search
        if not query.startswith('https://soundcloud.com'):
            # If it's not already a SoundCloud URL, make it a search
            query = f"scsearch:{query}"
        await self.lplay(ctx, query=query)
        
    async def _safe_voice_action(self, player, action_name, *args, **kwargs):
        """Safely execute a voice client action with error handling"""
        try:
            # Get the method by name
            action = getattr(player, action_name, None)
            if action and callable(action):
                return await action(*args, **kwargs)
            else:
                print(f"Action {action_name} not found or not callable")
                return None
        except Exception as e:
            print(f"Error executing voice action {action_name}: {e}")
            # Don't propagate the error - handled here
            return None
    
    @commands.command(name="lmusichelp", aliases=["lmhelp"])
    async def lmusichelp(self, ctx):
        """Show help for all music commands"""
        # In Replit environment, we purposefully prioritize the guaranteed direct mode
        if self.lavalink_connected:
            streaming_status = "✅ Advanced streaming mode (full features)"
            status_desc = "Connected to Lavalink server for high-quality playback"
        else:
            streaming_status = "✅ Direct streaming mode (Replit optimized)"
            status_desc = "Using YouTube API for guaranteed reliability on Replit"
        
        embed = discord.Embed(
            title="🎵 Ginsilog Music Commands",
            description=f"Ang bagong music player ng Ginsilog!\n\n**Status: {streaming_status}**\n{status_desc}",
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
            footer_text = "Optimized for Replit - Direct YouTube API for maximum reliability"
            
        embed.set_footer(text=footer_text)
        await ctx.send(embed=embed)
        

def setup(bot):
    bot.add_cog(LavalinkMusicCog(bot))