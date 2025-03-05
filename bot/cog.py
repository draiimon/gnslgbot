import discord
from discord.ext import commands
from groq import Groq
import asyncio
from collections import deque, defaultdict
import time
import random
import os
from ..config import Config

class ChatCog(commands.Cog):
    """Cog for handling chat interactions with the Groq AI model and games"""

    def __init__(self, bot):
        self.bot = bot
        self.groq_client = Groq(api_key=os.getenv("GROQ_API_KEY", Config.GROQ_API_KEY))
        self.conversation_history = defaultdict(lambda: deque(maxlen=10))
        self.user_message_timestamps = defaultdict(list)
        self.creator = "Your Name"  # Replace with actual creator name
        self.user_coins = defaultdict(lambda: 50_000)  # Default: ₱50,000
        self.daily_cooldown = defaultdict(int)
        self.blackjack_games = {}
        self.ADMIN_ROLE_ID = 1345727357662658603
        print("ChatCog initialized")

    # ========== HELPER FUNCTIONS ==========
    def get_user_balance(self, user_id: int) -> int:
        return self.user_coins[user_id]

    def add_coins(self, user_id: int, amount: int) -> int:
        self.user_coins[user_id] = int(self.user_coins[user_id] + amount)
        return self.user_coins[user_id]

    def deduct_coins(self, user_id: int, amount: int) -> bool:
        if self.user_coins[user_id] >= amount:
            self.user_coins[user_id] = int(self.user_coins[user_id] - amount)
            return True
        return False

    async def get_ai_response(self, conversation_history):
        try:
            messages = [
                {"role": "system", "content": "I am a helpful and friendly AI assistant. I respond in a conversational, polite manner."}
            ]

            for msg in conversation_history:
                messages.append({
                    "role": "user" if msg["is_user"] else "assistant",
                    "content": msg["content"]
                })

            completion = await asyncio.to_thread(
                self.groq_client.chat.completions.create,
                model=Config.GROQ_MODEL or "mixtral-8x7b-32768", #Fallback to default model if Config is missing
                messages=messages,
                temperature=0.7,
                max_tokens=800
            )

            return completion.choices[0].message.content

        except Exception as e:
            print(f"Error getting AI response: {e}")
            return "Sorry, I encountered an error. Please try again later."

    def is_rate_limited(self, user_id: int) -> bool:
        current_time = time.time()
        self.user_message_timestamps[user_id] = [
            ts for ts in self.user_message_timestamps[user_id]
            if current_time - ts < 60  # 60 seconds rate limit period
        ]
        return len(self.user_message_timestamps[user_id]) >= 5  # 5 messages per minute

    # ========== CHAT COMMANDS ==========
    @commands.command(name="usap")
    async def usap(self, ctx, *, message: str):
        """Chat with GROQ AI"""
        try:
            if self.is_rate_limited(ctx.author.id):
                await ctx.send(f"**TEKA LANG!** {ctx.author.mention} SOBRANG BILIS MO MAG-MESSAGE! HINAY HINAY LANG! 😤")
                return

            self.user_message_timestamps[ctx.author.id].append(time.time())
            channel_history = list(self.conversation_history[ctx.channel.id])
            channel_history.append({"is_user": True, "content": message})

            async with ctx.typing():
                response = await self.get_ai_response(channel_history)
                self.conversation_history[ctx.channel.id].append({"is_user": True, "content": message})
                self.conversation_history[ctx.channel.id].append({"is_user": False, "content": response})
                await ctx.send(f"{ctx.author.mention} {response}")

        except Exception as e:
            print(f"Error in usap command: {e}")
            await ctx.send(f"**PATAWAD** {ctx.author.mention}, MAY ERROR! SUBUKAN MO ULIT MAMAYA! 😢")

    @commands.command(name="clear")
    async def clear_history(self, ctx):
        """Clear conversation history"""
        self.conversation_history[ctx.channel.id].clear()
        await ctx.send("**AYOS!** CLEAR NA ANG CHAT HISTORY NATIN! 🧹")

    @commands.command(name="ask")
    async def ask(self, ctx, *, question):
        """Ask a one-off question without storing conversation"""
        if self.is_rate_limited(ctx.author.id):
            await ctx.send(f"**TEKA LANG!** {ctx.author.mention} HINAY HINAY SA TANONG! 😤")
            return

        self.user_message_timestamps[ctx.author.id].append(time.time())
        async with ctx.typing():
            response = await self.get_ai_response([{"is_user": True, "content": question}])
            await ctx.send(f"{ctx.author.mention} {response}")

    @commands.command(name="join")
    async def join(self, ctx):
        """Join voice channel"""
        if not ctx.author.voice:
            await ctx.send("**TANGA KA BA?!** PUMASOK KA MUNA SA VOICE CHANNEL BAGO MO KO PINAGJOJOIN! 😤")
            return

        channel = ctx.author.voice.channel
        try:
            if ctx.voice_client and ctx.voice_client.channel == channel:
                await ctx.send("**BULAG KA BA?!** NASA VOICE CHANNEL MO NA KO! 'g!leave' KUNG GUSTO MO KO PAALISIN! 😤")
                return

            if ctx.voice_client:
                await ctx.voice_client.disconnect()

            await channel.connect()
            await ctx.send(f"**AYUN OH!** NASA {channel.name} NA KO! TYPE 'g!leave' KUNG GUSTO MO KO UMALIS! 😎")

        except Exception as e:
            print(f"Error joining VC: {str(e)}")
            await ctx.send(f"**PATAWAD!** {ctx.author.mention} DI AKO MAKAPASOK SA VC! ERROR: {str(e)} 😢")

    @commands.command(name="leave")
    async def leave(self, ctx):
        """Leave voice channel"""
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("**SIGE AALIS NA KO!** TAWAG MO KO ULIT KUNG KAILANGAN MO KO! 👋")
        else:
            await ctx.send("**TANGA!** WALA NGA KO SA VOICE CHANNEL EH! 🤦")

    # ========== ECONOMY COMMANDS ==========
    @commands.command(name="daily")
    async def daily(self, ctx):
        """Claim daily ₱10,000"""
        current_time = time.time()
        last_claim = self.daily_cooldown.get(ctx.author.id, 0)

        if current_time - last_claim < 86400:
            await ctx.send(f"**BOBO KA BA?!** {ctx.author.mention} KAKA-CLAIM MO LANG NG DAILY MO! BALIK KA BUKAS! 😤")
            return

        self.daily_cooldown[ctx.author.id] = current_time
        self.add_coins(ctx.author.id, 10_000)
        await ctx.send(f"🎉 {ctx.author.mention} NAKA-CLAIM KA NA NG DAILY MO NA **₱10,000**! BALANCE MO NGAYON: **₱{self.get_user_balance(ctx.author.id):,}**")

    @commands.command(name="give")
    async def give(self, ctx, member: discord.Member, amount: int):
        """Transfer money to another user"""
        if amount <= 0:
            return await ctx.send("**TANGA KA BA?** WALANG NEGATIVE NA PERA! 😤")

        if not self.deduct_coins(ctx.author.id, amount):
            return await ctx.send(f"**WALA KANG PERA!** {ctx.author.mention} BALANCE MO: **₱{self.get_user_balance(ctx.author.id):,}** 😤")

        self.add_coins(member.id, amount)
        await ctx.send(f"💸 {ctx.author.mention} NAGBIGAY KA NG **₱{amount:,}** KAY {member.mention}! WAG MO SANA PAGSISIHAN YAN! 😤")

    # ========== GAME COMMANDS ==========
    @commands.command(name="toss")
    async def toss(self, ctx, choice: str, bet: int = 0):
        """Bet on heads (h) or tails (t)"""
        choice = choice.lower()
        if choice not in ['h', 't']:
            return await ctx.send("**TANGA!** PUMILI KA NG TAMA! 'h' PARA SA HEADS O 't' PARA SA TAILS! 😤")

        if bet < 0:
            return await ctx.send("**BOBO!** WALANG NEGATIVE NA BET! 😤")

        if bet > 0 and not self.deduct_coins(ctx.author.id, bet):
            return await ctx.send(f"**WALA KANG PERA!** {ctx.author.mention} BALANCE MO: **₱{self.get_user_balance(ctx.author.id):,}** 😤")

        result = random.choice(['h', 't'])
        win_message = random.choice(["**CONGRATS! NANALO KA! 🎉**", "**SANA ALL! PANALO KA! 🏆**", "**NICE ONE! NAKA-JACKPOT KA! 💰**"])
        lose_message = random.choice(["**BOBO KA TALO KA! 😂**", "**WALA KANG SWERTE! TALO KA! 😢**", "**TALO! WAG KA NA MAG-SUGAL! 🚫**"])

        if choice == result:
            winnings = bet * 2
            self.add_coins(ctx.author.id, winnings)
            await ctx.send(f"🎲 **{win_message}**\nRESULTA: **{result.upper()}**\nNANALO KA NG **₱{winnings:,}**!\nBALANCE MO NGAYON: **₱{self.get_user_balance(ctx.author.id):,}**")
        else:
            await ctx.send(f"🎲 **{lose_message}**\nRESULTA: **{result.upper()}**\nTALO KA NG **₱{bet:,}**!\nBALANCE MO NGAYON: **₱{self.get_user_balance(ctx.author.id):,}**")

    @commands.command(name="blackjack")
    async def blackjack(self, ctx, bet: int):
        """Play Blackjack"""
        if bet <= 0:
            await ctx.send("**TANGA!** WALANG GANYANG BET! POSITIVE NUMBER LANG! 😤")
            return

        if not self.deduct_coins(ctx.author.id, bet):
            await ctx.send(f"**WALA KANG PERA!** {ctx.author.mention} BALANCE MO: **₱{self.get_user_balance(ctx.author.id):,}** 😤")
            return

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

        await ctx.send(f"🎴 {ctx.author.mention}\nKARTA MO: {player_hand} (TOTAL: {sum(player_hand)})\n"
                     f"KARTA NG DEALER: [{dealer_hand[0]}, ?]\n"
                     f"TYPE 'g!hit' PARA KUMUHA NG KARTA O 'g!stand' PARA TUMIGIL! 🎲")

    @commands.command(name="hit")
    async def hit(self, ctx):
        """Draw a card in Blackjack"""
        if ctx.author.id not in self.blackjack_games:
            await ctx.send(f"**BOBO!** {ctx.author.mention} WALA KANG LARO! TYPE 'g!blackjack <bet>' PARA MAGLARO! 😤")
            return

        game = self.blackjack_games[ctx.author.id]
        game["player_hand"].append(game["deck"].pop())
        total = sum(game["player_hand"])

        if total > 21:
            await ctx.send(f"**TALO KA GAGO!** 💀\nKARTA MO: {game['player_hand']} (TOTAL: {total})\n"
                         f"KARTA NG DEALER: {game['dealer_hand']} (TOTAL: {sum(game['dealer_hand'])})\n"
                         f"NAWALA MO **₱{game['bet']:,}**! KAWAWA KA NAMAN! 😂")
            del self.blackjack_games[ctx.author.id]
        else:
            await ctx.send(f"🎴 {ctx.author.mention}\nKARTA MO: {game['player_hand']} (TOTAL: {total})\n"
                         f"TYPE 'g!hit' O 'g!stand'")

    @commands.command(name="stand")
    async def stand(self, ctx):
        """Stand in Blackjack"""
        if ctx.author.id not in self.blackjack_games:
            await ctx.send(f"**BOBO!** {ctx.author.mention} WALA KANG LARO! TYPE 'g!blackjack <bet>' PARA MAGLARO! 😤")
            return

        game = self.blackjack_games[ctx.author.id]
        dealer_total = sum(game["dealer_hand"])
        player_total = sum(game["player_hand"])

        while dealer_total < 17:
            game["dealer_hand"].append(game["deck"].pop())
            dealer_total = sum(game["dealer_hand"])

        if dealer_total > 21 or player_total > dealer_total:
            winnings = game["bet"] * 2
            self.add_coins(ctx.author.id, winnings)
            await ctx.send(f"**PANALO KA! 🎉**\nKARTA MO: {game['player_hand']} (TOTAL: {player_total})\n"
                         f"KARTA NG DEALER: {game['dealer_hand']} (TOTAL: {dealer_total})\n"
                         f"NANALO KA NG **₱{winnings:,}**!")
        elif player_total == dealer_total:
            self.add_coins(ctx.author.id, game["bet"])
            await ctx.send(f"**TABLA! 🤝**\nKARTA MO: {game['player_hand']} (TOTAL: {player_total})\n"
                         f"KARTA NG DEALER: {game['dealer_hand']} (TOTAL: {dealer_total})\n"
                         f"BUTI NA LANG HINDI KA NALUGI!")
        else:
            await ctx.send(f"**TALO KA GAGO! 💀**\nKARTA MO: {game['player_hand']} (TOTAL: {player_total})\n"
                         f"KARTA NG DEALER: {game['dealer_hand']} (TOTAL: {dealer_total})\n"
                         f"NAWALA MO **₱{game['bet']:,}**! KAWAWA KA NAMAN! 😂")

        del self.blackjack_games[ctx.author.id]

    # ========== UTILITY COMMANDS ==========
    @commands.command(name="rules")
    async def rules(self, ctx):
        """Display server rules"""
        rules = discord.Embed(
            title="📜 **SERVER RULES**",
            description="""**BASAHIN MO TO MABUTI PARA DI KA MA-KICK!**
286:

1. WALA KANG KARAPATAN MAGING BASTOS! RESPETO SA LAHAT! 🤬
2. BAWAL ANG ILLEGAL NA CONTENT! ISUSUMBONG KITA SA PULIS! 🚔
3. 18+ LANG DITO! BAWAL BATA! 🔞
4. WALA KANG KARAPATANG MAG-SPAM! 🚫
5. NSFW SA NSFW CHANNELS LANG! BASTOS! 🔇
6. BAWAL ANG DOXXING! RESPETO SA PRIVACY! 🕵️
7. SUNDIN MO ANG DISCORD TOS! 📋
8. PAG SINABI NG ADMIN O MOD, SUNDIN MO! 👮

**TANDAAN MO YAN KUNG AYAW MONG MA-BAN!**""",
            color=discord.Color.red()
        )
        await ctx.send(embed=rules)

    @commands.command(name="announcement")
    @commands.has_permissions(administrator=True)
    async def announcement(self, ctx, *, message: str = None):
        """Make an announcement"""
        if not message:
            await ctx.send("**GAGO!** ANONG INAANNOUNCE MO? WALA KANG MESSAGE! 😤")
            return

        announcement = discord.Embed(
            title="📢 **ANNOUNCEMENT**",
            description=message,
            color=discord.Color.blue()
        )
        announcement.set_footer(text=f"Announced by {ctx.author.name}")
        await ctx.send(embed=announcement)

    @commands.command(name="creator")
    async def creator(self, ctx):
        """Show bot creator info"""
        embed = discord.Embed(
            title="🤖 **BOT CREATOR**",
            description=f"**GAWA TO NI {self.creator}!**\nWAG MO KOPYAHIN! MAY KARAPATAN TO! 😤",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)


    @commands.command(name="balance")
    async def balance(self, ctx):
        """Check your balance"""
        balance = self.get_user_balance(ctx.author.id)
        embed = discord.Embed(
            title="💰 **ACCOUNT BALANCE**",
            description=f"{ctx.author.mention}'s balance: **₱{balance:,}**",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command(name="leaderboard")
    async def leaderboard(self, ctx):
        """Display wealth rankings"""
        sorted_users = sorted(self.user_coins.items(), key=lambda x: x[1], reverse=True)[:10]
        embed = discord.Embed(
            title="🏆 **MAYAMAN LEADERBOARD**",
            description="TOP 10 PINAKAMAYAMAN SA SERVER:",
            color=discord.Color.gold()
        )

        for idx, (user_id, coins) in enumerate(sorted_users, 1):
            user = self.bot.get_user(user_id) or "Unknown User"
            embed.add_field(
                name=f"{idx}. {user}",
                value=f"**₱{coins:,}**",
                inline=False
            )
        await ctx.send(embed=embed)

    # ========== ADMIN COMMANDS ==========
    @commands.command(name="sagad")
    @commands.has_role(1345727357662658603)
    async def sagad(self, ctx, amount: int, member: discord.Member):
        """Admin command to modify balances"""
        self.add_coins(member.id, amount)
        await ctx.send(f"💰 **ADMIN OVERRIDE:** NAG-DAGDAG KA NG **₱{amount:,}** KAY {member.mention}! WAG MO ABUSUHIN YAN! 😤", delete_after=10)

    @commands.command(name="tulong")
    async def tulong(self, ctx):
        """Display all available commands"""
        embed = discord.Embed(
            title="📚 **BOT COMMAND GUIDE**",
            description="**TANGINA MO! BASAHIN MO MABUTI TONG MGA COMMANDS NA TO:**",
            color=discord.Color.gold()
        )

        categories = {
            "🤖 AI CHAT": {
                "g!usap <message>": "Kausapin ang AI assistant",
                "g!ask <question>": "Quick tanong sa AI",
                "g!clear": "Clear chat history"
            },
            "🎵 VOICE": {
                "g!join": "Pasok sa voice channel mo",
                "g!leave": "Alis sa voice channel"
            },
            "💰 ECONOMY": {
                "g!daily": "Claim ₱10,000 araw-araw",
                "g!balance": "Check your pera",
                "g!give <@user> <amount>": "Bigyan ng pera",
                "g!leaderboard": "Top 10 mayaman"
            },
            "🎮 GAMES": {
                "g!toss <h/t> <bet>": "Coin flip betting",
                "g!blackjack <bet>": "Blackjack game",
                "g!game": "Number hulaan"
            },
            "⚙️ UTILITY": {
                "g!rules": "Server rules",
                "g!announcement": "Gumawa ng announcement",
                "g!creator": "Bot creator info"
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

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Handle command errors with Tagalog responses"""
        if isinstance(error, commands.MissingRole):
            await ctx.send("**BAWAL YAN SAYO! ADMIN LANG PWEDE DYAN! 😤**")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("**WALA KANG PERMISSION DYAN! 🚫**")
        else:
            print(f'Error: {str(error)}')
            await ctx.send(f"**MAY ERROR!** Patawad {ctx.author.mention}! 😢")

    @commands.command(name="game")
    async def game(self, ctx):
        """Number guessing game"""
        number = random.randint(1, 10)
        await ctx.send("🎮 **HULAAN MO NUMERO KO! (1-10)**\nPASHARE NAMAN NG HULA MO DYAN! 😤")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await self.bot.wait_for('message', timeout=30.0, check=check)
            guess = int(msg.content)

            if guess == number:
                await ctx.send(f"**SHET ANG GALING MO!** 🎉 Tama ka! Ang numero ay **{number}**!")
            else:
                await ctx.send(f"**HAHAHA BOBO!** 😂 Mali ka! Ang numero ay **{number}**!")
        except ValueError:
            await ctx.send("**TANGINA MO!** 😤 NUMERO LANG DAPAT! ULITIN MO!")
        except asyncio.TimeoutError:
            await ctx.send("**OY GAGO!** ⏰ TIMEOUT NA! ANG BAGAL MO NAMAN SUMAGOT!")


def setup(bot):
    """Add the cog to the bot"""
    bot.add_cog(ChatCog(bot))
