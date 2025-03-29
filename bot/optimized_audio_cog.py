import asyncio
import discord
import os
import re
import time
import random
import urllib.request
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from discord.ext import commands
from discord import FFmpegPCMAudio, PCMVolumeTransformer
from bot.custom_youtube import YouTubeUnblocker, SpotifyUnblocker

# Create temporary directories if they don't exist
os.makedirs("temp_music", exist_ok=True)


class MusicQueue:
    """Class to manage music queue for each guild"""
    
    def __init__(self):
        self.queue = []
        self.position = 0
        self.loop = False
        self.loop_queue = False
        self.current = None
        self.volume = 0.5
    
    def add(self, track):
        """Add a track to the queue"""
        self.queue.append(track)
    
    def next(self):
        """Get the next track in queue"""
        if not self.queue:
            return None
            
        if self.loop and self.current:
            # Stay on current track if loop is enabled
            return self.current
            
        if self.position >= len(self.queue):
            if self.loop_queue:
                # Start from beginning if loop queue is enabled
                self.position = 0
            else:
                return None
        
        self.current = self.queue[self.position]
        self.position += 1
        
        if not self.loop:
            # Only return the next track if not looping
            return self.current
        else:
            return self.current
    
    def clear(self):
        """Clear the queue"""
        self.queue = []
        self.position = 0
        self.current = None
    
    def skip(self):
        """Skip the current track"""
        self.loop = False  # Disable loop when skipping
        return self.next()
    
    def remove(self, index):
        """Remove a track from the queue"""
        if 0 <= index < len(self.queue):
            removed = self.queue.pop(index)
            
            # Adjust position if removed item was before current position
            if index < self.position:
                self.position -= 1
                
            return removed
        return None
    
    def current_queue(self):
        """Get the current queue as a list"""
        return self.queue[self.position-1:] if self.position > 0 else self.queue


class OptimizedMusicCog(commands.Cog):
    """Music commands using custom YouTube parser to bypass API restrictions"""
    
    def __init__(self, bot):
        self.bot = bot
        self.guild_queues = {}  # Dictionary to store music queues for each guild
        self.yt_parser = YouTubeUnblocker()
        
        # Initialize Spotify client with credentials
        try:
            spotify_credentials = SpotifyClientCredentials(
                client_id=os.getenv('SPOTIFY_CLIENT_ID'),
                client_secret=os.getenv('SPOTIFY_CLIENT_SECRET')
            )
            self.sp = spotipy.Spotify(client_credentials_manager=spotify_credentials)
            print("✅ Spotify API client initialized successfully!")
            self.spotify_enabled = True
        except Exception as e:
            print(f"⚠️ Error initializing Spotify client: {e}")
            self.spotify_enabled = False
            
        # Initialize custom Spotify parser as fallback
        self.spotify_parser = SpotifyUnblocker(self.yt_parser)
        
        # YT-DLP configuration
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'cookiefile': 'cookies.txt',  # Optional: use cookies to avoid some restrictions
            'extract_flat': True,
            'skip_download': True,
            'force_generic_extractor': False
        }
    
    def get_queue(self, guild_id):
        """Get or create a music queue for a guild"""
        if guild_id not in self.guild_queues:
            self.guild_queues[guild_id] = MusicQueue()
        return self.guild_queues[guild_id]
    
    async def join_voice_channel(self, ctx):
        """Join the user's voice channel"""
        voice_channel = ctx.author.voice.channel if ctx.author.voice else None
        
        if not voice_channel:
            await ctx.send("Kailangan mong sumali sa isang voice channel muna, tanga!")
            return None
        
        # Check if bot is already in a voice channel
        voice_client = ctx.guild.voice_client
        
        if voice_client:
            if voice_client.channel.id == voice_channel.id:
                return voice_client
            else:
                await voice_client.move_to(voice_channel)
                return voice_client
        else:
            voice_client = await voice_channel.connect()
            return voice_client
    
    async def download_audio(self, video_url, filename):
        """Download audio from a URL using yt-dlp"""
        try:
            # First approach: Use yt-dlp with best audio format
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': filename,
                'quiet': True,
                'no_warnings': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
                return True
        except Exception as e:
            print(f"Error downloading with yt-dlp: {e}")
            
            # Fallback: Try direct download using urllib
            try:
                # This is a simplified approach - real implementation would need more robust parsing
                # of the video's audio URL
                return False  # Direct download not implemented yet
            except Exception as e2:
                print(f"Error with fallback download: {e2}")
                return False
    
    def play_next(self, ctx):
        """Play the next track in the queue"""
        guild_id = ctx.guild.id
        queue = self.get_queue(guild_id)
        voice_client = ctx.guild.voice_client
        
        if not voice_client:
            return
        
        if voice_client.is_playing():
            voice_client.stop()
        
        # Get next track
        track = queue.next()
        
        if not track:
            asyncio.run_coroutine_threadsafe(
                ctx.send("✓ Queue empty. Leaving voice channel..."),
                self.bot.loop
            )
            asyncio.run_coroutine_threadsafe(voice_client.disconnect(), self.bot.loop)
            return
        
        # Generate a unique filename
        filename = f"temp_music/song_{guild_id}_{int(time.time())}.mp3"
        
        # Define the after function to play the next track
        def after_playing(error):
            if error:
                print(f"Player error: {error}")
            
            # Schedule the next track to play
            self.bot.loop.create_task(self._schedule_next(ctx))
        
        # Try to play the track
        try:
            success = asyncio.run_coroutine_threadsafe(
                self.download_audio(track['url'], filename), 
                self.bot.loop
            ).result()
            
            if success:
                audio_source = PCMVolumeTransformer(
                    FFmpegPCMAudio(filename),
                    volume=queue.volume
                )
                voice_client.play(audio_source, after=after_playing)
                
                # Send now playing message
                asyncio.run_coroutine_threadsafe(
                    ctx.send(f"🎵 Now playing: **{track['title']}**"),
                    self.bot.loop
                )
            else:
                # If download failed, try next song
                asyncio.run_coroutine_threadsafe(
                    ctx.send(f"❌ Failed to play: **{track['title']}**. Skipping..."),
                    self.bot.loop
                )
                self.play_next(ctx)
        except Exception as e:
            print(f"Error playing track: {e}")
            
            # Try to play next track
            self.play_next(ctx)
    
    async def _schedule_next(self, ctx):
        """Schedule the next track to play"""
        guild_id = ctx.guild.id
        queue = self.get_queue(guild_id)
        voice_client = ctx.guild.voice_client
        
        # Check if there are members in the voice channel
        if voice_client and voice_client.channel and len(voice_client.channel.members) <= 1:
            await ctx.send("✓ No one is listening. Leaving voice channel...")
            await voice_client.disconnect()
            return
        
        self.play_next(ctx)
    
    @commands.command(name="ytplay", aliases=["yp", "youtube"])
    async def ytplay(self, ctx, *, query: str = None):
        """Play a song from YouTube or Spotify using custom parser to bypass API blocks
        
        Usage:
        g!ytplay <YouTube URL or search query>
        g!ytplay <Spotify track URL>
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
            voice_client = await self.join_voice_channel(ctx)
            if not voice_client:
                return
            
            # Get the guild's queue
            queue = self.get_queue(ctx.guild.id)
            
            # Process the query
            spotify_pattern = r'open\.spotify\.com/(?:track|playlist)/([a-zA-Z0-9]+)'
            youtube_id = self.yt_parser.extract_video_id(query)
            spotify_match = re.search(spotify_pattern, query)
            
            # Check what type of query we have
            if youtube_id:
                # Direct YouTube URL
                video_info = self.yt_parser.get_video_info(youtube_id)
                if video_info:
                    queue.add(video_info)
                    await ctx.send(f"✓ Added to queue: **{video_info['title']}**")
                else:
                    await ctx.send("❌ Hindi ma-access ang YouTube video na yan!")
                    return
            elif spotify_match:
                # Spotify URL
                if 'track' in query:
                    # Single track
                    if self.spotify_enabled:
                        try:
                            # Extract track ID from URL
                            track_id = spotify_match.group(1)
                            # Get track info from Spotify API
                            spotify_track = self.sp.track(track_id)
                            
                            # Format artist names
                            artists = ", ".join([artist["name"] for artist in spotify_track["artists"]])
                            # Create a search query for YouTube
                            search_query = f"{spotify_track['name']} {artists}"
                            
                            await ctx.send(f"🔎 Searching for Spotify track: **{spotify_track['name']}** by **{artists}**")
                            
                            # Search YouTube for the track
                            results = self.yt_parser.search_videos(search_query, max_results=1)
                            
                            if results:
                                video = results[0]
                                # Add thumbnail from Spotify if available
                                if spotify_track["album"]["images"]:
                                    video["thumbnail"] = spotify_track["album"]["images"][0]["url"]
                                    
                                queue.add(video)
                                await ctx.send(f"✓ Added to queue (from Spotify): **{video['title']}**")
                            else:
                                await ctx.send(f"❌ Couldn't find a YouTube match for Spotify track: **{spotify_track['name']}**")
                                return
                        except Exception as e:
                            print(f"Error processing Spotify track: {e}")
                            # Fall back to the custom parser
                            await ctx.send("⚠️ Error with Spotify API, falling back to alternative method...")
                            track_info = self.spotify_parser.get_track_info(query)
                            if track_info:
                                queue.add(track_info)
                                await ctx.send(f"✓ Added to queue (from Spotify): **{track_info['title']}**")
                            else:
                                await ctx.send("❌ Hindi ma-access ang Spotify track na yan!")
                                return
                    else:
                        # Use fallback parser if Spotify API isn't available
                        track_info = self.spotify_parser.get_track_info(query)
                        if track_info:
                            queue.add(track_info)
                            await ctx.send(f"✓ Added to queue (from Spotify): **{track_info['title']}**")
                        else:
                            await ctx.send("❌ Hindi ma-access ang Spotify track na yan!")
                            return
                elif 'playlist' in query:
                    # Playlist
                    await ctx.send("⏳ Processing Spotify playlist... (ito'y maaaring tumagal ng ilang segundo)")
                    
                    if self.spotify_enabled:
                        try:
                            # Extract playlist ID from URL
                            playlist_id = spotify_match.group(1)
                            # Get playlist info from Spotify API
                            playlist = self.sp.playlist(playlist_id)
                            playlist_name = playlist["name"]
                            tracks = []
                            
                            # Process first 10 tracks (to avoid overloading)
                            count = 0
                            max_tracks = 10
                            
                            for item in playlist["tracks"]["items"]:
                                if count >= max_tracks:
                                    break
                                
                                track = item["track"]
                                if not track:
                                    continue
                                    
                                # Format artist names
                                artists = ", ".join([artist["name"] for artist in track["artists"]])
                                # Create search query for YouTube
                                search_query = f"{track['name']} {artists}"
                                
                                # Search YouTube
                                results = self.yt_parser.search_videos(search_query, max_results=1)
                                if results:
                                    video = results[0]
                                    # Add to queue
                                    queue.add(video)
                                    tracks.append(video)
                                    count += 1
                            
                            if tracks:
                                await ctx.send(f"✓ Added **{len(tracks)}** tracks from Spotify playlist: **{playlist_name}**")
                            else:
                                await ctx.send("❌ Couldn't find YouTube matches for any tracks in the playlist")
                                return
                                
                        except Exception as e:
                            print(f"Error processing Spotify playlist: {e}")
                            # Fall back to custom parser
                            await ctx.send("⚠️ Error with Spotify API, falling back to alternative method...")
                            playlist_info = self.spotify_parser.get_playlist_tracks(query, max_tracks=10)
                            
                            if playlist_info and playlist_info['tracks']:
                                for track in playlist_info['tracks']:
                                    queue.add(track)
                                
                                await ctx.send(f"✓ Added **{len(playlist_info['tracks'])}** tracks from Spotify playlist: **{playlist_info['title']}**")
                            else:
                                await ctx.send("❌ Hindi ma-access ang Spotify playlist na yan!")
                                return
                    else:
                        # Use fallback parser if Spotify API isn't available
                        playlist_info = self.spotify_parser.get_playlist_tracks(query, max_tracks=10)
                        
                        if playlist_info and playlist_info['tracks']:
                            for track in playlist_info['tracks']:
                                queue.add(track)
                            
                            await ctx.send(f"✓ Added **{len(playlist_info['tracks'])}** tracks from Spotify playlist: **{playlist_info['title']}**")
                        else:
                            await ctx.send("❌ Hindi ma-access ang Spotify playlist na yan!")
                            return
            else:
                # Search query for YouTube
                await ctx.send(f"🔎 Searching for: **{query}**")
                results = self.yt_parser.search_videos(query, max_results=1)
                
                if not results:
                    await ctx.send(f"❌ Walang nahanap na results para sa '{query}'")
                    return
                
                video = results[0]
                queue.add(video)
                await ctx.send(f"✓ Added to queue: **{video['title']}**")
            
            # Start playing if not already playing
            if not voice_client.is_playing():
                self.play_next(ctx)
    
    @commands.command(name="ytstop")
    async def ytstop(self, ctx):
        """Stop playing and clear the queue for the custom YouTube player"""
        voice_client = ctx.guild.voice_client
        
        if not voice_client or not voice_client.is_connected():
            await ctx.send("❌ Wala naman akong pinapatugtog!")
            return
        
        queue = self.get_queue(ctx.guild.id)
        queue.clear()
        
        if voice_client.is_playing():
            voice_client.stop()
        
        await ctx.send("✓ Inistop at ni-clear ang queue!")
    
    @commands.command(name="ytskip", aliases=["ys"])
    async def ytskip(self, ctx):
        """Skip the current song (YouTube parser player)"""
        voice_client = ctx.guild.voice_client
        
        if not voice_client or not voice_client.is_connected():
            await ctx.send("❌ Wala naman akong pinapatugtog!")
            return
        
        if not voice_client.is_playing():
            await ctx.send("❌ Wala naman akong pinapatugtog!")
            return
        
        voice_client.stop()
        await ctx.send("✓ Ni-skip ang kasalukuyang kanta!")
    
    @commands.command(name="ytqueue", aliases=["yq"])
    async def yt_queue(self, ctx):
        """Show the current YouTube player queue"""
        queue = self.get_queue(ctx.guild.id)
        current_queue = queue.current_queue()
        
        if not current_queue:
            await ctx.send("❌ Walang laman ang queue!")
            return
        
        # Create an embed for the queue
        embed = discord.Embed(
            title="🎵 Music Queue",
            color=0xFF5733
        )
        
        # Add current track
        if queue.current:
            embed.add_field(
                name="Now Playing",
                value=f"**{queue.current['title']}**",
                inline=False
            )
        
        # Add upcoming tracks
        queue_text = ""
        start_index = 0 if not queue.current else 1
        
        for i, track in enumerate(current_queue[start_index:], start=1):
            if i > 10:  # Limit to 10 tracks
                remaining = len(current_queue) - start_index - 10
                queue_text += f"\n*And {remaining} more...*"
                break
                
            queue_text += f"\n**{i}.** {track['title']}"
        
        if queue_text:
            embed.add_field(
                name="Up Next",
                value=queue_text,
                inline=False
            )
        
        # Add queue status
        embed.set_footer(text=f"Loop: {'✅' if queue.loop else '❌'} | Loop Queue: {'✅' if queue.loop_queue else '❌'} | Volume: {int(queue.volume * 100)}%")
        
        await ctx.send(embed=embed)
    
    @commands.command(name="ytvolume", aliases=["ytvol", "ytv"])
    async def ytvolume(self, ctx, volume: int = None):
        """Set the volume for YouTube player (0-100)"""
        voice_client = ctx.guild.voice_client
        queue = self.get_queue(ctx.guild.id)
        
        if volume is None:
            await ctx.send(f"✓ Current volume: **{int(queue.volume * 100)}%**")
            return
        
        if not 0 <= volume <= 100:
            await ctx.send("❌ Volume ay dapat nasa pagitan ng 0 at 100!")
            return
        
        queue.volume = volume / 100
        
        if voice_client and voice_client.source:
            voice_client.source.volume = queue.volume
        
        await ctx.send(f"✓ Volume set to **{volume}%**")
    
    @commands.command(name="ytloop", aliases=["ytl"])
    async def ytloop(self, ctx):
        """Toggle loop for the current YouTube player song"""
        queue = self.get_queue(ctx.guild.id)
        queue.loop = not queue.loop
        
        # Turn off loop queue if enabling loop
        if queue.loop:
            queue.loop_queue = False
        
        await ctx.send(f"✓ Loop: **{'Enabled' if queue.loop else 'Disabled'}**")
    
    @commands.command(name="ytloopqueue", aliases=["ytlq"])
    async def ytloop_queue(self, ctx):
        """Toggle loop for the entire YouTube player queue"""
        queue = self.get_queue(ctx.guild.id)
        queue.loop_queue = not queue.loop_queue
        
        # Turn off single loop if enabling loop queue
        if queue.loop_queue:
            queue.loop = False
        
        await ctx.send(f"✓ Loop Queue: **{'Enabled' if queue.loop_queue else 'Disabled'}**")
    
    @commands.command(name="ytclear")
    async def ytclear(self, ctx):
        """Clear the YouTube player music queue"""
        queue = self.get_queue(ctx.guild.id)
        old_size = len(queue.queue)
        queue.clear()
        
        await ctx.send(f"✓ Cleared **{old_size}** tracks from the queue!")
    
    @commands.command(name="ytremove", aliases=["ytrm"])
    async def ytremove(self, ctx, index: int):
        """Remove a song from the YouTube player queue by its index"""
        queue = self.get_queue(ctx.guild.id)
        
        # Adjust index to be 0-based
        index = index - 1
        
        removed = queue.remove(index)
        
        if removed:
            await ctx.send(f"✓ Removed from queue: **{removed['title']}**")
        else:
            await ctx.send("❌ Invalid index! Use g!queue to see the queue.")
    
    @commands.command(name="ytleave", aliases=["ytdisconnect", "ytdc"])
    async def ytleave(self, ctx):
        """YouTube player: Leave the voice channel"""
        voice_client = ctx.guild.voice_client
        
        if voice_client and voice_client.is_connected():
            await voice_client.disconnect()
            await ctx.send("✓ Disconnected from voice channel!")
        else:
            await ctx.send("❌ I'm not in a voice channel!")
    
    @commands.command(name="ytnowplaying", aliases=["ytnp"])
    async def yt_now_playing(self, ctx):
        """Show information about the currently playing song from YouTube player"""
        voice_client = ctx.guild.voice_client
        queue = self.get_queue(ctx.guild.id)
        
        if not voice_client or not voice_client.is_playing():
            await ctx.send("❌ Wala akong pinapatugtog ngayon!")
            return
        
        current = queue.current
        
        if not current:
            await ctx.send("❌ May problema sa pagkuha ng info ng kasalukuyang kanta!")
            return
        
        # Create an embed for the current track
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**{current['title']}**",
            color=0xFF5733
        )
        
        # Add thumbnail if available
        if 'thumbnail' in current:
            embed.set_thumbnail(url=current['thumbnail'])
        
        # Add duration if available
        if 'duration' in current and current['duration'] > 0:
            minutes, seconds = divmod(current['duration'], 60)
            embed.add_field(name="Duration", value=f"{minutes}:{seconds:02d}", inline=True)
        
        # Add source
        source_name = "YouTube" if current.get('source') == 'youtube' else "Unknown"
        embed.add_field(name="Source", value=source_name, inline=True)
        
        # Add uploader if available
        if 'uploader' in current:
            embed.add_field(name="Channel", value=current['uploader'], inline=True)
        
        # Add queue status
        embed.set_footer(text=f"Loop: {'✅' if queue.loop else '❌'} | Loop Queue: {'✅' if queue.loop_queue else '❌'} | Volume: {int(queue.volume * 100)}%")
        
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(OptimizedMusicCog(bot))