import discord
from discord.ext import commands
import asyncio
import os
import datetime
import random
import logging
import json
import edge_tts
from pydub import AudioSegment
from pydub.playback import play
import io
import wave
import struct

# Import from bot directory
from bot.config import Config
from bot.database import get_connection, store_audio_tts, get_audio_tts_by_id

class EnhancedMusicQueue:
    """A queue system for music playback with enhanced features"""
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

class EnhancedMusicCog(commands.Cog):
    """Enhanced Music Cog focused on TTS and local audio playback with aggressive Tagalog flair"""
    
    def __init__(self, bot):
        self.bot = bot
        
        # Create temp directories if they don't exist
        self.temp_dir = "temp_music"
        self.temp_tts_dir = "temp_audio"
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.temp_tts_dir, exist_ok=True)
        
        # Dictionary to store voice clients and queues per guild
        self.guild_music_data = {}
        
        # Track voice inactivity timers
        self.voice_inactivity_timers = {}
        
        # Voices for TTS
        self.tts_voices = [
            'fil-PH-AngeloNeural',  # Filipino male
            'fil-PH-BlessicaNeural', # Filipino female
            'en-US-AndrewMultilingualNeural', # English male
            'en-US-AvaNeural', # English female
            'en-PH-JamesNeural', # Filipino English male
            'en-PH-RosaNeural',  # Filipino English female
        ]
        
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
                'queue': EnhancedMusicQueue(),
                'volume': 0.5,  # Default volume (0.5 = 50%)
                'now_playing_message': None
            }
        return self.guild_music_data[guild_id]

    async def cog_load(self):
        """Initialize music systems"""
        print("🔊 Enhanced Music Cog loaded with Edge TTS and local audio support")
    
    async def cog_unload(self):
        """Clean up when cog is unloaded"""
        for guild_id in list(self.guild_music_data.keys()):
            guild = self.bot.get_guild(guild_id)
            if guild and guild.voice_client:
                await guild.voice_client.disconnect()
                
        # Clean up temp files
        for directory in [self.temp_dir, self.temp_tts_dir]:
            for file in os.listdir(directory):
                try:
                    os.remove(os.path.join(directory, file))
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

    async def generate_tts_audio(self, text, voice_name=None):
        """Generate TTS audio using Edge TTS and save to file
        
        Args:
            text (str): Text to convert to speech
            voice_name (str, optional): Voice to use. Defaults to random Filipino voice.
            
        Returns:
            str: Path to the audio file
        """
        if not voice_name:
            voice_name = random.choice(self.tts_voices)
            
        # Create a unique filename
        filename = os.path.join(self.temp_tts_dir, f"tts_{random.randint(10000, 99999)}.mp3")
        
        try:
            communicate = edge_tts.Communicate(text, voice_name)
            await communicate.save(filename)
            
            # Store in database for future use
            with open(filename, "rb") as f:
                audio_data = f.read()
                store_audio_tts(0, text, audio_data)
                
            return filename
        except Exception as e:
            print(f"Error generating TTS audio: {e}")
            return None
    
    @commands.command(name="join", aliases=["sumali"])
    async def join(self, ctx):
        """Join user's voice channel"""
        voice_client = await self._ensure_voice_connection(ctx.author.voice.channel if ctx.author.voice else None, ctx.channel)
        if voice_client:
            self.start_inactivity_timer(ctx.guild.id)
    
    @commands.command(name="leave", aliases=["alis", "disconnect"])
    async def leave(self, ctx):
        """Leave voice channel"""
        if ctx.guild.voice_client:
            guild_data = self.get_guild_data(ctx.guild.id)
            guild_data['queue'].clear()
            
            # Cancel inactivity timer
            if ctx.guild.id in self.voice_inactivity_timers:
                self.voice_inactivity_timers[ctx.guild.id].cancel()
                
            await ctx.guild.voice_client.disconnect()
            await ctx.send("👋 **AY OKAY!** Aalis na ako sa voice channel. Ayaw mo na ba sa akin? HA? GAGO! 😤")
        else:
            await ctx.send("**Anong pinagsasabi mo diyan?** Hindi naman ako naka-join sa voice channel! TANGA!")
    
    @commands.command(name="play", aliases=["p", "tugtugin"])
    async def play(self, ctx, *, query=None):
        """Play a local audio file, TTS message, or search for audio
        Usage:
        - g!play <filename> - Play a local audio file
        - g!play tts <message> - Convert text to speech and play it
        - g!play <search query> - Search for a song (disabled on Replit due to API restrictions)
        """
        if not query:
            return await ctx.send("**ULOL!** Walang query? Anong patutugtugin ko, hangin? Maglagay ka ng text!")
            
        # First, ensure we have a voice connection
        voice_client = await self._ensure_voice_connection(ctx.author.voice.channel if ctx.author.voice else None, ctx.channel)
        if not voice_client:
            return
            
        # Get guild data
        guild_data = self.get_guild_data(ctx.guild.id)
        queue = guild_data['queue']
        
        # TTS mode
        if query.lower().startswith("tts "):
            message = query[4:].strip()
            if not message:
                return await ctx.send("**HAYS NAKO!** Walang message? Ano sasabihin ko, \"...\"? Maglagay ka ng text!")
                
            await ctx.send(f"🔊 **Nag-generate ng TTS voice:** {message}")
            
            # Generate TTS audio
            file_path = await self.generate_tts_audio(message)
            if not file_path:
                return await ctx.send("**PUTANGINA!** Hindi ma-generate ang TTS audio. Edge TTS error!")
                
            # Add to queue
            song_info = {
                'title': f"TTS: {message[:30]}{'...' if len(message) > 30 else ''}",
                'file_path': file_path,
                'url': None,
                'duration': 0,  # We don't know the duration of TTS
                'thumbnail': None,
                'uploader': 'Edge TTS',
                'source': 'tts'
            }
            
            queue.add(song_info)
            await ctx.send(f"✅ **Idinagdag sa queue:** {song_info['title']}")
            
            # If not already playing, start playback
            if not voice_client.is_playing():
                await self.play_song(ctx.guild, ctx.channel)
            return
            
        # Check if query is a local file (for admins only)
        if ctx.author.guild_permissions.administrator and os.path.exists(query):
            # Add local file to queue
            song_info = {
                'title': os.path.basename(query),
                'file_path': query,
                'url': None,
                'duration': 0,  # We don't know the duration of local files
                'thumbnail': None,
                'uploader': 'Local File',
                'source': 'local'
            }
            
            queue.add(song_info)
            await ctx.send(f"✅ **Idinagdag sa queue:** {song_info['title']} (Local File)")
            
            # If not already playing, start playback
            if not voice_client.is_playing():
                await self.play_song(ctx.guild, ctx.channel)
            return
            
        # Otherwise, use TTS to explain that external music sources are currently unavailable
        await ctx.send("⚠️ **PAKYU YOUTUBE AT SPOTIFY!** API calls sa mga platforms na yan ay Forbidden sa Replit servers!")
        
        # Generate TTS explanation
        explanation = (
            "Sorry, pero hindi gumagana yung YouTube at Spotify APIs sa Replit servers dahil na-block ang IP range namin. "
            "Gamitin mo na lang yung TTS function: g!play tts <your message>. "
            "O kaya mag-play ka ng local audio files."
        )
        
        file_path = await self.generate_tts_audio(explanation)
        if not file_path:
            return await ctx.send("**PUTANGINA!** Hindi ma-generate ang TTS audio. Edge TTS error!")
            
        # Add to queue
        song_info = {
            'title': "API Restriction Explanation",
            'file_path': file_path,
            'url': None,
            'duration': 0,
            'thumbnail': None,
            'uploader': 'Edge TTS',
            'source': 'tts'
        }
        
        queue.add(song_info)
        
        # If not already playing, start playback
        if not voice_client.is_playing():
            await self.play_song(ctx.guild, ctx.channel)
    
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
        
        try:
            song = queue.current
            file_path = song.get('file_path')
            
            if not file_path or not os.path.exists(file_path):
                await text_channel.send(f"**PUTANGINA!** Hindi mahanap ang audio file: {file_path}")
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
                
                # Delete TTS audio files after playing
                if song.get('source') == 'tts' and file_path and os.path.exists(file_path):
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
                
                if song.get('uploader'):
                    embed.add_field(name="Source", value=song['uploader'])
                
                if song.get('duration') and song['duration'] > 0:
                    embed.add_field(name="Duración", value=str(datetime.timedelta(seconds=song['duration'])))
                
                if song.get('thumbnail'):
                    embed.set_thumbnail(url=song['thumbnail'])
                
                # Add a footer with the command help
                embed.set_footer(text="Commands: g!skip, g!stop, g!queue, g!volume")
                
                # Delete previous now playing message if it exists
                if guild_data['now_playing_message']:
                    try:
                        await guild_data['now_playing_message'].delete()
                    except:
                        pass
                
                # Send and store the new now playing message
                guild_data['now_playing_message'] = await text_channel.send(embed=embed)
            else:
                await text_channel.send("**LINTIK!** Nawala yung voice connection!")
                queue.current = None
                
        except Exception as e:
            await text_channel.send(f"**ERROR:** {str(e)}")
            queue.current = None
            await self.play_next(guild, text_channel)
    
    async def play_next(self, guild, text_channel):
        """Play the next song in the queue"""
        guild_data = self.get_guild_data(guild.id)
        queue = guild_data['queue']
        
        # Check if we should loop the current song
        if queue.loop and queue.current:
            # Just replay the current song
            await self.play_song(guild, text_channel)
            return
            
        # Otherwise, get the next song
        queue.current = queue.next()
        
        # If queue is now empty, start inactivity timer
        if not queue.current:
            await text_channel.send("**TANGINA!** Ubos na ang queue. Magdagdag ka pa ng kanta, GAGO!")
            self.start_inactivity_timer(guild.id)
            return
            
        # Play the next song
        await self.play_song(guild, text_channel)
    
    @commands.command(name="skip", aliases=["s", "laktaw"])
    async def skip(self, ctx):
        """Skip the current song"""
        if not ctx.guild.voice_client or not ctx.guild.voice_client.is_playing():
            return await ctx.send("**GAGO KA BA?** Wala namang tumutugtog!")
            
        guild_data = self.get_guild_data(ctx.guild.id)
        queue = guild_data['queue']
        
        # Admin can skip instantly
        if ctx.author.guild_permissions.administrator:
            await ctx.send(f"⏭️ **ADMIN POWER!** Si **{ctx.author.display_name}** ay nag-skip sa current song dahil ADMIN siya!")
            ctx.guild.voice_client.stop()
            return
            
        # Check if user is in the same voice channel
        if not ctx.author.voice or ctx.author.voice.channel.id != ctx.guild.voice_client.channel.id:
            return await ctx.send("**BOBO!** Dapat nasa parehong voice channel ka para mag-skip ng kanta! Join muna!")
            
        # Count voice channel members (exclude bots)
        voice_members = [m for m in ctx.guild.voice_client.channel.members if not m.bot]
        required_votes = max(2, len(voice_members) // 2)  # At least 2 votes or half of members
        
        # Add user's vote
        votes = queue.add_skip_vote(ctx.author.id)
        
        # If there's only one person in the channel, they can skip
        if len(voice_members) == 1:
            await ctx.send(f"⏭️ **IKW LANG NAMAN NASA VC!** Okay, nag-skip na ng kanta!")
            ctx.guild.voice_client.stop()
            return
            
        # Check if enough votes
        if votes >= required_votes:
            await ctx.send(f"⏭️ **MAJORITY VOTE!** Nag-skip na ng kanta! ({votes}/{required_votes} votes)")
            ctx.guild.voice_client.stop()
        else:
            await ctx.send(f"🗳️ **BOTO PARA SA SKIP!** {ctx.author.display_name} votes to skip ({votes}/{required_votes} votes needed)")
    
    @commands.command(name="queue", aliases=["q", "pila"])
    async def queue_cmd(self, ctx):
        """Show the current queue"""
        guild_data = self.get_guild_data(ctx.guild.id)
        queue = guild_data['queue']
        
        if not queue.current and queue.is_empty():
            return await ctx.send("**WALANG LAMAN!** Queue is empty, GAGO!")
            
        embed = discord.Embed(
            title="🎵 **MUSIC QUEUE**",
            description="",
            color=Config.EMBED_COLOR_INFO
        )
        
        # Add now playing
        if queue.current:
            embed.description += f"**Now Playing:**\n🎵 **{queue.current['title']}**\n\n"
        
        # Add queue items
        if not queue.is_empty():
            embed.description += "**Up Next:**\n"
            for i, song in enumerate(queue.get_queue()):
                embed.description += f"`{i+1}.` {song['title']}\n"
        else:
            embed.description += "*No more songs in queue*\n"
            
        embed.set_footer(text=f"Volume: {int(guild_data['volume'] * 100)}% | Commands: g!skip, g!stop, g!play")
        
        await ctx.send(embed=embed)
    
    @commands.command(name="clear_queue", aliases=["cq", "clearqueue"])
    async def clear_queue(self, ctx):
        """Clear all songs from the queue (except the currently playing one)"""
        guild_data = self.get_guild_data(ctx.guild.id)
        queue = guild_data['queue']
        
        if queue.is_empty():
            return await ctx.send("**ULOL!** Wala namang laman yung queue! BOBO!")
            
        queue.clear()
        await ctx.send("🧹 **LINIIIIIS!** Inalis ko na lahat ng kanta sa queue. Kontento ka na?")
    
    @commands.command(name="loop", aliases=["l", "ulit"])
    async def loop(self, ctx):
        """Toggle looping of the current song"""
        guild_data = self.get_guild_data(ctx.guild.id)
        queue = guild_data['queue']
        
        # Toggle loop state
        queue.loop = not queue.loop
        
        if queue.loop:
            await ctx.send("🔄 **PAULIT-ULIT NA KANTA!** Naka-loop mode na ngayon. Sasakit ulo mo nito!")
        else:
            await ctx.send("➡️ **AYOS!** Hindi na naka-loop. Next song na pagkatapos nito!")
    
    @commands.command(name="volume", aliases=["vol", "v", "lakas"])
    async def volume(self, ctx, volume: int = None):
        """Set the volume (0-100)"""
        guild_data = self.get_guild_data(ctx.guild.id)
        
        if volume is None:
            return await ctx.send(f"🔊 **VOLUME:** {int(guild_data['volume'] * 100)}%")
            
        if not 0 <= volume <= 100:
            return await ctx.send("**BOBO!** Volume dapat nasa pagitan ng 0 at 100!")
            
        # Set the new volume
        guild_data['volume'] = volume / 100
        
        # Apply to current playback
        if ctx.guild.voice_client and ctx.guild.voice_client.source:
            ctx.guild.voice_client.source.volume = guild_data['volume']
            
        await ctx.send(f"🔊 **VOLUME:** Set to {volume}%")
    
    @commands.command(name="stop", aliases=["st", "itigil"])
    async def stop(self, ctx):
        """Stop playback and clear the queue"""
        if not ctx.guild.voice_client or not ctx.guild.voice_client.is_playing():
            return await ctx.send("**LOKO KA BA?** Wala namang tumutugtog!")
            
        guild_data = self.get_guild_data(ctx.guild.id)
        queue = guild_data['queue']
        
        # Clear queue and stop playback
        queue.clear()
        ctx.guild.voice_client.stop()
        
        await ctx.send("⏹️ **TAMA NA YAN!** Inihinto ko na ang tumutugtog at inalis ko na ang lahat ng kanta sa queue.")
        
        # Start inactivity timer
        self.start_inactivity_timer(ctx.guild.id)
    
    @commands.command(name="pause", aliases=["pa", "ihinto"])
    async def pause(self, ctx):
        """Pause the current playback"""
        if not ctx.guild.voice_client or not ctx.guild.voice_client.is_playing():
            return await ctx.send("**TANGA!** Wala namang tumutugtog!")
            
        if ctx.guild.voice_client.is_paused():
            return await ctx.send("**ULOL!** Naka-pause na nga eh!")
            
        ctx.guild.voice_client.pause()
        await ctx.send("⏸️ **PAUSE!** Tumigil sandali ang tumutugtog.")
    
    @commands.command(name="resume", aliases=["r", "ituloy"])
    async def resume(self, ctx):
        """Resume the current playback"""
        if not ctx.guild.voice_client:
            return await ctx.send("**GAGO!** Wala ako sa voice channel!")
            
        if not ctx.guild.voice_client.is_paused():
            return await ctx.send("**LOKO!** Hindi naman naka-pause eh!")
            
        ctx.guild.voice_client.resume()
        await ctx.send("▶️ **RESUME!** Itinuloy ko na ang tumutugtog.")
    
    @commands.command(name="nowplaying", aliases=["np", "ngayon"])
    async def nowplaying(self, ctx):
        """Show information about the currently playing song"""
        if not ctx.guild.voice_client or not ctx.guild.voice_client.is_playing():
            return await ctx.send("**ULOL!** Wala namang tumutugtog!")
            
        guild_data = self.get_guild_data(ctx.guild.id)
        queue = guild_data['queue']
        
        if not queue.current:
            return await ctx.send("**WEIRD!** May tumutugtog pero walang current song? May bug ata!")
            
        song = queue.current
        
        embed = discord.Embed(
            title="🎵 **TUMUTUGTOG NGAYON**",
            description=f"**{song['title']}**",
            color=Config.EMBED_COLOR_PRIMARY
        )
        
        if song.get('uploader'):
            embed.add_field(name="Source", value=song['uploader'])
        
        if song.get('duration') and song['duration'] > 0:
            embed.add_field(name="Duración", value=str(datetime.timedelta(seconds=song['duration'])))
        
        embed.add_field(name="Volume", value=f"{int(guild_data['volume'] * 100)}%")
        embed.add_field(name="Loop Mode", value="Enabled ✅" if queue.loop else "Disabled ❌")
        
        if song.get('thumbnail'):
            embed.set_thumbnail(url=song['thumbnail'])
            
        embed.set_footer(text="Commands: g!skip, g!stop, g!queue, g!volume")
        
        await ctx.send(embed=embed)
        
    @commands.command(name="shuffle", aliases=["sf", "haluin"])
    async def shuffle(self, ctx):
        """Shuffle the songs in the queue"""
        guild_data = self.get_guild_data(ctx.guild.id)
        queue = guild_data['queue']
        
        if queue.is_empty():
            return await ctx.send("**ULOL!** Walang laman ang queue, anong i-shu-shuffle ko?")
            
        queue.shuffle()
        await ctx.send("🔀 **HINALUAN KO NA!** Naka-shuffle na ang queue!")
        
    @commands.command(name="remove", aliases=["rm", "tanggalin"])
    async def remove(self, ctx, index: int = None):
        """Remove a song from the queue by its index"""
        if index is None:
            return await ctx.send("**BOBO!** Specify a track number to remove! Example: g!remove 3")
            
        guild_data = self.get_guild_data(ctx.guild.id)
        queue = guild_data['queue']
        
        if queue.is_empty():
            return await ctx.send("**ULOL!** Walang laman ang queue!")
            
        if not 1 <= index <= len(queue.get_queue()):
            return await ctx.send(f"**GAGO!** Invalid track number! Must be between 1 and {len(queue.get_queue())}")
            
        # Adjust index (user-facing is 1-based, internal is 0-based)
        removed_song = queue.remove_song(index - 1)
        
        if removed_song:
            await ctx.send(f"❌ **TINANGGAL KO NA:** {removed_song['title']}")
        else:
            await ctx.send("**ERROR:** Hindi mahanap ang kanta!")

def setup(bot):
    bot.add_cog(EnhancedMusicCog(bot))