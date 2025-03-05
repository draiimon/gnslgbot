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
        self.groq_client = Groq(api_key=Config.GROQ_API_KEY)
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
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    # ========== HELP COMMAND ==========
    @commands.command(name="tulong")
    async def tulong(self, ctx):
        """Display all available commands"""
        embed = discord.Embed(
            title="📚 **BOT COMMAND GUIDE**",
            description="ITO MGA COMMAND NA PWEDE MO GAMITIN:",
            color=discord.Color.gold()
        )
        
        categories = {
            "🤖 AI CHAT": {
                "g!usap <message>": "Chat with the AI assistant",
                "g!ask <question>": "One-time question session",
                "g!clear": "Clear chat history"
            },
            "💰 ECONOMY": {
                "g!daily": "Claim daily ₱10,000",
                "g!balance": "Check your balance",
                "g!give <@user> <amount>": "Transfer money",
                "g!leaderboard": "Top 10 richest players"
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
            }
        }

        for category, commands in categories.items():
            embed.add_field(
                name=f"**{category}**",
                value="\n".join([f"• `{cmd}`: {desc}" for cmd, desc in commands.items()]),
                inline=False
            )

        embed.set_footer(text=f"Bot created by {self.creator}")
        await ctx.send(embed=embed)

    # ========== OTHER COMMANDS ==========
    @commands.command(name="balance")
    async def balance(self, ctx):
        """Check your current balance"""
        balance = self.get_user_balance(ctx.author.id)
        embed = discord.Embed(
            title="💰 **ACCOUNT BALANCE**",
            description=f"{ctx.author.mention}'s balance: **₱{balance:,}**",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    # ========== AI CHAT COMMANDS ==========
    async def get_ai_response(self, conversation_history):
        """Get response from Groq AI with conversation context"""
        try:
            messages = [
                {"role": "system", "content": "AKO SI GNSLG BOT AT AKO ANG IYONG AI ASSISTANT! ANONG MAITUTULONG KO SAYO? GAGO? TAGALOG ONLY"}
            ]
            for msg in conversation_history:
                messages.append({
                    "role": "user" if msg["is_user"] else "ASSISTANT MO GAGO",
                    "content": msg["content"]
                })
            completion = await asyncio.to_thread(
                self.groq_client.chat.completions.create,
                model=Config.GROQ_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=800
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"Error getting AI response: {e}")
            return "Sorry, I encountered an error. Please try again later."

    @commands.command(name="usap")
    async def usap(self, ctx, *, message: str):
        """Chat with GROQ AI"""
        if self.is_rate_limited(ctx.author.id):
            await ctx.send(f"Hi {ctx.author.mention}, you're sending messages too quickly. Please wait a moment before trying again.")
            return
        self.user_message_timestamps[ctx.author.id].append(time.time())
        channel_history = list(self.conversation_history[ctx.channel.id])
        channel_history.append({"is_user": True, "content": message})
        async with ctx.typing():
            response = await self.get_ai_response(channel_history)
            self.add_to_conversation(ctx.channel.id, True, message)
            self.add_to_conversation(ctx.channel.id, False, response)
            await ctx.send(f"{ctx.author.mention} {response}")

    @commands.command(name="ask")
    async def ask(self, ctx, *, question):
        """Ask the AI a one-off question without storing conversation"""
        async with ctx.typing():
            response = await self.get_ai_response([{"is_user": True, "content": question}])
            await ctx.send(f"{ctx.author.mention} {response}")

    @commands.command(name="clear")
    async def clear_history(self, ctx):
        """Clear the conversation history for the current channel"""
        self.conversation_history[ctx.channel.id].clear()
        await ctx.send("I've cleared our conversation history. We can start fresh now!")
    
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
        
        # Create the embed
        embed = discord.Embed(
            title="🏆 **GNSLG LEADERBOARD**",
            color=discord.Color.blurple()
        )
        
        # Loop through the top 20 users
        for idx, (user_id, coins) in enumerate(sorted_users):
            # Mention the user directly
            user_mention = f"@{user_id}"
            embed.add_field(
                name=f"{idx+1}. {user_mention}",
                value=f"**₱{coins:,}**",
                inline=False
            )
        
        # Send the embed
        await ctx.send(embed=embed)
    

def setup(bot):
    bot.add_cog(ChatCog(bot))

