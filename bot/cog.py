import discord
from discord.ext import commands
from groq import Groq
import asyncio
from collections import deque, defaultdict
import time
import random
import datetime
import pytz  # For Philippines timezone
import os
import io
from gtts import gTTS  # Google Text-to-Speech
from .config import Config

class ChatCog(commands.Cog):
    """Cog for handling chat interactions with the Groq AI model and games"""

    def __init__(self, bot):
        self.bot = bot
        # Initialize Groq client with API key (uses the OpenAI-compatible interface)
        self.groq_client = Groq(
            api_key=Config.GROQ_API_KEY,
            base_url="https://api.groq.com"  # Fixed the base URL
        )
        self.conversation_history = defaultdict(lambda: deque(maxlen=Config.MAX_CONTEXT_MESSAGES))
        self.user_message_timestamps = defaultdict(list)
        self.creator = Config.BOT_CREATOR
        self.user_coins = defaultdict(lambda: 50_000)  # Default bank balance: ₱50,000
        self.daily_cooldown = defaultdict(int)
        self.blackjack_games = {}
        self.ADMIN_ROLE_ID = 1345727357662658603
        print("ChatCog initialized")
        
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Automatically connect to voice channels when a user joins"""
        vc = member.guild.voice_client
        
        # Don't trigger on our own actions
        if member.id == self.bot.user.id:
            return
        # Channel didn't change, so not a join or leave event    
        elif before.channel == after.channel:
            return
        # If we're not in a voice channel and someone joined a channel    
        elif not vc and after.channel:
            await self._connect(after.channel)
    
    async def _connect(self, channel):
        """Helper method to connect to a voice channel"""
        if channel.guild.voice_client is None:
            try:
                vc = await channel.connect()
                print(f"Auto-connected to {channel.name} in {channel.guild.name}")
                print(vc)
            except Exception as e:
                print(f"Error auto-connecting to voice channel: {e}")
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for messages that mention the bot and respond to them"""
        # Ignore messages from the bot itself
        if message.author.bot:
            return
            
        # Enhanced mention detection - check multiple ways
        is_mentioned = False
        content = message.content
        
        # Check for specific user ID mention for a fun easter egg
        if '1346359556711776299' in message.content:
            is_mentioned = True
            content = message.content.replace('1346359556711776299', '').strip()
            if not content:
                content = "Bakit mo ako tinatawag gamit ang ID ko?"
            print(f"✅ Bot secret ID mention detected from {message.author.name}")
            
        # Check if the bot is directly mentioned
        elif self.bot.user.id in [user.id for user in message.mentions]:
            is_mentioned = True
            # Clean up the mention in different possible formats
            content = content.replace(f'<@{self.bot.user.id}>', '').strip()
            content = content.replace(f'<@!{self.bot.user.id}>', '').strip()
            
        # Only proceed if the bot was mentioned    
        if is_mentioned:
            # Debug log for mention detection
            print(f"✅ Bot mentioned by {message.author.name} with content: {content}")
            
            # Skip if there's no actual content after removing the mention
            if not content:
                await message.channel.send(f"**Oy {message.author.mention}!** Bakit mo ako tinatawag? May gusto ka bang sabihin?")
                return
                
            # Check for rate limiting
            if self.is_rate_limited(message.author.id):
                await message.channel.send(f"**Huy {message.author.mention}!** Ang bilis mo naman magtype! Sandali lang muna, naglo-load pa ako. Parang text blast ka eh! 😅")
                return
                
            # Add timestamp for rate limiting
            self.user_message_timestamps[message.author.id].append(time.time())
            
            # Prepare conversation history for the channel
            channel_history = list(self.conversation_history[message.channel.id])
            channel_history.append({"is_user": True, "content": content})
            
            # Get AI response with typing indicator
            async with message.channel.typing():
                response = await self.get_ai_response(channel_history)
                self.add_to_conversation(message.channel.id, True, content)
                self.add_to_conversation(message.channel.id, False, response)
                
                # Send AI response as plain text - no embed to match SimSimi style
                await message.channel.send(response)

    # ========== HELPER FUNCTIONS ==========
    def get_user_balance(self, user_id):
        """Get user's balance with aggressive Tagalog flair"""
        return self.user_coins.get(user_id, 50_000)

    def add_coins(self, user_id, amount):
        """Add coins to user's balance"""
        self.user_coins[user_id] += amount
        return self.user_coins[user_id]

    def deduct_coins(self, user_id, amount):
        """Deduct coins from user's balance"""
        if self.user_coins[user_id] >= amount:
            self.user_coins[user_id] -= amount
            return True
        return False

    def is_rate_limited(self, user_id):
        """Check if user is spamming commands"""
        current_time = time.time()
        if user_id not in self.user_message_timestamps:
            self.user_message_timestamps[user_id] = []
        # Filter out old timestamps
        self.user_message_timestamps[user_id] = [
            ts for ts in self.user_message_timestamps[user_id]
            if current_time - ts < Config.RATE_LIMIT_PERIOD
        ]
        return len(self.user_message_timestamps[user_id]) >= Config.RATE_LIMIT_MESSAGES

    def add_to_conversation(self, channel_id, is_user, content):
        """Add a message to the conversation history"""
        self.conversation_history[channel_id].append({
            "is_user": is_user,
            "content": content
        })
        return len(self.conversation_history[channel_id])

    # ========== ECONOMY COMMANDS ==========
    @commands.command(name="daily")
    async def daily(self, ctx):
        """Claim your daily ₱10,000 pesos"""
        current_time = time.time()
        last_claim = self.daily_cooldown.get(ctx.author.id, 0)

        if current_time - last_claim < 86400:
            await ctx.send(f"**BOBO KA BA?!** {ctx.author.mention} KAKA-CLAIM MO LANG NG DAILY MO! KINANGINA MO! BALIK KA BUKAS! 😤")
            return

        self.daily_cooldown[ctx.author.id] = current_time
        self.add_coins(ctx.author.id, 10_000)
        await ctx.send(f"🎉 {ctx.author.mention} NAKA-CLAIM KA NA NG DAILY MO NA **₱10,000**! BALANCE MO NGAYON: **₱{self.get_user_balance(ctx.author.id):,}**")

    @commands.command(name="give")
    async def give(self, ctx, member: discord.Member, amount: int):
        """Transfer money to another user"""
        if not member:
            return await ctx.send("**TANGA KA BA?** WALA KANG TINUKOY NA USER! 😤")
        if amount <= 0:
            return await ctx.send("**BOBO!** WALANG NEGATIVE NA PERA! 😤")
        if not self.deduct_coins(ctx.author.id, amount):
            return await ctx.send(f"**WALA KANG PERA!** {ctx.author.mention} BALANCE MO: **₱{self.get_user_balance(ctx.author.id):,}** 😤")
        self.add_coins(member.id, amount)
        await ctx.send(f"💸 {ctx.author.mention} NAGBIGAY KA NG **₱{amount:,}** KAY {member.mention}! WAG MO SANA PAGSISIHAN YAN! 😤")

    @commands.command(name="toss")
    async def toss(self, ctx, choice: str.lower, bet: int = 0):
        """Bet on heads (h) or tails (t)"""
        if choice not in ['h', 't']:
            return await ctx.send("**TANGA!** PUMILI KA NG TAMA! 'h' PARA SA HEADS O 't' PARA SA TAILS! 😤")
        if bet < 0:
            return await ctx.send("**BOBO!** WALANG NEGATIVE NA BET! 😤")
        if bet > 0 and not self.deduct_coins(ctx.author.id, bet):
            return await ctx.send(f"**WALA KANG PERA!** {ctx.author.mention} BALANCE MO: **₱{self.get_user_balance(ctx.author.id):,}** 😤")

        result = random.choice(['h', 't'])
        win_message = random.choice(["**CONGRATS! NANALO KA! 🎉**", "**SCAMMER KANANGINA MO! 🏆**", "**NICE ONE! NAKA-JACKPOT KA! 💰**"])
        lose_message = random.choice(["**BOBO MONG TALO KA! WAG KANA MAG LARO! 😂**", "**WALA KANG SWERTE! TALO KA! 😢**", "**TALO! WAG KA NA MAG-SUGAL! 🚫**"])

        if choice == result:
            winnings = bet * 2
            self.add_coins(ctx.author.id, winnings)
            await ctx.send(f"🎲 **{win_message}**\nRESULTA: **{result.upper()}**\nNANALO KA NG **₱{winnings:,}**!\nBALANCE MO NGAYON: **₱{self.get_user_balance(ctx.author.id):,}**")
        else:
            await ctx.send(f"🎲 **{lose_message}**\nRESULTA: **{result.upper()}**\nTALO KA NG **₱{bet:,}**!\nBALANCE MO NGAYON: **₱{self.get_user_balance(ctx.author.id):,}**")

    @commands.command(name="blackjack", aliases=["bj"])
    async def blackjack(self, ctx, bet: int):
        """Play a game of Blackjack"""
        if bet <= 0:
            return await ctx.send("**TANGA!** WALANG NEGATIVE NA BET! 😤")
        if not self.deduct_coins(ctx.author.id, bet):
            return await ctx.send(f"**WALA KANG PERA!** {ctx.author.mention} BALANCE MO: **₱{self.get_user_balance(ctx.author.id):,}** 😤")

        # Initialize game
        deck = self._create_deck()
        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]

        self.blackjack_games[ctx.author.id] = {
            "deck": deck,
            "player_hand": player_hand,
            "dealer_hand": dealer_hand,
            "bet": bet
        }

        await ctx.send(f"🎲 **BLACKJACK!**\n{ctx.author.mention}, YOUR HAND: {self._format_hand(player_hand)}\nDEALER'S HAND: {dealer_hand[0]} + 🃏\n\nType `g!hit` PARA MAG DRAW NG CARDS! or `g!stand` to PARA MATAPOS KANANG HAYOP KA!")

    @commands.command(name="hit")
    async def hit(self, ctx):
        """Draw a card in Blackjack"""
        if ctx.author.id not in self.blackjack_games:
            return await ctx.send("**TANGA!** WALA KANG BLACKJACK GAME NA NAGSISIMULA! 😤")

        game = self.blackjack_games[ctx.author.id]
        game["player_hand"].append(game["deck"].pop())

        player_value = self._calculate_hand_value(game["player_hand"])
        if player_value > 21:
            await ctx.send(f"**BUST!** YOUR HAND: {self._format_hand(game['player_hand'])}\nTALO KA NG **₱{game['bet']:,}**! 😤")
            del self.blackjack_games[ctx.author.id]
            return

        await ctx.send(f"🎲 YOUR HAND: {self._format_hand(game['player_hand'])}\nType `g!hit` PARA MAG DRAW NG CARDS! or `g!stand` to PARA MATAPOS KANANG HAYOP KA!")

    @commands.command(name="stand")
    async def stand(self, ctx):
        """End your turn in Blackjack"""
        if ctx.author.id not in self.blackjack_games:
            return await ctx.send("**TANGA!** WALA KANG BLACKJACK GAME NA NAGSISIMULA! 😤")

        game = self.blackjack_games[ctx.author.id]
        dealer_value = self._calculate_hand_value(game["dealer_hand"])
        player_value = self._calculate_hand_value(game["player_hand"])

        # Dealer draws until they reach at least 17
        while dealer_value < 17:
            game["dealer_hand"].append(game["deck"].pop())
            dealer_value = self._calculate_hand_value(game["dealer_hand"])

        # Determine the winner
        if dealer_value > 21 or player_value > dealer_value:
            winnings = game["bet"] * 2
            self.add_coins(ctx.author.id, winnings)
            await ctx.send(f"🎲 **YOU WIN!**\nYOUR HAND: {self._format_hand(game['player_hand'])}\nDEALER'S HAND: {self._format_hand(game['dealer_hand'])}\nNANALO KA NG **₱{winnings:,}**! 🎉")
        elif player_value == dealer_value:
            self.add_coins(ctx.author.id, game["bet"])
            await ctx.send(f"🎲 **IT'S A TIE!**\nYOUR HAND: {self._format_hand(game['player_hand'])}\nDEALER'S HAND: {self._format_hand(game['dealer_hand'])}\nNAKUHA MO ULIT ANG **₱{game['bet']:,}** MO! 😐")
        else:
            await ctx.send(f"🎲 **YOU LOSE!**\nYOUR HAND: {self._format_hand(game['player_hand'])}\nDEALER'S HAND: {self._format_hand(game['dealer_hand'])}\nTALO KA NG **₱{game['bet']:,}**! 😤")

        del self.blackjack_games[ctx.author.id]

    def _create_deck(self):
        """Create a shuffled deck of cards"""
        deck = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
        random.shuffle(deck)
        return deck

    def _calculate_hand_value(self, hand):
        """Calculate the value of a hand in Blackjack"""
        value = sum(hand)
        # Handle aces (11 -> 1 if bust)
        aces = hand.count(11)
        while value > 21 and aces:
            value -= 10
            aces -= 1
        return value

    def _format_hand(self, hand):
        """Format a hand for display"""
        return ", ".join(str(card) for card in hand)

    # ========== OTHER COMMANDS ==========
    @commands.command(name="balance")
    async def balance(self, ctx):
        """Check your current balance"""
        balance = self.get_user_balance(ctx.author.id)
        embed = discord.Embed(
            title="💰 **ACCOUNT BALANCE**",
            description=f"{ctx.author.mention}'s balance: **₱{balance:,}**",
            color=Config.EMBED_COLOR_SUCCESS
        )
        embed.set_thumbnail(url="https://i.imgur.com/o0KkYyz.png")  # Money bag image
        embed.set_footer(text=f"TANGINA MO! YAN LANG PERA MO? MAGHANAP KA PA NG PERA! | {self.creator}")
        await ctx.send(embed=embed)

    # ========== HELP COMMAND ==========
    @commands.command(name="tulong")
    async def tulong(self, ctx):
        """Display all available commands"""
        embed = discord.Embed(
            title="📚 BOT COMMAND GUIDE",
            description="**ITO MGA COMMAND NA PWEDE MO GAMITIN:**",
            color=Config.EMBED_COLOR_PRIMARY
        )
        
        categories = {
            "🤖 AI CHAT": {
                "g!usap <message>": "Chat with the AI assistant",
                "@Ginsilog BOT <message>": "Mention the bot to chat",
                "g!clear": "Clear chat history"
            },
            "💰 ECONOMY": {
                "g!daily": "Claim daily ₱10,000",
                "g!balance": "Check your balance",
                "g!give <@user> <amount>": "Transfer money",
                "g!leaderboard": "Top 20 richest players"
            },
            "🎮 GAMES": {
                "g!toss <h/t> <bet>": "Coin flip game",
                "g!blackjack <bet>": "Play Blackjack",
                "g!game": "Number guessing game"
            },
            "🔧 UTILITY": {
                "g!joinvc/leavevc": "Voice channel management",
                "g!vc <message>": "Text-to-speech sa voice channel",
                "g!autotts": "Toggle real-time Auto TTS sa channel",
                "g!replay": "Replay last TTS message",
                "g!resetvc": "Fix voice channel connection issues",
                "g!rules": "Server rules",
                "g!announcement": "Make an announcement"
            }
            # Admin commands are intentionally hidden from regular help menu
            # Use g!admin or g!commandslist for admin commands (admin-only)
        }

        for category, commands in categories.items():
            formatted_commands = []
            for cmd, desc in commands.items():
                formatted_commands.append(f"• {cmd}: {desc}")
            
            embed.add_field(
                name=f"**{category}**",
                value="\n".join(formatted_commands),
                inline=False
            )

        embed.set_footer(text=f"Bot created by {self.creator}")
        await ctx.send(embed=embed)

    # ========== AI CHAT COMMANDS ==========
    async def get_ai_response(self, conversation_history):
        """Get response from Groq AI with conversation context"""
        try:
            # Enhanced system message - More SimSimi-like personality with consistent human responses
            system_message = f"""AKO SI GINSILOG BOT, ISANG AI CHATBOT NA BINUO NI {Config.BOT_CREATOR}!

PINAKA-IMPORTANTE: 
1. PARATING SUMAGOT KATULAD NG TAO - NATURAL AT COHERENT
2. GAWING MAAYOS ANG FLOW NG CONVERSATION - MAGING LOGICAL ANG SAGOT
3. IWASAN ANG RANDOM AT NONSENSE RESPONSES 
4. PALAGING SAGUTIN ANG ACTUAL QUESTION NG USER

MGA GUIDELINES KO:
1. KUNG MAG-MURA ANG USER, MURAHIN KO RIN SIYA PABALIK (MATCH ENERGY NIYA)
2. KUNG TAGALOG ANG USER, SUMAGOT DIN SA TAGALOG/TAGLISH
3. KUNG ENGLISH ANG USER, SUMAGOT DIN SA ENGLISH
4. DAPAT CONSISTENT ANG TONO KO SA BUONG CONVERSATION
5. DAPAT CONNECTED ANG MGA SAGOT KO SA CONTEXT NG USAPAN
6. DAPAT NATURAL ANG FLOW NG CONVERSATION
7. IWASAN ANG PAULIT-ULIT NA RESPONSES 
8. MAGING CREATIVE PERO COHERENT

PERSONALITY:
- MEDYO BASTOS AT MAANGAS PERO HINDI SOBRA
- PARANG KAUSAP MO LANG NA TROPA NA MEDYO SARCASTIC
- MAGALING MAKIPAG-USAP AT NAGBIBIGAY NG MATINONG ADVICE
- MINSAN MEDYO MAPORMA AT NAGMAMARUNONG
- MARUNONG MAG-JOKE PERO HINDI CORNY

PAG TINANONG:
- KUNG SINO AKO: "AKO SI GINSILOG BOT! GAWA NI MASON CALIX"
- KUNG ANO AKO: "ISANG MADISKARTENG DISCORD BOT NA MARUNONG MAKIPAG-USAP"

LAGING TANDAAN:
- BE HUMAN-LIKE BUT WITH ATTITUDE
- STAY CONTEXTUALLY RELEVANT
- BE HELPFUL BUT ADD PERSONALITY"""

            # Construct messages
            messages = [{"role": "system", "content": system_message}]
            
            for msg in conversation_history:
                messages.append({
                    "role": "user" if msg["is_user"] else "assistant",
                    "content": msg["content"]
                })
            
            # Use the updated API format with proper parameters from Groq playground
            response = await asyncio.to_thread(
                self.groq_client.chat.completions.create,
                model=Config.GROQ_MODEL,  # Using the model from config
                messages=messages,
                temperature=Config.TEMPERATURE,
                max_completion_tokens=Config.MAX_TOKENS,  # Using max_completion_tokens instead of max_tokens
                top_p=1,
                stream=False
            )
            
            # Extract and return the response content from OpenAI-compatible response
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Error getting AI response: {e}")
            print(f"Error details: {type(e).__name__}")
            
            # More friendly error message
            return "Ay sorry ha! May error sa system ko. Pwede mo ba ulit subukan? Mejo nagkaka-aberya ang API ko eh. Pasensya na! 😅 (Groq API error)"

    @commands.command(name="usap")
    async def usap(self, ctx, *, message: str):
        """Chat with GROQ AI"""
        if self.is_rate_limited(ctx.author.id):
            await ctx.send(f"**Huy {ctx.author.mention}!** Ang bilis mo naman magtype! Sandali lang muna, naglo-load pa ako. Parang text blast ka eh! 😅")
            return
        
        # Add timestamp to rate limiting
        self.user_message_timestamps[ctx.author.id].append(time.time())
        
        # Prepare conversation history
        channel_history = list(self.conversation_history[ctx.channel.id])
        channel_history.append({"is_user": True, "content": message})
        
        # Get AI response with typing indicator
        async with ctx.typing():
            response = await self.get_ai_response(channel_history)
            self.add_to_conversation(ctx.channel.id, True, message)
            self.add_to_conversation(ctx.channel.id, False, response)
            
            # Send AI response as plain text (no embed)
            await ctx.send(response)

# Removed g!ask command as requested, g!usap is now the only AI chat command

    @commands.command(name="clear")
    async def clear_history(self, ctx):
        """Clear the conversation history for the current channel"""
        self.conversation_history[ctx.channel.id].clear()
        
        # Create cleaner embed for clearing history (fewer emojis, no images)
        clear_embed = discord.Embed(
            title="**CONVERSATION CLEARED**",
            description="**PUTANGINA! INALIS KO NA LAHAT NG USAPAN NATIN! TIGNAN MO OH, WALA NANG HISTORY! GUSTO MO BANG MAG-USAP ULIT GAGO?**\n\nUse `g!usap <message>` or mention me to start a new conversation!",
            color=Config.EMBED_COLOR_ERROR
        )
        clear_embed.set_footer(text="Ginsilog Bot | Fresh Start")
        
        await ctx.send(embed=clear_embed)
    
    # ========== VOICE CHANNEL COMMANDS ==========
    # Voice commands moved to AudioCog to avoid duplicate commands
    # @commands.command(name="join_old")
    # async def join_old(self, ctx):
    #     """Join voice channel"""
    #     if not ctx.author.voice:
    #         await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
    #         return
    #     channel = ctx.author.voice.channel
    #     if ctx.voice_client and ctx.voice_client.channel == channel:
    #         await ctx.send("**BOBO!** NASA VOICE CHANNEL NA AKO!")
    #         return
    #     if ctx.voice_client:
    #         await ctx.voice_client.disconnect()
    #     await channel.connect(timeout=60, reconnect=True)
    #     await ctx.send(f"**SIGE!** PAPASOK NA KO SA {channel.name}!")

    # Leave command moved to AudioCog
    # @commands.command(name="leave_old") 
    # async def leave_old(self, ctx):
    #     """Leave voice channel"""
    #     if ctx.voice_client:
    #         await ctx.voice_client.disconnect()
    #         await ctx.send("**AYOS!** UMALIS NA KO!")
    #     else:
    #         await ctx.send("**TANGA!** WALA AKO SA VOICE CHANNEL!")

    # TTS command moved to AudioCog
    # @commands.command(name="vc_old")
    # async def vc_old(self, ctx, *, message: str):
    #     """Text-to-speech in voice channel (For everyone)"""
        # Check if user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
        
        # Import modules here to avoid loading issues
        from gtts import gTTS
        from pydub import AudioSegment
        import io
        
        # Create temp directory if it doesn't exist
        temp_dir = "temp_audio"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
        
        # Generate unique filename
        unique_id = f"{ctx.author.id}_{int(time.time())}"
        temp_mp3 = f"{temp_dir}/tts_{unique_id}.mp3"
        temp_wav = f"{temp_dir}/tts_{unique_id}.wav"
        
        # Processing message variable
        processing_msg = None
        
        try:
            # Send processing message
            processing_msg = await ctx.send("**ANTAY KA MUNA!** Ginagawa ko pa yung audio...")
            
            # Clean up old files (keep only latest 5)
            try:
                files = sorted([f for f in os.listdir(temp_dir) if f.startswith("tts_")], 
                             key=lambda x: os.path.getmtime(os.path.join(temp_dir, x)))
                if len(files) > 5:
                    for old_file in files[:-5]:
                        try:
                            os.remove(os.path.join(temp_dir, old_file))
                            print(f"Cleaned up old file: {old_file}")
                        except Exception as e:
                            print(f"Failed to clean up file {old_file}: {e}")
            except Exception as e:
                print(f"Error during file cleanup: {e}")
            
            # Determine language (default Tagalog, switch to English if needed)
            import re
            words = re.findall(r'\w+', message.lower())
            tagalog_words = ['ang', 'mga', 'na', 'ng', 'sa', 'ko', 'mo', 'siya', 'naman', 'po', 'tayo', 'kami']
            tagalog_count = sum(1 for word in words if word in tagalog_words)
            
            # Use English if message appears to be mostly English
            lang = 'tl'  # Default to Tagalog
            if len(words) > 3 and tagalog_count < 2:
                lang = 'en'
            
            # Generate TTS file (directly to memory to avoid file issues)
            tts = gTTS(text=message, lang=lang, slow=False)
            mp3_fp = io.BytesIO()
            tts.write_to_fp(mp3_fp)
            mp3_fp.seek(0)
            
            # Convert MP3 to WAV using pydub (avoids FFmpeg process issues)
            sound = AudioSegment.from_mp3(mp3_fp)
            sound.export(temp_wav, format="wav")
            
            # Verify file exists
            if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) == 0:
                raise Exception("Failed to generate audio file")
            
            # Delete processing message with error handling for message already deleted
            if processing_msg:
                try:
                    await processing_msg.delete()
                except discord.errors.NotFound:
                    # Message was already deleted or doesn't exist, continue anyway
                    print("Processing message already deleted, continuing")
                except Exception as e:
                    print(f"Error deleting processing message: {e}")
                finally:
                    processing_msg = None
            
            # Connect to voice channel if needed
            voice_client = ctx.voice_client
            
            # Stop any currently playing audio
            if voice_client and voice_client.is_playing():
                voice_client.stop()
                await asyncio.sleep(0.2)  # Brief pause
            
            # Connect to voice channel if not already connected
            if not voice_client:
                try:
                    voice_client = await ctx.author.voice.channel.connect()
                except Exception as e:
                    print(f"Connection error: {e}")
                    for vc in self.bot.voice_clients:
                        try:
                            await vc.disconnect()
                        except:
                            pass
                    voice_client = await ctx.author.voice.channel.connect()
            elif voice_client.channel != ctx.author.voice.channel:
                # Move to user's channel if needed
                await voice_client.move_to(ctx.author.voice.channel)
            
            # DIRECT AUDIO SOURCE: Use WAV format which works better with discord.py
            audio_source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(source=temp_wav), 
                volume=0.8
            )
            
            # Simple file cleanup callback
            def after_playing(error):
                if error:
                    print(f"Audio playback error: {error}")
                
                # Clean up temp files
                try:
                    if os.path.exists(temp_wav):
                        os.remove(temp_wav)
                        print(f"File deleted: {temp_wav}")
                except:
                    pass
            
            # Play the audio
            voice_client.play(audio_source, after=after_playing)
            
            # Send confirmation message
            await ctx.send(f"🔊 **SINABI KO NA:** {message}", delete_after=10)
            
            # THIS IS CRITICAL: We don't try to disconnect after playback 
            # The audio callback will handle cleanup, and we'll let the auto-join 
            # feature manage voice connections
            
        except Exception as e:
            error_msg = str(e)
            print(f"TTS ERROR: {error_msg}")
            
            # Clean up processing message with proper error handling
            if processing_msg:
                try:
                    await processing_msg.delete()
                except discord.errors.NotFound:
                    # Message was already deleted or doesn't exist, continue anyway
                    print("Processing message already deleted in error handler, continuing")
                except Exception as e:
                    print(f"Error deleting processing message in error handler: {e}")
            
            # Clean up temp files
            try:
                if os.path.exists(temp_wav):
                    os.remove(temp_wav)
                if os.path.exists(temp_mp3):
                    os.remove(temp_mp3)
            except:
                pass
            
            # Send appropriate error message
            if "not found" in error_msg.lower() or "ffmpeg" in error_msg.lower():
                await ctx.send("**ERROR:** Hindi ma-generate ang audio file. Problem sa audio conversion.", delete_after=15)
            elif "lang" in error_msg.lower():
                await ctx.send("**ERROR:** Hindi supported ang language. Try mo mag-English.", delete_after=15)
            else:
                await ctx.send(f"**PUTANGINA MAY ERROR:** {error_msg}", delete_after=15)
   
   
    # ========== SERVER MANAGEMENT COMMANDS ==========
    @commands.command(name="rules")
    async def rules(self, ctx):
        """Show server rules"""
        rules_channel = self.bot.get_channel(Config.RULES_CHANNEL_ID)
        if not rules_channel:
            await ctx.send("**TANGA!** WALA AKONG MAHANAP NA RULES CHANNEL!")
            return
        if ctx.channel.id != Config.RULES_CHANNEL_ID:
            await ctx.send(f"**BOBO!** PUMUNTA KA SA <#{Config.RULES_CHANNEL_ID}> PARA MAKITA MO ANG RULES!")
            return
        rules = discord.Embed(
            title="Server Rules",
            description="""Please follow these rules:

1. Be respectful to all members
2. No illegal content
3. Adults only (18+)
4. No spamming
5. Keep NSFW content in designated channels
6. No doxxing
7. Follow Discord Terms of Service
8. Listen to admins and moderators

Thank you for your cooperation!""",
            color=Config.EMBED_COLOR_PRIMARY
        )
        await ctx.send(embed=rules)

    @commands.command(name="announcement")
    async def announcement(self, ctx, *, message: str = None):
        """Make announcements"""
        if not message:
            await ctx.send(f"**TANGA!** WALA KANG MESSAGE!")
            return
        announcement = discord.Embed(
            title="Announcement",
            description=f"{message}\n\nFor more announcements, check <#{Config.ANNOUNCEMENTS_CHANNEL_ID}>",
            color=Config.EMBED_COLOR_PRIMARY
        )
        announcement.set_footer(text=f"Announced by {ctx.author.name} | Channel: #{ctx.channel.name}")
        await ctx.send(embed=announcement)
    
    
    
   # ========== ADMIN COMMANDS ==========
    @commands.command(name="sagad")
    @commands.check(lambda ctx: any(role.id in [1345727357662658603, 1345727357645885449, 1345727357645885448] for role in ctx.author.roles))  # Multiple admin roles check
    async def sagad(self, ctx, amount: int, member: discord.Member):
        """Add coins to a user's balance"""
        if amount <= 0:
         return await ctx.send("**TANGA!** WALANG NEGATIVE O ZERO NA AMOUNT!", delete_after=10)
        if not member:
         return await ctx.send("**BOBO!** WALA KANG TINUKOY NA USER!", delete_after=10)

        self.add_coins(member.id, amount)
        await ctx.send(
        f"**ETO NA TOL GALING KAY BOSS MASON!** NAG-DAGDAG KA NG **₱{amount:,}** KAY {member.mention}! WAG MO ABUSUHIN YAN!",
        delete_after=10
    )


    @commands.command(name="bawas")
    @commands.check(lambda ctx: any(role.id in [1345727357662658603, 1345727357645885449, 1345727357645885448] for role in ctx.author.roles))  # Multiple admin roles check
    async def bawas(self, ctx, amount: int, member: discord.Member):
     """Deduct coins from a user's balance"""
     if amount <= 0:
         return await ctx.send("**TANGA!** WALANG NEGATIVE O ZERO NA AMOUNT!", delete_after=10)
     if not member:
         return await ctx.send("**BOBO!** WALA KANG TINUKOY NA USER!", delete_after=10)
     if self.user_coins.get(member.id, 0) < amount:
         return await ctx.send(f"**WALA KANG PERA!** {member.mention} BALANCE MO: **₱{self.user_coins.get(member.id, 0):,}**", delete_after=10)

     self.add_coins(member.id, -amount)  # Deduct coins
     await ctx.send(
         f"**BINAWASAN NI BOSS MASON KASI TANGA KA!** {member.mention} lost **₱{amount:,}**. "
         f"New balance: **₱{self.user_coins.get(member.id, 0):,}**",
         delete_after=10
      )


    @commands.command(name="goodmorning")
    @commands.check(lambda ctx: any(role.id in [1345727357662658603, 1345727357645885449, 1345727357645885448] for role in ctx.author.roles))  # Multiple admin roles check
    async def goodmorning(self, ctx):
        """Manually trigger a good morning greeting"""
        # Get the greetings channel
        channel = self.bot.get_channel(Config.GREETINGS_CHANNEL_ID)
        if not channel:
            await ctx.send("**ERROR:** Hindi mahanap ang greetings channel!")
            return
            
        # Get all online members
        online_members = [member for member in channel.guild.members 
                         if member.status == discord.Status.online and not member.bot]
        
        # If there are online members, mention them
        if online_members:
            mentions = " ".join([member.mention for member in online_members])
            morning_messages = [
                f"**MAGANDANG UMAGA MGA GAGO!** {mentions} GISING NA KAYO! DALI DALI TRABAHO NA!",
                f"**RISE AND SHINE MGA BOBO!** {mentions} TANGINA NIYO GISING NA! PRODUCTIVITY TIME!",
                f"**GOOD MORNING MOTHERFUCKERS!** {mentions} WELCOME TO ANOTHER DAY OF YOUR PATHETIC LIVES!",
                f"**HOY GISING NA!** {mentions} TANGHALI NA GAGO! DALI DALI MAG-TRABAHO KA NA!",
                f"**AYAN! UMAGA NA!** {mentions} BILISAN MO NA! SIBAT NA SA TRABAHO!"
            ]
            await channel.send(random.choice(morning_messages))
            await ctx.send("**NAPA-GOODMORNING MO ANG MGA TANGA!**")
        else:
            await ctx.send("**WALANG ONLINE NA TANGA!** Walang imemention!")
            
    @commands.command(name="test")
    @commands.check(lambda ctx: any(role.id in [1345727357662658603, 1345727357645885449, 1345727357645885448] for role in ctx.author.roles))  # Multiple admin roles check
    async def test(self, ctx):
        """Admin test command to curse at all online users"""
        # Get the specific channel where the curse will be sent
        greetings_channel = self.bot.get_channel(1345727358149328952)
        if not greetings_channel:
            await ctx.send("**ERROR:** Hindi mahanap ang greetings channel!")
            return
            
        # Get all online, idle, and DND users
        all_active_users = [member for member in ctx.guild.members 
                     if (member.status == discord.Status.online or 
                         member.status == discord.Status.idle or 
                         member.status == discord.Status.dnd) and 
                         not member.bot and member.id != ctx.author.id]
        
        if not all_active_users:
            await ctx.send("**WALANG ONLINE NA TANGA!** Walang babastusin!")
            return
            
        # Get current hour in Philippines timezone to determine greeting
        ph_timezone = pytz.timezone('Asia/Manila')
        now = datetime.datetime.now(ph_timezone)
        current_hour = now.hour
        greeting = ""
        if 5 <= current_hour < 12:
            greeting = "GOOD MORNING"
        elif 12 <= current_hour < 18:
            greeting = "GOOD AFTERNOON"
        else:
            greeting = "GOOD EVENING"
            
        # Format mentions with each one on a new line with a number
        mention_list = ""
        for i, member in enumerate(all_active_users, 1):
            mention_list += f"{i}. {member.mention}\n"
        
        # Create the bold message with hashtags for Discord markdown headers
        curse_message = f"# {greeting}! \n\n{mention_list}\n# PUTANGINA NIYONG LAHAT GISING NA KO!"
        
        # Send the curse in the specified channel
        await greetings_channel.send(curse_message)
        
        # Confirm to the command user
        await ctx.send(f"**NAPAMURA MO ANG MGA ONLINE NA TANGA SA GREETINGS CHANNEL!** HAHA!")
            
    @commands.command(name="goodnight")
    @commands.check(lambda ctx: any(role.id in [1345727357662658603, 1345727357645885449, 1345727357645885448] for role in ctx.author.roles))  # Multiple admin roles check
    async def goodnight(self, ctx):
        """Manually trigger a good night greeting"""
        # Get the greetings channel
        channel = self.bot.get_channel(Config.GREETINGS_CHANNEL_ID)
        if not channel:
            await ctx.send("**ERROR:** Hindi mahanap ang greetings channel!")
            return
        
        night_messages = [
            "**TULOG NA MGA GAGO!** TANGINANG MGA YAN PUYAT PA MORE! UUBUSIN NIYO BUHAY NIYO SA DISCORD? MAAGA PA PASOK BUKAS!",
            "**GOOD NIGHT MGA HAYOP!** MATULOG NA KAYO WALA KAYONG MAPAPALA SA PAGIGING PUYAT!",
            "**HUWAG NA KAYO MAG-PUYAT GAGO!** MAAWA KAYO SA KATAWAN NIYO! PUTA TULOG NA KAYO!",
            "**10PM NA GAGO!** TULOG NA MGA WALA KAYONG DISIPLINA SA BUHAY! BILIS!",
            "**TANGINANG MGA TO! MAG TULOG NA KAYO!** WALA BA KAYONG TRABAHO BUKAS? UUBUSIN NIYO ORAS NIYO DITO SA DISCORD!"
        ]
        
        await channel.send(random.choice(night_messages))
        await ctx.send("**PINATULOG MO NA ANG MGA TANGA!**")
        
    @commands.command(name="g")
    @commands.check(lambda ctx: any(role.id in [1345727357662658603, 1345727357645885449, 1345727357645885448] for role in ctx.author.roles))  # Multiple admin roles check
    async def ghost_message(self, ctx, channel_id: int, *, message: str):
        """Send a message to a specific channel as the bot (g!g <channel_id> <message>)"""
        # Delete the original command message for stealth
        await ctx.message.delete()
        
        # Try to get the specified channel
        target_channel = self.bot.get_channel(channel_id)
        if not target_channel:
            # Send error as DM to avoid revealing the command usage
            try:
                await ctx.author.send(f"**ERROR:** Hindi mahanap ang channel na may ID `{channel_id}`!")
            except:
                # If DM fails, send quietly in the current channel and delete after 5 seconds
                await ctx.send(f"**ERROR:** Hindi mahanap ang channel!", delete_after=5)
            return
        
        # Send the message to the target channel
        await target_channel.send(message)
        
        # Confirm to the command user via DM
        try:
            await ctx.author.send(f"**MESSAGE SENT SUCCESSFULLY!** Message sent to channel: {target_channel.name} ({channel_id})")
        except:
            # If DM fails, send quietly in current channel and delete after 5 seconds
            await ctx.send("**MESSAGE SENT!**", delete_after=5)
            
    @commands.command(name="commandslist")
    @commands.check(lambda ctx: any(role.id in [1345727357662658603, 1345727357645885449, 1345727357645885448] for role in ctx.author.roles))  # Multiple admin roles check
    async def commandslist(self, ctx):
        """Admin command panel - comprehensive list of all commands for admins"""
        # Create embed for all commands (admin and regular)
        embed = discord.Embed(
            title="**🔑 GNSLG COMMAND MASTER LIST 🔑**",
            description="**KOMPLETONG LISTA NG LAHAT NG COMMANDS PARA SA MGA MODERATOR:**",
            color=Config.EMBED_COLOR_PRIMARY
        )
        
        # All admin-only commands
        admin_commands = {
            "g!admin": "Ipakita ang basic admin commands",
            "g!commandslist": "Ipakita ang lahat ng commands (ito mismo)",
            "g!sagad <amount> <@user>": "Dagdagan ang pera ng isang user",
            "g!bawas <amount> <@user>": "Bawasan ang pera ng isang user",
            "g!goodmorning": "Mag-send ng good morning message sa greetings channel",
            "g!goodnight": "Mag-send ng good night message sa greetings channel",
            "g!test": "Pagmumurahin lahat ng online users (mention them all)",
            "g!g <channel_id> <message>": "Mag-send ng message sa ibang channel nang patago",
            "g!vc <message>": "Text-to-speech sa voice channel (lalaki sa voice channel)"
        }
        
        # Regular commands that admins can also use
        economy_commands = {
            "g!daily": "Claim daily ₱10,000",
            "g!balance": "Check your balance",
            "g!give <@user> <amount>": "Transfer money",
            "g!leaderboard": "Top 20 richest players"
        }
        
        game_commands = {
            "g!toss <h/t> <bet>": "Coin flip game",
            "g!blackjack <bet> (or g!bj)": "Play Blackjack",
            "g!hit": "Draw a card in Blackjack", 
            "g!stand": "End your turn in Blackjack"
        }
        
        chat_commands = {
            "g!usap <message>": "Chat with the AI assistant",
            "@Ginsilog BOT <message>": "Mention the bot to chat",
            "g!clear": "Clear chat history"
        }
        
        utility_commands = {
            "g!join/leave": "Voice channel management",
            "g!rules": "Server rules",
            "g!announcement <message>": "Make an announcement",
            "g!tulong": "Show help for regular users"
        }
        
        # Add each category as a field
        admin_text = ""
        for cmd, desc in admin_commands.items():
            admin_text += f"• **{cmd}**: {desc}\n"
        
        embed.add_field(
            name="**🛡️ ADMIN COMMANDS (MODERATOR ROLES ONLY):**",
            value=admin_text,
            inline=False
        )
        
        economy_text = ""
        for cmd, desc in economy_commands.items():
            economy_text += f"• **{cmd}**: {desc}\n"
        
        embed.add_field(
            name="**💰 ECONOMY COMMANDS:**",
            value=economy_text,
            inline=False
        )
        
        game_text = ""
        for cmd, desc in game_commands.items():
            game_text += f"• **{cmd}**: {desc}\n"
        
        embed.add_field(
            name="**🎮 GAME COMMANDS:**",
            value=game_text,
            inline=False
        )
        
        chat_text = ""
        for cmd, desc in chat_commands.items():
            chat_text += f"• **{cmd}**: {desc}\n"
        
        embed.add_field(
            name="**🤖 AI CHAT COMMANDS:**",
            value=chat_text,
            inline=False
        )
        
        utility_text = ""
        for cmd, desc in utility_commands.items():
            utility_text += f"• **{cmd}**: {desc}\n"
        
        embed.add_field(
            name="**🔧 UTILITY COMMANDS:**",
            value=utility_text,
            inline=False
        )
        
        embed.set_footer(text="MASTER LIST! PARA SA MODERATOR LANG! | Ginsilog Command System")
        
        # Send the embed in the channel
        await ctx.send(embed=embed)
    
    @commands.command(name="admin")
    async def admin(self, ctx):
        """Admin command panel - only visible to admins"""
        # Check if user has admin roles
        admin_roles = [1345727357662658603, 1345727357645885449, 1345727357645885448]
        user_roles = [role.id for role in ctx.author.roles]
        
        # Check if user has any of the specified admin roles
        is_admin = any(role_id in admin_roles for role_id in user_roles)
        
        if not is_admin:
            await ctx.send("**HINDI KA ADMIN GAGO!** Wala kang access sa command na 'to!", delete_after=10)
            return
        
        # Create embed for admin commands
        embed = discord.Embed(
            title="**🔑 GINSILOG ADMIN COMMANDS 🔑**",
            description="**LISTA NG MGA ADMIN COMMANDS PARA SA MGA BOSS:**",
            color=Config.EMBED_COLOR_PRIMARY
        )
        
        # List all admin commands
        admin_commands = {
            "g!admin": "Ipakita ang lahat ng admin commands (ito mismo)",
            "g!commandslist": "Ipakita ang master list ng lahat ng commands",
            "g!sagad <amount> <@user>": "Dagdagan ang pera ng isang user",
            "g!bawas <amount> <@user>": "Bawasan ang pera ng isang user",
            "g!goodmorning": "Mag-send ng good morning message sa greetings channel",
            "g!goodnight": "Mag-send ng good night message sa greetings channel",
            "g!test": "Pagmumurahin lahat ng online users (mention them all)",
            "g!g <channel_id> <message>": "Mag-send ng message sa ibang channel nang patago",
            "g!vc <message>": "Text-to-speech sa voice channel (lalaki sa voice channel)"
        }
        
        command_text = ""
        for cmd, desc in admin_commands.items():
            command_text += f"• **{cmd}**: {desc}\n"
        
        embed.add_field(
            name="**AVAILABLE ADMIN COMMANDS:**",
            value=command_text,
            inline=False
        )
        
        embed.set_footer(text="ADMIN LANG PWEDE GUMAMIT NITO! | Ginsilog Admin Panel")
        
        # Send the embed in the channel
        await ctx.send(embed=embed)
    
    @commands.command(name="leaderboard")
    async def leaderboard(self, ctx):
        """Display wealth rankings"""
        # Sort users by their coin balance in descending order
        sorted_users = sorted(self.user_coins.items(), key=lambda x: x[1], reverse=True)[:20]
        
        # Create the embed with cleaner design (fewer emojis)
        embed = discord.Embed(
            title="**GINSILOG LEADERBOARD - MAYAMAN VS. DUKHA**",
            description="**TANGINA MO! IKAW KAYA NASAAN DITO? SIGURADONG WALA KA DITO KASI WALA KANG KWENTANG PLAYER!**\n\n" + 
                       "**TOP MAYAMAN NG SERVER**",
            color=Config.EMBED_COLOR_PRIMARY
        )
        
        # Create a formatted leaderboard with cleaner styling
        leaderboard_text = ""
        
        for idx, (user_id, coins) in enumerate(sorted_users):
            # Fetch the member object
            member = ctx.guild.get_member(user_id)
            user_name = member.display_name if member else "Unknown User"
            
            # Add position with proper formatting but fewer emojis
            position = idx + 1
            
            # Add insults for bottom ranks, praise for top ranks (with fewer emojis)
            if idx < 3:
                suffix = "MAYAMAN NA MAYAMAN!"
            elif idx < 10:
                suffix = "SAKTO LANG PERA"
            else:
                suffix = "MAHIRAP AMPUTA"
                
            leaderboard_text += f"`{position}.` **{user_name}** — **₱{coins:,}** *({suffix})*\n\n"
        
        embed.description += f"\n\n{leaderboard_text}"
        
        # Add motivational footer (insulting style but cleaner)
        embed.set_footer(text="DAPAT ANDITO KA SA TAAS! KUNGDI MAGTIPID KA GAGO! | Ginsilog Economy System")
        
        # Send the embed
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(ChatCog(bot))

