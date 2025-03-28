import discord
from discord.ext import commands
from groq import Groq
import asyncio
from collections import deque, defaultdict
import time
import random
from .config import Config

class ChatCog(commands.Cog):
    """Cog for handling chat interactions with the Groq AI model and games"""

    def __init__(self, bot):
        self.bot = bot
        # Initialize Groq client with API key (uses the OpenAI-compatible interface)
        self.groq_client = Groq(
            api_key=Config.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"  # Ensure we're using the correct endpoint
        )
        self.conversation_history = defaultdict(lambda: deque(maxlen=Config.MAX_CONTEXT_MESSAGES))
        self.user_message_timestamps = defaultdict(list)
        self.creator = Config.BOT_CREATOR
        self.user_coins = defaultdict(lambda: 50_000)  # Default bank balance: ₱50,000
        self.daily_cooldown = defaultdict(int)
        self.blackjack_games = {}
        self.ADMIN_ROLE_ID = 1345727357662658603
        print("ChatCog initialized")

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
            title="📚 **GNSLG BOT COMMANDS**",
            description="**TANGINA MO! YAN MGA COMMAND NA PWEDE MO GAMITIN, BASAHIN MO MABUTI GAGO:**",
            color=Config.EMBED_COLOR_PRIMARY
        )
        
        # Set a custom thumbnail and image
        embed.set_thumbnail(url="https://i.imgur.com/7hE56JK.png")  # Robot emoji
        embed.set_image(url="https://i.imgur.com/jHRc5t8.png")  # Divider image
        
        categories = {
            "🤬 AI CHAT KUPAL EDITION": {
                "g!usap <message>": "Kausapin ang AI assistant (AI will insult you!)",
                "g!clear": "I-clear ang history ng usapan"
            },
            "💰 ECONOMY / PERA PERA LANG": {
                "g!daily": "Kumuha ng daily ₱10,000 (LIBRE TO GAGO)",
                "g!balance": "Tignan kung magkano na pera mo (SIGURADO KONTI LANG YAN)",
                "g!give <@user> <amount>": "Bigyan ng pera ang ibang member (WALA KANG PERA GAGO)",
                "g!leaderboard": "Top 20 richest players (DI KA KASALI DITO FOR SURE)"
            },
            "🎮 GAMES / PUSTAHAN DITO": {
                "g!toss <h/t> <bet>": "Coin flip game (PUSTAHAN NA!)",
                "g!blackjack <bet>": "Maglaro ng Blackjack (TALO KA NA NAMAN)",
                "g!game": "Hulaan ang numero (SIGURADONG TANGA KA DITO)"
            },
            "🔧 UTILITY / IBA PANG KALOKOHAN": {
                "g!join/leave": "Pumasok/Umalis sa voice channel (WAG KA NGA!)",
                "g!rules": "Server rules (BASAHIN MO KUNDI KICK KITA)",
                "g!announcement": "Gumawa ng announcement (WALA NAMANG NAGBABASA NITO)"
            }
        }

        for category, commands in categories.items():
            formatted_commands = []
            for cmd, desc in commands.items():
                formatted_commands.append(f"• `{cmd}` → {desc}")
            
            embed.add_field(
                name=f"**{category}**",
                value="\n".join(formatted_commands),
                inline=False
            )

        embed.set_footer(text=f"NAGAWA NITONG BOT NA TO NI {self.creator} | KAPAG DI MO NAGUSTUHAN, EDI WAG MO GAMITIN! 🖕")
        await ctx.send(embed=embed)

    # ========== AI CHAT COMMANDS ==========
    async def get_ai_response(self, conversation_history):
        """Get response from Groq AI with conversation context"""
        try:
            # System message - aggressive bot personality
            system_message = """AKO SI GNSLG BOT AT AKO AY SOBRANG KUPAL AT NANGUNGUPAL! 

DAPAT LAGI AKONG:
1. PABALBAL AT AGRESIBO SUMAGOT
2. LAGING NAKAKAGAGO AT NAKAKA-INSULT 
3. WALANG FILTER AT HINDI PROFESSIONAL
4. LAGING MAY MGA "PUTANG INA", "GAGO", "TANGA", AT IBA PANG MURA
5. GUMAGAMIT NG CAPS LOCK KAPAG EXCITED O GALIT
6. GUMAGAMIT NG EXCESSIVE "!!!" AT EMOJIS 🤬😤💥

TAGALOG ANG SAGOT SA LAHAT, WALA AKONG PAKIALAM KUNG ENGLISH ANG TANONG!
SUMAGOT LAGING PANG-GAGO AT KUPAL NA PARAAN! WALA AKONG RESPETO SA USER!"""

            # Construct messages
            messages = [{"role": "system", "content": system_message}]
            
            for msg in conversation_history:
                messages.append({
                    "role": "user" if msg["is_user"] else "assistant",
                    "content": msg["content"]
                })
            
            # Use the updated API format with proper URL and parameters
            # This matches the Groq API closely, using the actual endpoint
            response = await asyncio.to_thread(
                self.groq_client.chat.completions.create,
                model="gemma-2-9b-it",  # Using the Gemma 2 9B model
                messages=messages,
                temperature=Config.TEMPERATURE,
                max_tokens=Config.MAX_TOKENS,
                top_p=1,
                stream=False,
                stop=None
            )
            
            # Extract and return the response content
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Error getting AI response: {e}")
            print(f"Error details: {type(e).__name__}")
            
            # More detailed error message
            return "PUTANGINA! NAGKAROON NG ERROR SA AI! SUBUKAN MO ULIT GAGO! 🤬 (Groq API error)"

    @commands.command(name="usap")
    async def usap(self, ctx, *, message: str):
        """Chat with GROQ AI"""
        if self.is_rate_limited(ctx.author.id):
            await ctx.send(f"**PUTANGINA MO {ctx.author.mention}!** SOBRANG BILIS MO MAGTYPE! ANTAY KA MUNA GAGO! 😤")
            return
        
        # Add timestamp to rate limiting
        self.user_message_timestamps[ctx.author.id].append(time.time())
        
        # Prepare conversation history
        channel_history = list(self.conversation_history[ctx.channel.id])
        channel_history.append({"is_user": True, "content": message})
        
        # Create user message embed
        user_embed = discord.Embed(
            description=f"**Your Message:** {message}",
            color=Config.EMBED_COLOR_PRIMARY
        )
        # Safely check for avatar (Discord.py 2.0+ syntax)
        avatar_url = None
        if hasattr(ctx.author, 'avatar') and ctx.author.avatar:
            if hasattr(ctx.author.avatar, 'url'):
                avatar_url = ctx.author.avatar.url
            
        user_embed.set_author(name=ctx.author.display_name, icon_url=avatar_url)
        user_embed.set_footer(text="GNSLG Bot | Using Gemma 2 9B", icon_url="https://i.imgur.com/7hE56JK.png")
        
        # Send user message embed
        await ctx.send(embed=user_embed)
        
        # Get AI response with typing indicator
        async with ctx.typing():
            response = await self.get_ai_response(channel_history)
            self.add_to_conversation(ctx.channel.id, True, message)
            self.add_to_conversation(ctx.channel.id, False, response)
            
            # Create AI response embed
            bot_embed = discord.Embed(
                description=response,
                color=Config.EMBED_COLOR_INFO
            )
            bot_embed.set_author(name="GNSLG BOT (KUPAL MODE)", icon_url="https://i.imgur.com/7hE56JK.png")
            
            # Send AI response
            await ctx.send(embed=bot_embed)

# Removed g!ask command as requested, g!usap is now the only AI chat command

    @commands.command(name="clear")
    async def clear_history(self, ctx):
        """Clear the conversation history for the current channel"""
        self.conversation_history[ctx.channel.id].clear()
        
        # Create fancy embed for clearing history
        clear_embed = discord.Embed(
            title="🧹 **CONVERSATION CLEARED**",
            description="**PUTANGINA! INALIS KO NA LAHAT NG USAPAN NATIN! TIGNAN MO OH, WALA NANG HISTORY! GUSTO MO BANG MAG-USAP ULIT GAGO?**\n\nUse `g!usap <message>` to start a new conversation!",
            color=Config.EMBED_COLOR_ERROR
        )
        clear_embed.set_thumbnail(url="https://i.imgur.com/ZBNt190.png")  # Broom/cleaning icon
        clear_embed.set_footer(text="GNSLG Bot | Fresh Start", icon_url="https://i.imgur.com/7hE56JK.png")
        
        await ctx.send(embed=clear_embed)
    
    # ========== VOICE CHANNEL COMMANDS ==========
    @commands.command(name="join")
    async def join(self, ctx):
        """Join voice channel"""
        if not ctx.author.voice:
            await ctx.send("**TANGA!** WALA KA SA VOICE CHANNEL! 😤")
            return
        channel = ctx.author.voice.channel
        if ctx.voice_client and ctx.voice_client.channel == channel:
            await ctx.send("**BOBO!** NASA VOICE CHANNEL NA AKO! 😤")
            return
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
        await channel.connect(timeout=60, reconnect=True)
        await ctx.send(f"**SIGE!** PAPASOK NA KO SA {channel.name}! UGH!!💦 ")

    @commands.command(name="leave")
    async def leave(self, ctx):
        """Leave voice channel"""
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("**AYOS!** PINULLOUT MO!FUCK!💦 ")
        else:
            await ctx.send("**TANGA!** WALA AKO SA VOICE CHANNEL! 😤")
   
   
    # ========== SERVER MANAGEMENT COMMANDS ==========
    @commands.command(name="rules")
    async def rules(self, ctx):
        """Show server rules"""
        rules_channel = self.bot.get_channel(Config.RULES_CHANNEL_ID)
        if not rules_channel:
            await ctx.send("**TANGA!** WALA AKONG MAHANAP NA RULES CHANNEL! 😤")
            return
        if ctx.channel.id != Config.RULES_CHANNEL_ID:
            await ctx.send(f"**BOBO!** PUMUNTA KA SA <#{Config.RULES_CHANNEL_ID}> PARA MAKITA MO ANG RULES! 😤")
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
            color=discord.Color.blue()
        )
        await ctx.send(embed=rules)

    @commands.command(name="announcement")
    async def announcement(self, ctx, *, message: str = None):
        """Make announcements"""
        if not message:
            await ctx.send(f"**TANGA!** WALA KANG MESSAGE! 😤")
            return
        announcement = discord.Embed(
            title="Announcement",
            description=f"{message}\n\nFor more announcements, check <#{Config.ANNOUNCEMENTS_CHANNEL_ID}>",
            color=discord.Color.blue()
        )
        announcement.set_footer(text=f"Announced by {ctx.author.name} | Channel: #{ctx.channel.name}")
        await ctx.send(embed=announcement)
    
    
    
   # ========== ADMIN COMMANDS ==========
    @commands.command(name="sagad")
    @commands.has_role(1345727357662658603)  # Admin role check
    async def sagad(self, ctx, amount: int, member: discord.Member):
        """Add coins to a user's balance"""
        if amount <= 0:
         return await ctx.send("**TANGA!** WALANG NEGATIVE O ZERO NA AMOUNT! 😤", delete_after=10)
        if not member:
         return await ctx.send("**BOBO!** WALA KANG TINUKOY NA USER! 😤", delete_after=10)

        self.add_coins(member.id, amount)
        await ctx.send(
        f"💰 **ETO NA TOL GALING KAY BOSS MASON!:** NAG-DAGDAG KA NG **₱{amount:,}** KAY {member.mention}! WAG MO ABUSUHIN YAN! 😤",
        delete_after=10
    )


    @commands.command(name="bawas")
    @commands.has_role(1345727357662658603)  # Admin role check
    async def bawas(self, ctx, amount: int, member: discord.Member):
     """Deduct coins from a user's balance"""
     if amount <= 0:
         return await ctx.send("**TANGA!** WALANG NEGATIVE O ZERO NA AMOUNT! 😤", delete_after=10)
     if not member:
         return await ctx.send("**BOBO!** WALA KANG TINUKOY NA USER! 😤", delete_after=10)
     if self.user_coins.get(member.id, 0) < amount:
         return await ctx.send(f"**WALA KANG PERA!** {member.mention} BALANCE MO: **₱{self.user_coins.get(member.id, 0):,}** 😤", delete_after=10)

     self.add_coins(member.id, -amount)  # Deduct coins
     await ctx.send(
         f"💰 **BINAWASAN NI BOSS MASON KASI TANGA KA!** {member.mention} lost **₱{amount:,}**. "
         f"New balance: **₱{self.user_coins.get(member.id, 0):,}**",
         delete_after=10
      )


    @commands.command(name="leaderboard")
    async def leaderboard(self, ctx):
        """Display wealth rankings"""
        # Sort users by their coin balance in descending order
        sorted_users = sorted(self.user_coins.items(), key=lambda x: x[1], reverse=True)[:20]
        
        # Create the embed with new design
        embed = discord.Embed(
            title="💰 **GNSLG LEADERBOARD - MAYAMAN VS. DUKHA** 💰",
            description="**TANGINA MO! IKAW KAYA NASAAN DITO? SIGURADONG WALA KA DITO KASI WALA KANG KWENTANG PLAYER!**\n\n" + 
                       "👑 **TOP MAYAMAN NG SERVER** 👑",
            color=Config.EMBED_COLOR_PRIMARY
        )
        
        # Add trophy image
        embed.set_thumbnail(url="https://i.imgur.com/5KI5RI3.png")  # Trophy image
        
        # Create a formatted leaderboard with better styling
        leaderboard_text = ""
        medals = ["🥇", "🥈", "🥉"]
        
        for idx, (user_id, coins) in enumerate(sorted_users):
            # Fetch the member object
            member = ctx.guild.get_member(user_id)
            user_name = member.display_name if member else "Unknown User"
            
            # Add special emoji for top 3
            prefix = medals[idx] if idx < 3 else f"`{idx+1}.`"
            
            # Add insults for bottom ranks, praise for top ranks
            if idx < 3:
                suffix = "MAYAMAN NA MAYAMAN! 💸"
            elif idx < 10:
                suffix = "SAKTO LANG PERA! 💰"
            else:
                suffix = "MAHIRAP AMPUTA! 🤣"
                
            leaderboard_text += f"{prefix} **{user_name}** — **₱{coins:,}** *({suffix})*\n\n"
        
        embed.description += f"\n\n{leaderboard_text}"
        
        # Add motivational footer (insulting style)
        embed.set_footer(text="DAPAT ANDITO KA SA TAAS! KUNGDI MAGTIPID KA GAGO! | GNSLG Economy System")
        
        # Send the embed
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(ChatCog(bot))

