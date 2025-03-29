import discord
from discord.ext import commands
from gtts import gTTS
import io
import os
import asyncio
import time
import random
import shutil
import wavelink
from wavelink.tracks import Playable, YouTubeTrack
from wavelink.ext import spotify
from pydub import AudioSegment
from pydub.playback import play
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
    """Custom player class with queue functionality (Wavelink 3.x compatibility)"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.now_playing = None
        self.is_playing = False
        self.loop = False
        self.queue = wavelink.Queue()
        
    async def on_track_end(self, reason):
        """Called when track finishes, plays the next track in queue (Wavelink 3.x)"""
        print(f"Track ended with reason: {reason}")
        
        if self.loop and self.now_playing:
            await self.play(self.now_playing)
            return
            
        # Go to the next track
        if self.queue.is_empty:
            self.now_playing = None
            self.is_playing = False
            return
            
        # Get next track
        track = self.queue.get()
        self.now_playing = track
        await self.play(track)
        print(f"Playing next track: {track.title}")
        
    async def do_next(self):
        """Legacy method - Play the next track in queue """
        if self.loop and self.now_playing:
            await self.play(self.now_playing)
            return

        # Check if queue is empty
        if self.queue.is_empty:
            self.now_playing = None
            self.is_playing = False
            return
        
        # Get next track and play it
        track = self.queue.get()
        self.now_playing = track
        
        # Play using wavelink
        await self.play(track)
        self.is_playing = True
    
    async def add_tracks(self, ctx, tracks):
        """Add tracks to the queue with user feedback"""
        if not tracks:
            await ctx.send("**WALA AKONG NAKITANG KANTA!** Try mo nga ulit.", delete_after=15)
            return
        
        # Single track received
        if not isinstance(tracks, list):
            # Add requester attribute for displaying who requested
            tracks.requester = ctx.author
            
            # Add to queue
            self.queue.put(tracks)
            await ctx.send(f"**ADDED TO QUEUE:** {tracks.title}", delete_after=15)
            
        # List of tracks
        elif isinstance(tracks, list):
            if len(tracks) == 1:
                track = tracks[0]
                track.requester = ctx.author
                self.queue.put(track)
                await ctx.send(f"**ADDED TO QUEUE:** {track.title}", delete_after=15)
            else:
                # Handling a list of tracks
                for track in tracks:
                    track.requester = ctx.author
                    self.queue.put(track)
                await ctx.send(f"**ADDED TO QUEUE:** {len(tracks)} tracks", delete_after=15)
        
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
        """Initialize audio systems (TTS works without Lavalink)"""
        print("Initializing Audio Systems...")
        
        # For our updated 2025 approach, we don't need Lavalink for TTS
        # We now use direct Discord voice client playback
        # But we'll still try to connect for music playback commands
        
        # Setup Wavelink nodes (optional - only needed for music playback)
        try:
            # Create nodes using Wavelink 3.x API
            nodes = [
                wavelink.Node(
                    uri='http://localhost:2333',
                    password='youshallnotpass',
                    inactive_player_timeout=None,
                    identifier="main-node"
                )
            ]
            
            # Connect to the Lavalink server using wavelink 3.x API
            wavelink.Pool.nodes = nodes
            await wavelink.Pool.nodes[0].connect(client=self.bot)
            self.wavelink_connected = True
            print("✅ Connected to Lavalink node! (Music playback enabled)")
            
            # Setup track end event handling (updated for wavelink 3.x)
            # In wavelink 3.x, we use the on_wavelink_track_end event
            self.bot.add_listener(self.on_wavelink_track_end, "on_wavelink_track_end")
            
        except Exception as e:
            print(f"ℹ️ NOTE: Lavalink not available: {e}")
            print("ℹ️ TTS will work fine, but music playback commands won't work")
            self.wavelink_connected = False
        
        print("✅ Audio Cog loaded with 2025 TTS implementation")
        
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
        # Disconnect all players gracefully using wavelink 3.x API
        try:
            if wavelink.Pool.nodes:
                node = wavelink.Pool.get_node()
                if node and node.players:
                    for player in node.players.values():
                        try:
                            await player.disconnect()
                        except Exception as e:
                            print(f"Error disconnecting player: {e}")
        except Exception as e:
            print(f"Error during cog unload: {e}")

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
        """Join a voice channel using direct Discord voice client (2025 Method)"""
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Get the user's channel
        channel = ctx.author.voice.channel
        print(f"Attempting to join channel: {channel.name} (ID: {channel.id})")
        
        try:
            # Check if already in a voice channel
            voice_client = ctx.guild.voice_client
            if voice_client and voice_client.channel and voice_client.channel.id == channel.id:
                return await ctx.send("**BOBO!** NASA VOICE CHANNEL MO NA AKO!")
            elif voice_client:
                print(f"Already connected to a different channel, disconnecting from {voice_client.channel.name}")
                await voice_client.disconnect()
            
            # First try direct Discord connection (2025 method)
            print("Connecting with direct Discord voice client...")
            try:
                voice_client = await channel.connect()
                await ctx.send(f"**SIGE!** PAPASOK NA KO SA {channel.name}!")
                print(f"Successfully connected to {channel.name} with direct Discord voice client")
                return
            except Exception as direct_error:
                print(f"Direct connection error: {direct_error}")
                
                # Only if Wavelink is available, try it as a fallback
                if self.wavelink_connected:
                    try:
                        print("Trying Wavelink connection as fallback...")
                        player = await channel.connect(cls=wavelink.Player)
                        await ctx.send(f"**SIGE!** PAPASOK NA KO SA {channel.name}! (Wavelink mode)")
                        print(f"Connected to {channel.name} with Wavelink")
                        return
                    except Exception as wavelink_error:
                        print(f"Wavelink connection also failed: {wavelink_error}")
                        raise Exception(f"Failed to connect: {direct_error} | Wavelink error: {wavelink_error}")
                else:
                    # Re-raise the direct connection error since Wavelink isn't available
                    raise direct_error
            
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
    
    async def play_tts_directly(self, player, filename):
        """Play a TTS file directly using FFmpeg"""
        print(f"Trying direct FFmpeg playback as fallback...")
        
        # Check if the file exists
        if not os.path.exists(filename):
            raise Exception("File does not exist for direct playback")
            
        # Use FFmpeg source as a fallback
        try:
            # Different handling for Wavelink Player vs regular VoiceClient
            if isinstance(player, wavelink.Player):
                # For Wavelink 2.6.3, we need to convert the file to a URL
                # and let Lavalink handle it
                abs_path = os.path.abspath(filename).replace('\\', '/')
                file_url = f"file:///{abs_path}"
                
                # Get a node and tracks using wavelink 3.x API
                node = wavelink.Pool.get_node()
                if not node:
                    raise Exception("No Lavalink node available")
                
                # Use wavelink 3.x search API
                tracks = await wavelink.Playable.search(file_url)
                if not tracks:
                    raise Exception("Could not load track from file")
                
                # Play the track
                await player.play(tracks[0])
            else:
                # Regular discord.py VoiceClient
                source = discord.FFmpegPCMAudio(filename)
                player.play(source)
                
            return True
        except Exception as e:
            print(f"Direct playback failed: {e}")
            return False
    
    # Custom PCM audio source that directly reads from WAV file
    class PCMStream(discord.AudioSource):
        def __init__(self, filename):
            import wave
            self.file = wave.open(filename, "rb")
            self.closed = False
            
        def read(self):
            # Read smaller buffer size (1920 bytes) for lower memory usage
            if self.closed:
                return b''
            return self.file.readframes(960)  # 960 samples = 1920 bytes for 16-bit stereo
            
        def is_opus(self):
            return False  # This is PCM, not Opus
            
        def cleanup(self):
            if not self.closed:
                self.file.close()
                self.closed = True
    
    @commands.command(name="vc")
    async def vc(self, ctx, *, message: str):
        """Text-to-speech using Edge TTS with direct Discord playback (2025 Method)"""
        # Check if user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Check rate limiting
        if is_rate_limited(ctx.author.id):
            return await ctx.send(f"**TEKA LANG {ctx.author.mention}!** Ang bilis mo mag-type! Hinay-hinay lang!")
        
        add_rate_limit_entry(ctx.author.id)
        
        # Send processing message
        processing_msg = await ctx.send("**SANDALI LANG!** Ginagawa ko pa yung audio...")
        
        try:
            # Generate TTS using edge_tts
            print(f"Generating Edge TTS for message: '{message}'")
            mp3_filename = f"{self.temp_dir}/tts_{ctx.message.id}.mp3"
            
            # Import edge_tts here to avoid overhead if not used
            import edge_tts
            
            # Create Edge TTS communicator - use Tagalog/Filipino voice
            # Options: fil-PH-AngeloNeural (male), fil-PH-BlessicaNeural (female)
            # If these fail, fallback to en-US-JennyNeural or en-US-ChristopherNeural
            tts = edge_tts.Communicate(text=message, voice="fil-PH-BlessicaNeural")
            
            # Generate MP3 audio using Edge TTS API
            await tts.save(mp3_filename)
            print(f"Edge TTS file generated successfully: {mp3_filename}")
            
            # Verify file exists and has content
            if not os.path.exists(mp3_filename):
                raise Exception("Failed to generate Edge TTS file - file does not exist")
            
            if os.path.getsize(mp3_filename) == 0:
                raise Exception("Failed to generate Edge TTS file - file is empty")
                
            print(f"Edge TTS file saved: {mp3_filename} ({os.path.getsize(mp3_filename)} bytes)")
            
            # Store in database
            with open(mp3_filename, "rb") as f:
                audio_data = f.read()
                audio_id = store_audio_tts(ctx.author.id, message, audio_data)
                print(f"Stored Edge TTS in database with ID: {audio_id}")
            
            # Connect to the voice channel
            voice_channel = ctx.author.voice.channel
            
            try:
                # Modern 2025 approach for Discord playback - using direct voice client
                # We'll use the classic Discord voice client first for more reliability
                
                # Get existing voice client or create a new one
                voice_client = ctx.voice_client
                if not voice_client:
                    print(f"Connecting to voice channel: {voice_channel.name}")
                    voice_client = await voice_channel.connect()
                elif voice_client.channel.id != voice_channel.id:
                    print(f"Moving to different voice channel: {voice_channel.name}")
                    await voice_client.move_to(voice_channel)
                
                # Create audio source from the MP3 file
                audio_source = discord.FFmpegPCMAudio(mp3_filename)
                
                # Apply volume transformer to normalize the audio
                audio = discord.PCMVolumeTransformer(audio_source, volume=1.0)
                
                # Play the audio file
                voice_client.play(audio)
                print(f"Playing TTS audio directly through Discord voice client: {mp3_filename}")
                
                # Success message
                await processing_msg.delete()
                await ctx.send(f"🔊 **SPEAKING:** {message}", delete_after=10)
                
                # Wait for the audio to finish playing
                while voice_client.is_playing():
                    await asyncio.sleep(0.5)
                
                # Don't disconnect - let the bot stay in channel 
                # We purposely avoid disconnecting to minimize join/leave spam
                
            except Exception as play_error:
                print(f"Discord playback error: {play_error}")
                import traceback
                traceback.print_exc()
                
                # If classic method fails, try with FFmpeg disabled (fallback)
                try:
                    # Fallback to using our PCMStream method
                    voice_client = ctx.voice_client
                    if not voice_client:
                        voice_client = await voice_channel.connect()
                    
                    # Convert MP3 to WAV with proper format for Discord
                    from pydub import AudioSegment
                    wav_filename = f"{self.temp_dir}/tts_wav_{ctx.message.id}.wav"
                    
                    # Convert using pydub with optimized settings
                    audio = AudioSegment.from_mp3(mp3_filename)
                    audio = audio.set_frame_rate(48000).set_channels(2)
                    audio.export(wav_filename, format="wav")
                    
                    # Use our custom PCM streaming
                    source = self.PCMStream(wav_filename)
                    voice_client.play(source)
                    
                    # Success message for fallback method
                    await processing_msg.delete()
                    await ctx.send(f"🔊 **SPEAKING (Fallback Mode):** {message}", delete_after=10)
                    
                    # Wait for playback to finish
                    while voice_client.is_playing():
                        await asyncio.sleep(0.5)
                    
                    # Clean up WAV file
                    try:
                        os.remove(wav_filename)
                    except:
                        pass
                        
                except Exception as fallback_error:
                    # Both methods failed
                    print(f"Fallback playback also failed: {fallback_error}")
                    
                    # Even if playback fails, we've still generated the TTS
                    await processing_msg.delete()
                    await ctx.send(f"🔊 **TTS GENERATED:** {message}\n\n(Audio generated but couldn't be played. Error: {str(play_error)[:100]}...)", delete_after=15)
                
            # Clean up the files once we're done
            try:
                os.remove(mp3_filename)
                print(f"Removed temporary file: {mp3_filename}")
            except Exception as e:
                print(f"Error removing file: {e}")
            
            # Clean up old database entries
            cleanup_old_audio_tts(keep_count=20)
            print("Cleaned up old TTS entries")
            
        except Exception as e:
            print(f"⚠️ EDGE TTS ERROR: {e}")
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
        """Replay last TTS message from database using direct Discord playback (2025 Method)"""
        # Check if user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Get the latest audio entry
        audio_data = get_latest_audio_tts()
        if not audio_data:
            return await ctx.send("**WALA AKONG MAALALA!** Wala pa akong na-save na audio.")
        
        audio_id, audio_bytes = audio_data
        
        # Send processing message
        processing_msg = await ctx.send("**SANDALI LANG!** Ire-replay ko pa yung huling audio...")
        
        try:
            # Save audio to temp file
            mp3_filename = f"{self.temp_dir}/replay_{ctx.message.id}.mp3"
            
            with open(mp3_filename, "wb") as f:
                f.write(audio_bytes)
                
            print(f"Saved replay audio to file: {mp3_filename}")
            
            # Connect to the voice channel
            voice_channel = ctx.author.voice.channel
            
            try:
                # Modern 2025 approach for Discord playback - using direct voice client
                # Get existing voice client or create a new one
                voice_client = ctx.voice_client
                if not voice_client:
                    print(f"Connecting to voice channel: {voice_channel.name}")
                    voice_client = await voice_channel.connect()
                elif voice_client.channel.id != voice_channel.id:
                    print(f"Moving to different voice channel: {voice_channel.name}")
                    await voice_client.move_to(voice_channel)
                
                # Create audio source from the MP3 file
                audio_source = discord.FFmpegPCMAudio(mp3_filename)
                
                # Apply volume transformer to normalize the audio
                audio = discord.PCMVolumeTransformer(audio_source, volume=1.0)
                
                # Play the audio file
                voice_client.play(audio)
                print(f"Playing replay audio directly through Discord voice client: {mp3_filename}")
                
                # Success message
                await processing_msg.delete()
                await ctx.send(f"🔊 **REPLAYING:** Last TTS message", delete_after=10)
                
                # Wait for the audio to finish playing
                while voice_client.is_playing():
                    await asyncio.sleep(0.5)
                
                # Don't disconnect - let the bot stay in channel
                
            except Exception as play_error:
                print(f"Discord replay error: {play_error}")
                import traceback
                traceback.print_exc()
                
                # If classic method fails, try with FFmpeg disabled (fallback)
                try:
                    # Fallback to using our PCMStream method
                    voice_client = ctx.voice_client
                    if not voice_client:
                        voice_client = await voice_channel.connect()
                    
                    # Convert MP3 to WAV with proper format for Discord
                    from pydub import AudioSegment
                    wav_filename = f"{self.temp_dir}/replay_wav_{ctx.message.id}.wav"
                    
                    # Convert using pydub with optimized settings
                    audio = AudioSegment.from_mp3(mp3_filename)
                    audio = audio.set_frame_rate(48000).set_channels(2)
                    audio.export(wav_filename, format="wav")
                    
                    # Use our custom PCM streaming
                    source = self.PCMStream(wav_filename)
                    voice_client.play(source)
                    
                    # Success message for fallback method
                    await processing_msg.delete()
                    await ctx.send(f"🔊 **REPLAYING (Fallback Mode):** Last TTS message", delete_after=10)
                    
                    # Wait for playback to finish
                    while voice_client.is_playing():
                        await asyncio.sleep(0.5)
                    
                    # Clean up WAV file
                    try:
                        os.remove(wav_filename)
                    except:
                        pass
                        
                except Exception as fallback_error:
                    # Both methods failed
                    print(f"Fallback replay also failed: {fallback_error}")
                    
                    # Even if playback fails, we've still retrieved the audio
                    await processing_msg.delete()
                    await ctx.send(f"🔊 **LAST TTS RETRIEVED**\n\n(Audio file found but couldn't be played. Error: {str(play_error)[:100]}...)", delete_after=15)
                
            # Clean up the files
            try:
                os.remove(mp3_filename)
                print(f"Removed temporary replay file: {mp3_filename}")
            except Exception as e:
                print(f"Error removing replay file: {e}")
            
        except Exception as e:
            print(f"⚠️ REPLAY ERROR: {e}")
            import traceback
            traceback.print_exc()
            
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
        
        # Send searching message
        search_msg = await ctx.send(f"**HINAHANAP KO PA:** {query}")
        
        # Get or create the player
        channel = ctx.author.voice.channel
        
        try:
            player = ctx.voice_client
            
            # Create a new player if we don't have one
            if not player:
                # Create MusicPlayer instance instead of a regular Wavelink player
                player = await channel.connect(cls=MusicPlayer)
                print(f"Created new MusicPlayer in {channel.name}")
            
            # Check if we need to move the player
            elif player.channel != channel:
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
            
            # Using the new wavelink 3.x API
            if is_url:
                # For direct URL playback
                try:
                    # Get the node from the Pool
                    node = wavelink.Pool.get_node()
                    
                    # Check if it's a YouTube URL - Use YouTube or auto-select based on URL
                    if "youtube.com" in query or "youtu.be" in query:
                        print("Searching YouTube for URL:", query)
                        # YouTube URL case
                        if "playlist" in query or "list=" in query:
                            # This is a playlist URL
                            tracks = await wavelink.YouTubePlaylist.search(query)
                            print(f"Found {len(tracks.tracks)} tracks in playlist")
                            
                            if not tracks or not tracks.tracks:
                                await search_msg.delete()
                                return await ctx.send(f"**TANGINA! WALANG NAKITA:** No tracks found for that playlist")
                                
                            await player.add_tracks(ctx, tracks.tracks)
                            await search_msg.delete()
                            await ctx.send(f"**PLAYLIST ADDED TO QUEUE:** Added {len(tracks.tracks)} tracks from **{tracks.name}**")
                            return
                        else:
                            # Single YouTube URL
                            tracks = await wavelink.YouTubeTrack.search(query)
                    else:
                        # Generic URL (could be Spotify, SoundCloud, etc.)
                        tracks = await wavelink.Playable.search(query)
                    
                    if not tracks:
                        await search_msg.delete()
                        return await ctx.send(f"**TANGINA! WALANG NAKITA:** No tracks found for that URL")
                        
                    # Get the first result for URL search
                    track = tracks[0]
                    await player.add_tracks(ctx, [track])
                    
                except Exception as e:
                    print(f"Error searching URL: {e}")
                    await search_msg.delete()
                    return await ctx.send(f"**ERROR SEARCHING URL:** {str(e)[:100]}...")
            else:
                # For search queries
                try:
                    # Search YouTube for the query
                    print("Searching YouTube for query:", query)
                    tracks = await wavelink.YouTubeTrack.search(query)
                    
                    if not tracks:
                        await search_msg.delete()
                        return await ctx.send(f"**TANGINA! WALANG NAKITA:** No results found for **{query}**")
                    
                    # For search results, add the top result
                    await player.add_tracks(ctx, [tracks[0]])
                except Exception as e:
                    print(f"Error searching: {e}")
                    await search_msg.delete()
                    return await ctx.send(f"**ERROR SEARCHING:** {str(e)[:100]}...")
            
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