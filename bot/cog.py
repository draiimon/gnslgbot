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
        return self.user_coins.get(user_id, 50_000)

    def add_coins(self, user_id, amount):
        self.user_coins[user_id] += amount
        return self.user_coins[user_id]

    def deduct_coins(self, user_id, amount):
        if self.user_coins[user_id] >= amount:
            self.user_coins[user_id] -= amount
            return True
        return False

    # ========== ECONOMY COMMANDS ==========
    @commands.command(name="daily")
    async def daily(self, ctx):
        """Claim your daily ₱10,000 pesos"""
        current_time = time.time()
        last_claim = self.daily_cooldown.get(ctx.author.id, 0)

        if current_time - last_claim < 86400:
            await ctx.send(f"{ctx.author.mention} Please wait 24 hours before claiming again!")
            return

        self.daily_cooldown[ctx.author.id] = current_time
        self.add_coins(ctx.author.id, 10_000)
        await ctx.send(f"🎉 {ctx.author.mention} Daily ₱10,000 claimed! New balance: ₱{self.get_user_balance(ctx.author.id):,}")

    @commands.command(name="give")
    async def give(self, ctx, member: discord.Member, amount: int):
        """Transfer money to another user"""
        if amount <= 0:
            return await ctx.send("Please enter a positive amount.")
            
        if not self.deduct_coins(ctx.author.id, amount):
            return await ctx.send("Insufficient funds!")
            
        self.add_coins(member.id, amount)
        await ctx.send(f"💸 {ctx.author.mention} transferred ₱{amount:,} to {member.mention}!")

    # ========== GAME COMMANDS ==========
    @commands.command(name="toss")
    async def toss(self, ctx, choice: str.lower, bet: int = 0):
        """Bet on heads (h) or tails (t)"""
        if choice not in ['h', 't']:
            return await ctx.send("Please choose 'h' for heads or 't' for tails!")
            
        if bet < 0:
            return await ctx.send("Please enter a positive bet amount.")
            
        if bet > 0 and not self.deduct_coins(ctx.author.id, bet):
            return await ctx.send(f"{ctx.author.mention} Insufficient funds! Balance: ₱{self.get_user_balance(ctx.author.id):,}")

        result = random.choice(['h', 't'])
        win_message = random.choice(["CONGRATULATIONS! 🎉", "YOU WON! 🏆", "NICE ONE! 👍"])
        lose_message = random.choice(["BOBO KA TALO KA! 😂", "BETTER LUCK NEXT TIME! 😢", "TALO! 🚫"])

        if choice == result:
            winnings = bet * 2
            self.add_coins(ctx.author.id, winnings)
            await ctx.send(f"🎲 **{win_message}**\nResult: {result.upper()}\nWon: ₱{winnings:,}!\nNew Balance: ₱{self.get_user_balance(ctx.author.id):,}")
        else:
            await ctx.send(f"🎲 **{lose_message}**\nResult: {result.upper()}\nLost: ₱{bet:,}\nBalance: ₱{self.get_user_balance(ctx.author.id):,}")

    # ========== ADMIN COMMANDS ==========
    @commands.command(name="sagad")
    @commands.has_role(1345727357662658603)
    async def sagad(self, ctx, amount: int, member: discord.Member):
        """Admin command to modify balances"""
        self.add_coins(member.id, amount)
        await ctx.send(f"💰 Admin override: Added ₱{amount:,} to {member.mention}'s account!", delete_after=10)

    # ========== HELP COMMAND ==========
    @commands.command(name="tulong")
    async def tulong(self, ctx):
        """Display all available commands"""
        embed = discord.Embed(
            title="📚 Bot Command Guide",
            description="Here's a list of available commands:",
            color=discord.Color.gold()
        )
        
        categories = {
            "🤖 AI Chat": {
                "g!usap <message>": "Chat with the AI assistant",
                "g!ask <question>": "One-time question session",
                "g!clear": "Clear chat history"
            },
            "💰 Economy": {
                "g!daily": "Claim daily ₱10,000",
                "g!balance": "Check your balance",
                "g!give <@user> <amount>": "Transfer money",
                "g!leaderboard": "Top 10 richest players"
            },
            "🎮 Games": {
                "g!toss <h/t> <bet>": "Coin flip game",
                "g!blackjack <bet>": "Play Blackjack",
                "g!game": "Number guessing game"
            },
            "🔧 Utility": {
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
            title="💰 Account Balance",
            description=f"{ctx.author.mention}'s balance: ₱{balance:,}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command(name="leaderboard")
    async def leaderboard(self, ctx):
        """Display wealth rankings"""
        sorted_users = sorted(self.user_coins.items(), key=lambda x: x[1], reverse=True)[:10]
        
        embed = discord.Embed(
            title="🏆 Wealth Leaderboard",
            color=discord.Color.blurple()
        )
        
        for idx, (user_id, coins) in enumerate(sorted_users):
            user = self.bot.get_user(user_id) or "Unknown User"
            embed.add_field(
                name=f"{idx+1}. {user}",
                value=f"₱{coins:,}",
                inline=False
            )
            
        await ctx.send(embed=embed)

 @commands.command(name="help")
    async def help(self, ctx):
        """Redirect users to use g!tulong instead"""
        await ctx.send("Please use `g!tulong` to see the list of available commands!")

    @commands.command(name="creator")
    async def show_creator(self, ctx):
        """Show bot creator info"""
        creator_embed = discord.Embed(
            title="Bot Creator",
            description=f"This bot was created by {self.creator}",
            color=discord.Color.gold()
        )
        await ctx.send(embed=creator_embed)

    # Server management commands
    @commands.command(name="rules")
    async def rules(self, ctx):
        """Show server rules"""
        rules_channel = self.bot.get_channel(Config.RULES_CHANNEL_ID)

        if not rules_channel:
            await ctx.send("I couldn't find the rules channel!")
            return

        if ctx.channel.id != Config.RULES_CHANNEL_ID:
            await ctx.send(f"Please check the rules in <#{Config.RULES_CHANNEL_ID}>")
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
            await ctx.send(f"Please provide a message to announce. You can post announcements in <#{Config.ANNOUNCEMENTS_CHANNEL_ID}>")
            return

        announcement = discord.Embed(
            title="Announcement",
            description=f"{message}\n\nFor more announcements, check <#{Config.ANNOUNCEMENTS_CHANNEL_ID}>",
            color=discord.Color.blue()
        )
        announcement.set_footer(text=f"Announced by {ctx.author.name} | Channel: #{ctx.channel.name}")
        await ctx.send(embed=announcement)

    # Entertainment commands
    @commands.command(name="game")
    async def game(self, ctx):
        """Start a simple number guessing game"""
        await ctx.send("🎮 Let's play a game! Guess my number between 1-10. Just type the number.")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        number = random.randint(1, 10)
        try:
            msg = await self.bot.wait_for('message', timeout=30.0, check=check)
            try:
                guess = int(msg.content)
                if guess == number:
                    await ctx.send("Congratulations! You guessed correctly!")
                else:
                    await ctx.send(f"Sorry, the correct answer was {number}. Better luck next time!")
            except ValueError:
                await ctx.send("Please enter a valid number next time!")
        except asyncio.TimeoutError:
            await ctx.send("Time's up! You didn't respond in time.")

    # Daily money system
    @commands.command(name="daily")
    async def daily(self, ctx):
        """Claim 10k coins daily"""
        current_time = time.time()
        last_claim = self.daily_cooldown.get(ctx.author.id, 0)

        if current_time - last_claim < 86400:  # 24-hour cooldown
            await ctx.send(f"Ulol {ctx.author.mention}, kaka-claim mo lang ng daily mo! Balik ka bukas.")
            return

        self.daily_cooldown[ctx.author.id] = current_time
        self.add_coins(ctx.author.id, 10_000)
        await ctx.send(f"🎉 {ctx.author.mention}, you claimed your daily **10,000 coins**! New balance: {self.get_user_balance(ctx.author.id)}")

    # Games
    @commands.command(name="toss")
    async def toss_coin(self, ctx, bet: int = 0):
        """Toss a coin and bet on heads or tails"""
        if bet < 0:
            await ctx.send("Tangina mo, wag kang negative! Positive bets lang!")
            return

        if bet > 0 and not self.deduct_coins(ctx.author.id, bet):
            await ctx.send(f"Ulol {ctx.author.mention}, wala kang pera! Balance mo: {self.get_user_balance(ctx.author.id)} coins.")
            return

        result = random.choice(["Heads", "Tails"])
        await ctx.send(f"🎲 {ctx.author.mention} tossed a coin... It's **{result}**!")

        if bet > 0:
            if random.random() < 0.5:  # 50% chance to win
                winnings = bet * 2
                self.add_coins(ctx.author.id, winnings)
                await ctx.send(f"Congratulations! You won **{winnings} coins**! New balance: {self.get_user_balance(ctx.author.id)}")
            else:
                await ctx.send(f"Bad luck! You lost your bet. Balance: {self.get_user_balance(ctx.author.id)}")

    @commands.command(name="blackjack")
    async def blackjack(self, ctx, bet: int):
        """Play a simplified Blackjack game"""
        if bet < 0:
            await ctx.send("Gago, wag kang negative! Positive bets lang!")
            return

        if not self.deduct_coins(ctx.author.id, bet):
            await ctx.send(f"Ulol {ctx.author.mention}, wala kang pera! Balance mo: {self.get_user_balance(ctx.author.id)} coins.")
            return

        # Initialize game
        deck = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
        random.shuffle(deck)
        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]

        self.blackjack_games[ctx.author.id] = {
            "deck": deck,
            "player_hand": player_hand,
            "dealer_hand": dealer_hand,
            "bet": bet
        }

        await ctx.send(f"🎴 {ctx.author.mention}, your hand: {player_hand} (Total: {sum(player_hand)})\n"
                       f"Dealer's hand: [{dealer_hand[0]}, ?]\n"
                       f"Type `g!hit` to draw a card or `g!stand` to end your turn.")

    @commands.command(name="hit")
    async def hit(self, ctx):
        """Draw a card in Blackjack"""
        if ctx.author.id not in self.blackjack_games:
            await ctx.send("Ulol, wala kang ongoing na Blackjack game! Use `g!blackjack <bet>` to start.")
            return

        game = self.blackjack_games[ctx.author.id]
        game["player_hand"].append(game["deck"].pop())
        player_total = sum(game["player_hand"])

        if player_total > 21:
            await ctx.send(f"Bust! Your hand: {game['player_hand']} (Total: {player_total})\n"
                           f"Dealer's hand: {game['dealer_hand']} (Total: {sum(game['dealer_hand'])})\n"
                           f"You lost your bet of {game['bet']} coins.")
            del self.blackjack_games[ctx.author.id]
            return

        await ctx.send(f"🎴 {ctx.author.mention}, your hand: {game['player_hand']} (Total: {player_total})\n"
                       f"Type `g!hit` to draw another card or `g!stand` to end your turn.")

    @commands.command(name="stand")
    async def stand(self, ctx):
        """End your turn in Blackjack"""
        if ctx.author.id not in self.blackjack_games:
            await ctx.send("Ulol, wala kang ongoing na Blackjack game! Use `g!blackjack <bet>` to start.")
            return

        game = self.blackjack_games[ctx.author.id]
        dealer_total = sum(game["dealer_hand"])
        player_total = sum(game["player_hand"])

        # Dealer draws until total >= 17
        while dealer_total < 17:
            game["dealer_hand"].append(game["deck"].pop())
            dealer_total = sum(game["dealer_hand"])

        # Determine winner
        if dealer_total > 21 or player_total > dealer_total:
            winnings = game["bet"] * 2
            self.add_coins(ctx.author.id, winnings)
            await ctx.send(f"🎴 You win! Your hand: {game['player_hand']} (Total: {player_total})\n"
                           f"Dealer's hand: {game['dealer_hand']} (Total: {dealer_total})\n"
                           f"You won **{winnings} coins**! New balance: {self.get_user_balance(ctx.author.id)}")
        elif player_total == dealer_total:
            self.add_coins(ctx.author.id, game["bet"])
            await ctx.send(f"🎴 It's a tie! Your hand: {game['player_hand']} (Total: {player_total})\n"
                           f"Dealer's hand: {game['dealer_hand']} (Total: {dealer_total})\n"
                           f"Your bet of {game['bet']} coins was returned.")
        else:
            await ctx.send(f"🎴 You lose! Your hand: {game['player_hand']} (Total: {player_total})\n"
                           f"Dealer's hand: {game['dealer_hand']} (Total: {dealer_total})\n"
                           f"You lost your bet of {game['bet']} coins.")

        del self.blackjack_games[ctx.author.id]

    # Bank commands
    @commands.command(name="balance")
    async def balance(self, ctx):
        """Check your coin balance"""
        balance = self.get_user_balance(ctx.author.id)
        await ctx.send(f"{ctx.author.mention}, you have **{balance} coins**!")

    @commands.command(name="leaderboard")
    async def leaderboard(self, ctx):
        """Show the top 10 users with the most coins"""
        sorted_users = sorted(self.user_coins.items(), key=lambda x: x[1], reverse=True)[:10]
        leaderboard = "\n".join([f"{i+1}. <@{user}>: {coins} coins" for i, (user, coins) in enumerate(sorted_users)])
        await ctx.send(f"🏆 **Top 10 Richest Users** 🏆\n{leaderboard}")

def setup(bot):
    """Add the cog to the bot"""
    bot.add_cog(ChatCog(bot))
    
