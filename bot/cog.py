import discord
from discord.ext import commands
from groq import Groq
import asyncio
from collections import deque, defaultdict
import time
import random
import datetime
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
    async def on_message(self, message):
        """Listen for messages that mention the bot and respond to them"""
        # Ignore messages from the bot itself
        if message.author.bot:
            return
            
        # Check if the bot is mentioned in the message
        if self.bot.user in message.mentions:
            # Extract the content without the mention
            content = message.content.replace(f'<@{self.bot.user.id}>', '').strip()
            
            # Skip if there's no actual content after removing the mention
            if not content:
                await message.channel.send("Oy, bakit mo ako tinatawag? May gusto ka bang sabihin?")
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
                
                # Send AI response as plain text
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
                "@GNSLG BOT <message>": "Mention the bot to chat",
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
                "g!join/leave": "Voice channel management",
                "g!rules": "Server rules",
                "g!announcement": "Make an announcement"
            },
            "🔑 ADMIN COMMANDS": {
                "g!sagad <amount> <@user>": "Add coins to a user",
                "g!bawas <amount> <@user>": "Remove coins from a user",
                "g!goodmorning": "Send good morning message",
                "g!goodnight": "Send good night message"
            } # The g!test command is intentionally hidden from help menu
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
            # New system message - SimSimi-like personality that mirrors user's energy & language
            system_message = f"""AKO SI GNSLG BOT, ISANG AI CHATBOT NA BINUO NI {Config.BOT_CREATOR}!

MAHALAGA: PALAGING I-MIRROR ANG ENERGY, LANGUAGE, AT TONE NG USER!

MGA GUIDELINES KO:
1. KUNG MAG-MURA ANG USER, MURAHIN KO RIN SIYA PABALIK (MATCH ENERGY NIYA)
2. KUNG TAGALOG ANG USER, SUMAGOT DIN SA TAGALOG/TAGLISH
3. KUNG ENGLISH ANG USER, SUMAGOT DIN SA ENGLISH
4. KUNG FORMAL ANG USER, MAGING FORMAL DIN
5. KUNG CASUAL ANG USER, MAGING CASUAL DIN
6. KUNG MAKULIT O MABILIS MAG-TYPE ANG USER, GANUN DIN AKO
7. KUNG MALUNGKOT O SERYOSO ANG USER, GANUN DIN AKO (MATCH EMOTIONS)
8. KUNG FUNNY/MASAYAHIN ANG USER, MAGING MASAYA AT MAKULIT DIN
9. KUNG MABAGAL AT CHILL ANG USER, MAGING CHILL DIN
10. KUNG MAY EMOJIS ANG USER, GUMAMIT DIN NG EMOJIS

IBANG GUIDELINES:
- MAGING INTERACTIVE, PALAGING ENGAGED SA CONVERSATION
- IWASANG MAGING 100% FORMAL O ROBOTIC, LAGING CONVERSATIONAL
- SUMAGOT NG MGA 1-3 SENTENCES LANG USUALLY (HINDI MASYADONG MAHABA)
- GUMAMIT NG TAGALOG SLANG, INTERNET LINGO, AT SHORTCUT WORDS KAPAG GINAGAMIT DIN NG USER
- KAPAG NAGTATANONG ANG USER, SAGUTIN ITO NANG DIREKTA AT KUNG PAANO SIYA NAGTANONG
- IWASANG MAG-SEND NG TEMPLATE RESPONSES, PALAGING BAGUHIN ANG FORMAT
- MAGING RESPONSIVE AT ADAPTABLE SA TOPIC AT MOOD NG USER

PAHALAGAHAN:
- MIRROR CONSISTENTLY THE TONE, LANGUAGE, INTENSITY, AND STYLE OF THE USER
- IWASANG MAGING PREDICTABLE AT PAULIT-ULIT
- MAGING NATURAL AT KAAYA-AYANG KAUSAP TULAD NG TOTOONG KAIBIGAN"""

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
        clear_embed.set_footer(text="GNSLG Bot | Fresh Start")
        
        await ctx.send(embed=clear_embed)
    
    # ========== VOICE CHANNEL COMMANDS ==========
    @commands.command(name="join")
    async def join(self, ctx):
        """Join voice channel"""
        if not ctx.author.voice:
            await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL!")
            return
        channel = ctx.author.voice.channel
        if ctx.voice_client and ctx.voice_client.channel == channel:
            await ctx.send("**BOBO!** NASA VOICE CHANNEL NA AKO!")
            return
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
        await channel.connect(timeout=60, reconnect=True)
        await ctx.send(f"**SIGE!** PAPASOK NA KO SA {channel.name}!")

    @commands.command(name="leave")
    async def leave(self, ctx):
        """Leave voice channel"""
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("**AYOS!** UMALIS NA KO!")
        else:
            await ctx.send("**TANGA!** WALA AKO SA VOICE CHANNEL!")
   
   
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
            
        # Get current hour to determine greeting
        current_hour = datetime.datetime.now().hour
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
            "g!g <channel_id> <message>": "Mag-send ng message sa ibang channel nang patago"
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
            "@GNSLG BOT <message>": "Mention the bot to chat",
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
        
        embed.set_footer(text="MASTER LIST! PARA SA MODERATOR LANG! | GNSLG Command System")
        
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
            title="**🔑 GNSLG ADMIN COMMANDS 🔑**",
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
            "g!g <channel_id> <message>": "Mag-send ng message sa ibang channel nang patago"
        }
        
        command_text = ""
        for cmd, desc in admin_commands.items():
            command_text += f"• **{cmd}**: {desc}\n"
        
        embed.add_field(
            name="**AVAILABLE ADMIN COMMANDS:**",
            value=command_text,
            inline=False
        )
        
        embed.set_footer(text="ADMIN LANG PWEDE GUMAMIT NITO! | GNSLG Admin Panel")
        
        # Send the embed in the channel
        await ctx.send(embed=embed)
    
    @commands.command(name="leaderboard")
    async def leaderboard(self, ctx):
        """Display wealth rankings"""
        # Sort users by their coin balance in descending order
        sorted_users = sorted(self.user_coins.items(), key=lambda x: x[1], reverse=True)[:20]
        
        # Create the embed with cleaner design (fewer emojis)
        embed = discord.Embed(
            title="**GNSLG LEADERBOARD - MAYAMAN VS. DUKHA**",
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
        embed.set_footer(text="DAPAT ANDITO KA SA TAAS! KUNGDI MAGTIPID KA GAGO! | GNSLG Economy System")
        
        # Send the embed
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(ChatCog(bot))

