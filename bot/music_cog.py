import discord
from discord.ext import commands
import asyncio
import re
import os
import datetime
import random
import logging
from urllib.parse import urlparse, parse_qs
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp
from pytube import YouTube, Search, Playlist
import json

# Import from bot directory
from bot.config import Config
from bot.database import get_connection

class MusicQueue:
    """A queue system for music playback"""
    def __init__(self):
        self.queue = []
        self.current = None
        self.is_playing = False
        self.loop = False
        self.skip_votes = set()
    
    def add(self, item):
        """Add item to queue"""
        self.queue.append(item)
    
    def next(self):
        """Get next item from queue"""
        if not self.queue:
            self.current = None
            return None
        
        self.current = self.queue.pop(0)
        return self.current
    
    def clear(self):
        """Clear the queue"""
        self.queue = []
        self.current = None
        self.skip_votes = set()
    
    def is_empty(self):
        """Check if queue is empty"""
        return len(self.queue) == 0
    
    def get_queue(self):
        """Get all items in queue"""
        return self.queue
    
    def add_skip_vote(self, user_id):
        """Add a skip vote"""
        self.skip_votes.add(user_id)
        return len(self.skip_votes)

    def clear_skip_votes(self):
        """Clear skip votes"""
        self.skip_votes.clear()
        
    def get_queue_length(self):
        """Get total queue length including current song"""
        return len(self.queue) + (1 if self.current else 0)
    
    def remove_song(self, index):
        """Remove a song from the queue by index"""
        if 0 <= index < len(self.queue):
            return self.queue.pop(index)
        return None
    
    def shuffle(self):
        """Shuffle the queue"""
        random.shuffle(self.queue)

class MusicCog(commands.Cog):
    """Music commands cog for Ginsilog Discord Bot with aggressively rude Tagalog flair"""
    
    def __init__(self, bot):
        self.bot = bot
        
        # Create temp directory if it doesn't exist
        self.temp_dir = "temp_music"
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Dictionary to store voice clients and queues per guild
        self.guild_music_data = {}
        
        # Track voice inactivity timers
        self.voice_inactivity_timers = {}
        
        # Initialize Spotify client if credentials are available
        spotify_client_id = os.getenv('SPOTIFY_CLIENT_ID')
        spotify_client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        
        self.spotify = None
        if spotify_client_id and spotify_client_secret:
            self.spotify = spotipy.Spotify(
                client_credentials_manager=SpotifyClientCredentials(
                    client_id=spotify_client_id,
                    client_secret=spotify_client_secret
                )
            )
        
        # YT-DLP options
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'extractaudio': True,
            'audioformat': 'mp3',
            'outtmpl': f'{self.temp_dir}/%(id)s.%(ext)s',
            'restrictfilenames': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'quiet': True,
            'no_warnings': True,
            'default_search': 'auto',
            'source_address': '0.0.0.0',
        }
        
        # Common Filipino insults for music playback
        self.filipino_insults = [
            "Tangina mo!",
            "Putangina!",
            "Gago!",
            "Bobo!",
            "Inutil!",
            "Ulol!",
            "Hayop ka!",
            "Tanga!",
            "Siraulo!",
            "Hayup na yan!",
            "PAKSHET!",
            "LECHE!",
            "KUPAL!",
            "BWISET!"
        ]
        
    def get_guild_data(self, guild_id):
        """Get or create guild music data"""
        if guild_id not in self.guild_music_data:
            self.guild_music_data[guild_id] = {
                'queue': MusicQueue(),
                'volume': 0.5,  # Default volume (0.5 = 50%)
                'now_playing_message': None
            }
        return self.guild_music_data[guild_id]

    async def cog_load(self):
        """Initialize music systems"""
        print("🎵 Music Cog initializing with Ginsilog theme...")
    
    async def cog_unload(self):
        """Clean up when cog is unloaded"""
        for guild_id in list(self.guild_music_data.keys()):
            guild = self.bot.get_guild(guild_id)
            if guild and guild.voice_client:
                await guild.voice_client.disconnect()
                
        # Clean up temp files
        for file in os.listdir(self.temp_dir):
            try:
                os.remove(os.path.join(self.temp_dir, file))
            except Exception as e:
                print(f"Error cleaning up file: {e}")
    
    def start_inactivity_timer(self, guild_id, error=None):
        """Start timer to disconnect after period of inactivity"""
        # Cancel any existing timer
        if guild_id in self.voice_inactivity_timers:
            self.voice_inactivity_timers[guild_id].cancel()
        
        # Define auto-disconnect task
        async def auto_disconnect_task():
            await asyncio.sleep(300)  # 5 minutes
            guild = self.bot.get_guild(guild_id)
            if guild and guild.voice_client and not guild.voice_client.is_playing():
                await guild.voice_client.disconnect()
                print(f"Automatically disconnected from voice in guild {guild_id} due to inactivity")
                
                # Send sassy message in the last used channel
                for channel in guild.text_channels:
                    try:
                        await channel.send(f"**{random.choice(self.filipino_insults)}** Umalis ako sa VC kasi walang gumagamit! Parang ikaw lang yan, walang gumagamit. 🖕")
                        break
                    except:
                        continue
        
        # Start a new timer
        self.voice_inactivity_timers[guild_id] = asyncio.create_task(auto_disconnect_task())
    
    def extract_video_id(self, url):
        """Extract video ID from a YouTube URL"""
        # Regular YouTube URLs
        if "youtube.com/watch" in url:
            parsed_url = urlparse(url)
            return parse_qs(parsed_url.query).get('v', [None])[0]
        # Shortened YouTube URLs
        elif "youtu.be/" in url:
            return url.split("youtu.be/")[1].split("?")[0]
        return None
    
    def is_spotify_url(self, url):
        """Check if a URL is a Spotify URL"""
        return "spotify.com" in url
    
    def is_youtube_url(self, url):
        """Check if a URL is a YouTube URL"""
        return "youtube.com" in url or "youtu.be" in url
    
    def is_youtube_playlist(self, url):
        """Check if a URL is a YouTube playlist"""
        return "youtube.com/playlist" in url or ("youtube.com" in url and "list=" in url)
    
    def is_spotify_playlist(self, url):
        """Check if a URL is a Spotify playlist"""
        return "spotify.com/playlist" in url
    
    def is_spotify_track(self, url):
        """Check if a URL is a Spotify track"""
        return "spotify.com/track" in url
    
    def is_spotify_album(self, url):
        """Check if a URL is a Spotify album"""
        return "spotify.com/album" in url
    
    async def get_youtube_info(self, url_or_search):
        """Get info about a YouTube video or search query"""
        if self.is_youtube_url(url_or_search):
            try:
                with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                    info = ydl.extract_info(url_or_search, download=False)
                    if info:
                        return {
                            'url': info['webpage_url'],
                            'title': info['title'],
                            'duration': info['duration'],
                            'thumbnail': info.get('thumbnail'),
                            'uploader': info.get('uploader'),
                            'source': 'youtube'
                        }
            except Exception as e:
                print(f"Error getting YouTube info: {e}")
                return None
        else:
            # Perform a YouTube search
            try:
                search_results = Search(url_or_search).results
                if search_results:
                    video = search_results[0]
                    return {
                        'url': f"https://www.youtube.com/watch?v={video.video_id}",
                        'title': video.title,
                        'duration': video.length,
                        'thumbnail': video.thumbnail_url,
                        'uploader': video.author,
                        'source': 'youtube'
                    }
            except Exception as e:
                print(f"Error searching YouTube: {e}")
                return None
        return None
    
    async def get_youtube_playlist(self, url):
        """Get info about a YouTube playlist"""
        try:
            playlist = Playlist(url)
            videos = []
            
            for video_url in playlist.video_urls[:25]:  # Limit to 25 videos to avoid rate limiting
                try:
                    with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                        info = ydl.extract_info(video_url, download=False)
                        if info:
                            videos.append({
                                'url': info['webpage_url'],
                                'title': info['title'],
                                'duration': info['duration'],
                                'thumbnail': info.get('thumbnail'),
                                'uploader': info.get('uploader'),
                                'source': 'youtube'
                            })
                except Exception as e:
                    print(f"Error getting playlist video info: {e}")
                    continue
                    
            return {
                'title': playlist.title,
                'videos': videos,
                'source': 'youtube_playlist'
            }
        except Exception as e:
            print(f"Error getting YouTube playlist: {e}")
            return None
    
    async def get_spotify_track_info(self, url):
        """Get info about a Spotify track"""
        if not self.spotify:
            return None
            
        try:
            # Extract track ID from URL
            track_id = url.split('/')[-1].split('?')[0]
            track = self.spotify.track(track_id)
            
            # Search for the track on YouTube
            search_query = f"{track['name']} {' '.join([artist['name'] for artist in track['artists']])}"
            youtube_info = await self.get_youtube_info(search_query)
            
            if youtube_info:
                return {
                    'url': youtube_info['url'],
                    'title': f"{track['name']} - {', '.join([artist['name'] for artist in track['artists']])}",
                    'duration': youtube_info['duration'],
                    'thumbnail': track['album']['images'][0]['url'] if track['album']['images'] else youtube_info['thumbnail'],
                    'uploader': track['artists'][0]['name'],
                    'source': 'spotify'
                }
        except Exception as e:
            print(f"Error getting Spotify track: {e}")
            return None
        return None
    
    async def get_spotify_playlist(self, url):
        """Get info about a Spotify playlist"""
        if not self.spotify:
            return None
            
        try:
            # Extract playlist ID from URL
            playlist_id = url.split('/')[-1].split('?')[0]
            
            playlist = self.spotify.playlist(playlist_id)
            tracks = playlist['tracks']['items']
            
            videos = []
            for track_item in tracks[:25]:  # Limit to 25 tracks to avoid rate limiting
                track = track_item['track']
                search_query = f"{track['name']} {' '.join([artist['name'] for artist in track['artists']])}"
                youtube_info = await self.get_youtube_info(search_query)
                
                if youtube_info:
                    videos.append({
                        'url': youtube_info['url'],
                        'title': f"{track['name']} - {', '.join([artist['name'] for artist in track['artists']])}",
                        'duration': youtube_info['duration'],
                        'thumbnail': track['album']['images'][0]['url'] if track['album']['images'] else youtube_info['thumbnail'],
                        'uploader': track['artists'][0]['name'],
                        'source': 'spotify'
                    })
            
            return {
                'title': playlist['name'],
                'videos': videos,
                'source': 'spotify_playlist'
            }
        except Exception as e:
            print(f"Error getting Spotify playlist: {e}")
            return None
        return None
    
    async def get_spotify_album(self, url):
        """Get info about a Spotify album"""
        if not self.spotify:
            return None
            
        try:
            # Extract album ID from URL
            album_id = url.split('/')[-1].split('?')[0]
            
            album = self.spotify.album(album_id)
            tracks = album['tracks']['items']
            
            videos = []
            for track in tracks[:25]:  # Limit to 25 tracks to avoid rate limiting
                search_query = f"{track['name']} {' '.join([artist['name'] for artist in track['artists']])}"
                youtube_info = await self.get_youtube_info(search_query)
                
                if youtube_info:
                    videos.append({
                        'url': youtube_info['url'],
                        'title': f"{track['name']} - {', '.join([artist['name'] for artist in track['artists']])}",
                        'duration': youtube_info['duration'],
                        'thumbnail': album['images'][0]['url'] if album['images'] else youtube_info['thumbnail'],
                        'uploader': track['artists'][0]['name'],
                        'source': 'spotify'
                    })
            
            return {
                'title': album['name'],
                'videos': videos,
                'source': 'spotify_album'
            }
        except Exception as e:
            print(f"Error getting Spotify album: {e}")
            return None
        return None
    
    async def _ensure_voice_connection(self, voice_channel, text_channel):
        """Ensure bot is connected to voice channel"""
        if not voice_channel:
            await text_channel.send("**TANGINA MO!** Kailangan mo muna sumali sa isang voice channel! Bobo amputa.")
            return None
            
        guild = voice_channel.guild
        
        # Check if we're already connected to another channel in this guild
        if guild.voice_client:
            if guild.voice_client.channel.id != voice_channel.id:
                await guild.voice_client.move_to(voice_channel)
                await text_channel.send(f"✅ Lumipat ako sa **{voice_channel.name}** tangina pabago-bago ka kasi!")
            return guild.voice_client
        else:
            # Connect to the voice channel
            try:
                voice_client = await voice_channel.connect()
                await text_channel.send(f"✅ Sumali ako sa **{voice_channel.name}**. Punyeta! Anong kakantahin ko ha?")
                return voice_client
            except discord.ClientException as e:
                await text_channel.send(f"**ERROR:** Hindi ako makasali sa voice channel. Tangina! {str(e)}")
                return None
    
    async def play_song(self, guild, text_channel):
        """Play the next song in the queue"""
        guild_data = self.get_guild_data(guild.id)
        queue = guild_data['queue']
        
        if queue.is_empty() and not queue.current:
            await text_channel.send("**DIYOS KO PO!** Wala nang kanta sa queue! Maglagay ka muna ng kanta, GAGO!")
            self.start_inactivity_timer(guild.id)
            return
        
        # Get the next song if there's no current song
        if not queue.current:
            queue.current = queue.next()
            if not queue.current:
                await text_channel.send("**WEH?** Walang kanta? Wag kang mag-alala, makakahanap din tayo ng kanta para sayo.")
                self.start_inactivity_timer(guild.id)
                return
        
        # Reset skip votes
        queue.clear_skip_votes()
        
        # Download the song
        song = queue.current
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(song['url'], download=True)
                file_path = ydl.prepare_filename(info)
                
                # Fix file extension if needed
                base, _ = os.path.splitext(file_path)
                for ext in ['.mp3', '.webm', '.m4a']:
                    if os.path.exists(f"{base}{ext}"):
                        file_path = f"{base}{ext}"
                        break
        except Exception as e:
            await text_channel.send(f"**PUTANGINA!** Hindi ma-download yung kanta: {str(e)}")
            queue.current = None
            await self.play_song(guild, text_channel)
            return
        
        # Create the audio source
        audio_source = discord.FFmpegPCMAudio(file_path)
        
        # Apply volume transformation
        audio_source = discord.PCMVolumeTransformer(audio_source, volume=guild_data['volume'])
        
        # Define what to do after the song ends
        def after_playing(error):
            if error:
                print(f"Player error: {error}")
            
            # Delete the audio file
            try:
                os.remove(file_path)
            except:
                pass
            
            # Set up the next song
            asyncio.run_coroutine_threadsafe(self.play_next(guild, text_channel), self.bot.loop)
        
        # Play the song
        if guild.voice_client:
            guild.voice_client.play(audio_source, after=after_playing)
            
            # Send a now playing message with the song info
            embed = discord.Embed(
                title="🎵 **TUMUTUGTOG NGAYON**",
                description=f"**{song['title']}**",
                color=Config.EMBED_COLOR_PRIMARY
            )
            embed.add_field(name="Uploader", value=song['uploader'])
            embed.add_field(name="Duración", value=str(datetime.timedelta(seconds=song['duration'])))
            
            if song['thumbnail']:
                embed.set_thumbnail(url=song['thumbnail'])
                
            embed.set_footer(text=f"Source: {song['source'].capitalize()} | Requested by {song['requester']}")
            
            # Delete previous now playing message
            if guild_data['now_playing_message']:
                try:
                    await guild_data['now_playing_message'].delete()
                except:
                    pass
                    
            guild_data['now_playing_message'] = await text_channel.send(embed=embed)
    
    async def play_next(self, guild, text_channel):
        """Play the next song in the queue"""
        guild_data = self.get_guild_data(guild.id)
        queue = guild_data['queue']
        
        # If loop is enabled, re-add the current song to the end of queue
        if queue.loop and queue.current:
            queue.add(queue.current)
        
        # Set current to None to trigger getting the next song
        queue.current = None
        
        # Play the next song
        await self.play_song(guild, text_channel)
    
    @commands.command(name="join", aliases=["j", "summon"])
    async def join(self, ctx):
        """Join a voice channel"""
        voice_channel = ctx.author.voice.channel if ctx.author.voice else None
        if not voice_channel:
            return await ctx.send("**TANGINA MO!** Kailangan mo muna sumali sa isang voice channel! Bobo amputa.")
            
        await self._ensure_voice_connection(voice_channel, ctx.channel)
    
    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx, *, query: str = None):
        """Play music from YouTube or Spotify"""
        # Check if the user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGINA MO!** Kailangan mo muna sumali sa isang voice channel! Bobo amputa.")
        
        # Check if query is provided
        if not query:
            return await ctx.send("**GAGO!** Ano gusto mong patugtugin ko? Hangin? Magbigay ka ng link o pangalan ng kanta!")
        
        # Get the voice client
        voice_client = await self._ensure_voice_connection(ctx.author.voice.channel, ctx.channel)
        if not voice_client:
            return
        
        # Check if it's a playlist
        if self.is_youtube_playlist(query):
            # Process YouTube playlist
            await ctx.send(f"🔍 Hinahanap ang YouTube playlist... **TANGINA MAGHINTAY KA**!")
            playlist_info = await self.get_youtube_playlist(query)
            
            if not playlist_info:
                return await ctx.send("**PUNYETA!** Hindi ko mahanap yang playlist na yan!")
            
            # Add all songs to the queue
            guild_data = self.get_guild_data(ctx.guild.id)
            queue = guild_data['queue']
            
            added_count = 0
            for video in playlist_info['videos']:
                video['requester'] = ctx.author.display_name
                queue.add(video)
                added_count += 1
            
            await ctx.send(f"**✅ AYOS PUTA!** Nag-add ako ng **{added_count}** kanta mula sa playlist **{playlist_info['title']}**")
            
            # Start playing if not already playing
            if not voice_client.is_playing():
                await self.play_song(ctx.guild, ctx.channel)
                
        elif self.is_spotify_playlist(query):
            # Process Spotify playlist
            if not self.spotify:
                return await ctx.send("**PUTANGINA!** Hindi naka-set-up ang Spotify integration. Lagyan mo muna ng Spotify API key, GAGO!")
            
            await ctx.send(f"🔍 Hinahanap ang Spotify playlist... **TANGINA MAGHINTAY KA**!")
            playlist_info = await self.get_spotify_playlist(query)
            
            if not playlist_info:
                return await ctx.send("**PUNYETA!** Hindi ko mahanap yang playlist na yan!")
            
            # Add all songs to the queue
            guild_data = self.get_guild_data(ctx.guild.id)
            queue = guild_data['queue']
            
            added_count = 0
            for video in playlist_info['videos']:
                video['requester'] = ctx.author.display_name
                queue.add(video)
                added_count += 1
            
            await ctx.send(f"**✅ AYOS PUTA!** Nag-add ako ng **{added_count}** kanta mula sa Spotify playlist **{playlist_info['title']}**")
            
            # Start playing if not already playing
            if not voice_client.is_playing():
                await self.play_song(ctx.guild, ctx.channel)
                
        elif self.is_spotify_album(query):
            # Process Spotify album
            if not self.spotify:
                return await ctx.send("**PUTANGINA!** Hindi naka-set-up ang Spotify integration. Lagyan mo muna ng Spotify API key, GAGO!")
            
            await ctx.send(f"🔍 Hinahanap ang Spotify album... **TANGINA MAGHINTAY KA**!")
            album_info = await self.get_spotify_album(query)
            
            if not album_info:
                return await ctx.send("**PUNYETA!** Hindi ko mahanap yang album na yan!")
            
            # Add all songs to the queue
            guild_data = self.get_guild_data(ctx.guild.id)
            queue = guild_data['queue']
            
            added_count = 0
            for video in album_info['videos']:
                video['requester'] = ctx.author.display_name
                queue.add(video)
                added_count += 1
            
            await ctx.send(f"**✅ AYOS PUTA!** Nag-add ako ng **{added_count}** kanta mula sa Spotify album **{album_info['title']}**")
            
            # Start playing if not already playing
            if not voice_client.is_playing():
                await self.play_song(ctx.guild, ctx.channel)
                
        elif self.is_spotify_track(query):
            # Process Spotify track
            if not self.spotify:
                return await ctx.send("**PUTANGINA!** Hindi naka-set-up ang Spotify integration. Lagyan mo muna ng Spotify API key, GAGO!")
            
            await ctx.send(f"🔍 Hinahanap ang Spotify track... **TANGINA MAGHINTAY KA**!")
            track_info = await self.get_spotify_track_info(query)
            
            if not track_info:
                return await ctx.send("**PUNYETA!** Hindi ko mahanap yang kanta na yan!")
            
            # Add song to the queue
            guild_data = self.get_guild_data(ctx.guild.id)
            queue = guild_data['queue']
            
            track_info['requester'] = ctx.author.display_name
            queue.add(track_info)
            
            await ctx.send(f"**✅ AYOS PUTA!** Nag-add ako ng **{track_info['title']}** sa queue")
            
            # Start playing if not already playing
            if not voice_client.is_playing():
                await self.play_song(ctx.guild, ctx.channel)
                
        else:
            # Process single song (YouTube or search)
            await ctx.send(f"🔍 Hinahanap ang **{query}**... **TANGINA MAGHINTAY KA**!")
            song_info = await self.get_youtube_info(query)
            
            if not song_info:
                return await ctx.send("**PUNYETA!** Hindi ko mahanap yang kanta na yan!")
            
            # Add song to the queue
            guild_data = self.get_guild_data(ctx.guild.id)
            queue = guild_data['queue']
            
            song_info['requester'] = ctx.author.display_name
            queue.add(song_info)
            
            await ctx.send(f"**✅ AYOS PUTA!** Nag-add ako ng **{song_info['title']}** sa queue")
            
            # Start playing if not already playing
            if not voice_client.is_playing():
                await self.play_song(ctx.guild, ctx.channel)
    
    @commands.command(name="pause", aliases=["pa"])
    async def pause(self, ctx):
        """Pause the currently playing song"""
        if not ctx.guild.voice_client or not ctx.guild.voice_client.is_playing():
            return await ctx.send("**ULOL!** Wala naman akong pinapatugtog! Pano ko ito ipa-pause?")
        
        # Check if user is in the same channel
        if not ctx.author.voice or ctx.author.voice.channel.id != ctx.guild.voice_client.channel.id:
            return await ctx.send("**TANGA!** Kailangan mo muna sumali sa voice channel ko! Bobo amputa.")
        
        ctx.guild.voice_client.pause()
        await ctx.send(f"⏸️ **{random.choice(self.filipino_insults)}** Na-pause ang kanta. Mag-resume ka na lang kung gusto mo buksan ulit.")
    
    @commands.command(name="resume", aliases=["r", "res"])
    async def resume(self, ctx):
        """Resume the currently paused song"""
        if not ctx.guild.voice_client:
            return await ctx.send("**GAGO!** Wala ako sa voice channel. Pano ko ito i-reresume ha?")
        
        if not ctx.author.voice or ctx.author.voice.channel.id != ctx.guild.voice_client.channel.id:
            return await ctx.send("**TANGA!** Kailangan mo muna sumali sa voice channel ko! Bobo amputa.")
        
        if ctx.guild.voice_client.is_playing():
            return await ctx.send("**BULAG BA MATA MO?** Hindi naman naka-pause eh! Ano resume-resume ka pa dyan!")
        
        ctx.guild.voice_client.resume()
        await ctx.send(f"▶️ **{random.choice(self.filipino_insults)}** In-resume ko na yung kanta. Masaya ka na?")
    
    @commands.command(name="skip", aliases=["s", "next"])
    async def skip(self, ctx):
        """Skip the currently playing song"""
        if not ctx.guild.voice_client or not ctx.guild.voice_client.is_playing():
            return await ctx.send("**ULOL!** Wala naman akong pinapatugtog! Pano ko ito isi-skip?")
        
        if not ctx.author.voice or ctx.author.voice.channel.id != ctx.guild.voice_client.channel.id:
            return await ctx.send("**TANGA!** Kailangan mo muna sumali sa voice channel ko! Bobo amputa.")
        
        # Get guild data
        guild_data = self.get_guild_data(ctx.guild.id)
        queue = guild_data['queue']
        
        # Count the number of users in the voice channel (excluding bots)
        voice_members = len([m for m in ctx.guild.voice_client.channel.members if not m.bot])
        votes_needed = max(2, voice_members // 2)  # At least 2 votes or half of the members
        
        # Admin or song requester can skip immediately
        if ctx.author.guild_permissions.manage_guild or (queue.current and queue.current.get('requester') == ctx.author.display_name):
            ctx.guild.voice_client.stop()
            return await ctx.send(f"⏭️ **{random.choice(self.filipino_insults)}** Sineskip ko na ang kanta dahil ikaw ang admin o requester.")
        
        # Add vote and check if we have enough
        votes = queue.add_skip_vote(ctx.author.id)
        
        if votes >= votes_needed:
            ctx.guild.voice_client.stop()
            await ctx.send(f"⏭️ **{random.choice(self.filipino_insults)}** Sineskip ko na ang kanta dahil marami nang gusto i-skip ito.")
        else:
            await ctx.send(f"🗳️ **{ctx.author.display_name}** nag-vote para i-skip. **{votes}/{votes_needed}** votes needed.")
    
    @commands.command(name="forceskip", aliases=["fs"])
    @commands.has_permissions(manage_guild=True)
    async def forceskip(self, ctx):
        """Force skip the currently playing song (admin only)"""
        if not ctx.guild.voice_client or not ctx.guild.voice_client.is_playing():
            return await ctx.send("**ULOL!** Wala naman akong pinapatugtog! Pano ko ito isi-skip?")
        
        ctx.guild.voice_client.stop()
        await ctx.send(f"⏭️ **{random.choice(self.filipino_insults)}** Admin ka nga pala, kaya sineskip ko na ang kanta.")
    
    @commands.command(name="stop", aliases=["st", "clearq"])
    async def stop(self, ctx):
        """Stop playing music and clear the queue"""
        if not ctx.guild.voice_client:
            return await ctx.send("**GAGO!** Wala ako sa voice channel. Pano ko ito isi-stop ha?")
        
        if not ctx.author.voice or ctx.author.voice.channel.id != ctx.guild.voice_client.channel.id:
            return await ctx.send("**TANGA!** Kailangan mo muna sumali sa voice channel ko! Bobo amputa.")
        
        # Get guild data
        guild_data = self.get_guild_data(ctx.guild.id)
        queue = guild_data['queue']
        
        # Clear the queue
        queue.clear()
        
        # Stop playing
        if ctx.guild.voice_client.is_playing():
            ctx.guild.voice_client.stop()
        
        await ctx.send(f"⏹️ **{random.choice(self.filipino_insults)}** Stopped the music and cleared the queue. Happy ka na? Wala ng tugtugan!")
    
    @commands.command(name="volume", aliases=["vol", "v"])
    async def volume(self, ctx, volume: int = None):
        """Change the player volume"""
        if not ctx.guild.voice_client:
            return await ctx.send("**GAGO!** Wala ako sa voice channel. Pano ko ibabago ang volume ha?")
        
        if not ctx.author.voice or ctx.author.voice.channel.id != ctx.guild.voice_client.channel.id:
            return await ctx.send("**TANGA!** Kailangan mo muna sumali sa voice channel ko! Bobo amputa.")
        
        # Get guild data
        guild_data = self.get_guild_data(ctx.guild.id)
        
        # If no volume provided, display current volume
        if volume is None:
            current_volume = int(guild_data['volume'] * 100)
            return await ctx.send(f"🔊 Current volume: **{current_volume}%**")
        
        # Validate volume range
        if not 0 <= volume <= 100:
            return await ctx.send("**TANGA!** Volume should be between 0 and 100! Wag kang plastic!")
        
        # Set the new volume
        guild_data['volume'] = volume / 100
        
        # Update current player volume if playing
        if ctx.guild.voice_client.source:
            ctx.guild.voice_client.source.volume = guild_data['volume']
        
        await ctx.send(f"🔊 **{random.choice(self.filipino_insults)}** Set the volume to **{volume}%**")
    
    @commands.command(name="queue", aliases=["q", "playlist"])
    async def queue(self, ctx, page: int = 1):
        """Show the music queue"""
        # Get guild data
        guild_data = self.get_guild_data(ctx.guild.id)
        queue = guild_data['queue']
        
        if queue.is_empty() and not queue.current:
            return await ctx.send("**PUTANGINA!** Wala pa sa queue eh! Magdagdag ka muna ng kanta, GAGO!")
        
        # Calculate total pages (10 songs per page)
        total_songs = len(queue.queue) + (1 if queue.current else 0)
        songs_per_page = 10
        total_pages = (total_songs + songs_per_page - 1) // songs_per_page
        
        # Validate page number
        if page < 1 or page > total_pages:
            return await ctx.send(f"**TANGA!** Page number should be between 1 and {total_pages}! Diyos ko po!")
        
        # Create embed for queue
        embed = discord.Embed(
            title="🎵 **GINSILOG MUSIC QUEUE** 🎵",
            description=f"Total songs: **{total_songs}**",
            color=Config.EMBED_COLOR_PRIMARY
        )
        
        # Add currently playing song
        if queue.current:
            duration = str(datetime.timedelta(seconds=queue.current['duration']))
            embed.add_field(
                name="📀 Currently Playing:",
                value=f"**{queue.current['title']}** - {duration} [Requested by {queue.current['requester']}]",
                inline=False
            )
        
        # Add songs from the queue
        start_idx = (page - 1) * songs_per_page
        end_idx = min(start_idx + songs_per_page, len(queue.queue))
        
        queue_text = ""
        for i in range(start_idx, end_idx):
            song = queue.queue[i]
            duration = str(datetime.timedelta(seconds=song['duration']))
            queue_text += f"**{i+1}.** {song['title']} - {duration} [Requested by {song['requester']}]\n"
        
        if queue_text:
            embed.add_field(name="🎶 Up Next:", value=queue_text, inline=False)
            
        # Add page info
        embed.set_footer(text=f"Page {page}/{total_pages} | Use g!queue <page> to view other pages")
        
        await ctx.send(embed=embed)
    
    @commands.command(name="nowplaying", aliases=["np", "current"])
    async def nowplaying(self, ctx):
        """Show information about the currently playing song"""
        # Get guild data
        guild_data = self.get_guild_data(ctx.guild.id)
        queue = guild_data['queue']
        
        if not queue.current:
            return await ctx.send("**GAGO!** Wala naman akong pinapatugtog ngayon! Bulag ka ba?")
        
        song = queue.current
        
        # Create embed for current song
        embed = discord.Embed(
            title="🎵 **TUMUTUGTOG NGAYON**",
            description=f"**{song['title']}**",
            color=Config.EMBED_COLOR_PRIMARY
        )
        
        embed.add_field(name="Uploader", value=song['uploader'])
        embed.add_field(name="Duración", value=str(datetime.timedelta(seconds=song['duration'])))
        embed.add_field(name="URL", value=f"[Click Here]({song['url']})", inline=False)
        
        if song['thumbnail']:
            embed.set_thumbnail(url=song['thumbnail'])
            
        embed.set_footer(text=f"Source: {song['source'].capitalize()} | Requested by {song['requester']}")
        
        await ctx.send(embed=embed)
    
    @commands.command(name="loop", aliases=["repeat"])
    async def loop(self, ctx):
        """Toggle loop mode for the queue"""
        if not ctx.guild.voice_client:
            return await ctx.send("**GAGO!** Wala ako sa voice channel. Pano ko ilo-loop 'to ha?")
        
        if not ctx.author.voice or ctx.author.voice.channel.id != ctx.guild.voice_client.channel.id:
            return await ctx.send("**TANGA!** Kailangan mo muna sumali sa voice channel ko! Bobo amputa.")
        
        # Get guild data
        guild_data = self.get_guild_data(ctx.guild.id)
        queue = guild_data['queue']
        
        # Toggle loop mode
        queue.loop = not queue.loop
        
        if queue.loop:
            await ctx.send(f"🔄 **{random.choice(self.filipino_insults)}** Naka-loop na ngayon ang queue. Paulit-ulit na ang kanta! Masokista ka ba?")
        else:
            await ctx.send(f"➡️ **{random.choice(self.filipino_insults)}** Hindi na naka-loop ang queue. Aba, umayos ka rin pala.")
    
    @commands.command(name="remove", aliases=["rm"])
    async def remove(self, ctx, index: int):
        """Remove a song from the queue by its index"""
        if not ctx.guild.voice_client:
            return await ctx.send("**GAGO!** Wala ako sa voice channel. Pano ko aalisin ang kanta ha?")
        
        if not ctx.author.voice or ctx.author.voice.channel.id != ctx.guild.voice_client.channel.id:
            return await ctx.send("**TANGA!** Kailangan mo muna sumali sa voice channel ko! Bobo amputa.")
        
        # Get guild data
        guild_data = self.get_guild_data(ctx.guild.id)
        queue = guild_data['queue']
        
        # Check if queue is empty
        if queue.is_empty():
            return await ctx.send("**ULOL!** Wala pang kanta sa queue! Ano aalisin mo?")
        
        # Adjust index (user sees 1-based, we use 0-based)
        index -= 1
        
        # Remove the song
        removed_song = queue.remove_song(index)
        
        if removed_song:
            await ctx.send(f"✅ **{removed_song['title']}** ay inalis sa queue. Ayaw mo na ba talaga pakinggan 'to?")
        else:
            await ctx.send(f"**TANGA!** Walang kanta sa index {index+1}. Magbilang ka nga ng maayos!")
    
    @commands.command(name="shuffle", aliases=["sh"])
    async def shuffle(self, ctx):
        """Shuffle the current queue"""
        if not ctx.guild.voice_client:
            return await ctx.send("**GAGO!** Wala ako sa voice channel. Pano ko i-shushuffle ang queue ha?")
        
        if not ctx.author.voice or ctx.author.voice.channel.id != ctx.guild.voice_client.channel.id:
            return await ctx.send("**TANGA!** Kailangan mo muna sumali sa voice channel ko! Bobo amputa.")
        
        # Get guild data
        guild_data = self.get_guild_data(ctx.guild.id)
        queue = guild_data['queue']
        
        # Check if queue is empty
        if queue.is_empty():
            return await ctx.send("**ULOL!** Wala pang kanta sa queue! Ano i-shushuffle mo?")
        
        # Shuffle the queue
        queue.shuffle()
        
        await ctx.send(f"🔀 **{random.choice(self.filipino_insults)}** Na-shuffle ko na ang queue. Pati buhay mo sana ma-shuffle din para magka-improvement naman!")
    
    @commands.command(name="leave", aliases=["dc", "disconnect"])
    async def leave(self, ctx):
        """Leave the voice channel"""
        if not ctx.guild.voice_client:
            return await ctx.send("**GAGO!** Hindi naman ako naka-connect sa kahit anong voice channel eh!")
        
        if not ctx.author.voice or ctx.author.voice.channel.id != ctx.guild.voice_client.channel.id:
            return await ctx.send("**TANGA!** Kailangan mo muna sumali sa voice channel ko! Bobo amputa.")
        
        # Get guild data
        guild_data = self.get_guild_data(ctx.guild.id)
        queue = guild_data['queue']
        
        # Clear the queue
        queue.clear()
        
        # Cancel the inactivity timer
        if ctx.guild.id in self.voice_inactivity_timers:
            self.voice_inactivity_timers[ctx.guild.id].cancel()
            del self.voice_inactivity_timers[ctx.guild.id]
        
        # Disconnect
        await ctx.guild.voice_client.disconnect()
        
        await ctx.send(f"👋 **{random.choice(self.filipino_insults)}** Umalis na ako sa voice channel. Nakaka-stress ka kausap eh!")
    
    @commands.command(name="search", aliases=["find"])
    async def search(self, ctx, *, query: str):
        """Search for songs on YouTube"""
        if not query:
            return await ctx.send("**TANGINA MO!** Ano ba hahanapin ko? Magbigay ka naman ng search term!")
        
        await ctx.send(f"🔍 Hinahanap ang **{query}**... **TANGINA MAGHINTAY KA**!")
        
        try:
            # Search for videos
            search_results = Search(query).results[:5]  # Get top 5 results
            
            if not search_results:
                return await ctx.send("**PUTANGINA!** Walang nahanap sa search mo! Baka typo yan!")
            
            # Create embed for search results
            embed = discord.Embed(
                title=f"🔍 Search Results for: {query}",
                description="Type the number to play a song, or 'cancel' to cancel.",
                color=Config.EMBED_COLOR_PRIMARY
            )
            
            for i, result in enumerate(search_results, 1):
                embed.add_field(
                    name=f"{i}. {result.title}",
                    value=f"Duration: {str(datetime.timedelta(seconds=result.length))}\nChannel: {result.author}",
                    inline=False
                )
            
            # Send the embed
            message = await ctx.send(embed=embed)
            
            # Wait for user response
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel and \
                       (m.content.isdigit() or m.content.lower() == 'cancel')
            
            try:
                response = await self.bot.wait_for('message', check=check, timeout=30.0)
                
                # If user wants to cancel
                if response.content.lower() == 'cancel':
                    return await ctx.send("**TALAGA?** Kala ko may gusto kang pakinggan! Nag-search pa ako!")
                
                # Get the selected video
                selected_index = int(response.content) - 1
                if 0 <= selected_index < len(search_results):
                    selected_video = search_results[selected_index]
                    
                    # Process like play command
                    await ctx.send(f"🎵 Playing: **{selected_video.title}**")
                    
                    # Prepare song info
                    song_info = {
                        'url': f"https://www.youtube.com/watch?v={selected_video.video_id}",
                        'title': selected_video.title,
                        'duration': selected_video.length,
                        'thumbnail': selected_video.thumbnail_url,
                        'uploader': selected_video.author,
                        'source': 'youtube',
                        'requester': ctx.author.display_name
                    }
                    
                    # Get voice client
                    voice_client = await self._ensure_voice_connection(ctx.author.voice.channel, ctx.channel)
                    if not voice_client:
                        return
                    
                    # Add song to queue
                    guild_data = self.get_guild_data(ctx.guild.id)
                    queue = guild_data['queue']
                    queue.add(song_info)
                    
                    # Start playing if not already playing
                    if not voice_client.is_playing():
                        await self.play_song(ctx.guild, ctx.channel)
                else:
                    await ctx.send("**GAGO!** Invalid number. Ang bobo mo talaga mag-bilang!")
            
            except asyncio.TimeoutError:
                await ctx.send("**PUTANG INA!** Ang tagal mo mag-isip! Cancelled search results.")
        
        except Exception as e:
            await ctx.send(f"**ERROR:** Failed to search for songs: {str(e)}")
    
def setup(bot):
    """Add cog to bot"""
    bot.add_cog(MusicCog(bot))