import discord
from discord.ext import commands
from groq import Groq
import asyncio
from collections import deque, defaultdict
import time
import random
from .config import Config

class ChatCog(commands.Cog):
    """🔥🔥🔥 WELCOME SA PINAKAMALUPIT NA BOT SA LAHAT NG DISCORD!!! 🤬🔥💦"""

    def __init__(self, bot):
        """INITIALIZING THE MOST POWERFUL, BASTOS, AT HIGHEST IQ NA BOT! 🤖💀"""
        self.bot = bot
        self.groq_client = Groq(api_key=Config.GROQ_API_KEY)
        self.conversation_history = defaultdict(lambda: deque(maxlen=Config.MAX_CONTEXT_MESSAGES))
        self.user_message_timestamps = defaultdict(list)
        self.creator = Config.BOT_CREATOR
        print("🔥🔥🔥 BOT ONLINE, MGA ULUL! 🔥🔥🔥")

    async def get_ai_response(self, conversation_history):
        """KUKUNIN ANG PINAKA-BOGCHI NA SAGOT PARA SA TANONG MO, TARANTADO KA! 🤬"""
        try:
            messages = [
                {"role": "system", "content": "PUTANGINA MO! AKO SI AI, ANG PINAKAMALUPIT AT PINAKAMATALINONG BOT! HINDI AKO PANG-BOBO!"}
            ]

            for msg in conversation_history:
                messages.append({
                    "role": "user" if msg["is_user"] else "assistant",
                    "content": msg["content"]
                })

            completion = await asyncio.to_thread(
                self.groq_client.chat.completions.create,
                model=Config.GROQ_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=800
            )

            response = completion.choices[0].message.content
            return response

        except Exception as e:
            return "PUTANGINA, MAY ERROR! SUBUKAN MO ULIT, GAGO! 🤬"

    @commands.command(name="usap")
    async def usap(self, ctx, *, message: str):
        """USAP TAYO, PERO WAG KANG BOBO! 🤬"""
        response = await self.get_ai_response([{"is_user": True, "content": message}])
        await ctx.send(f"{ctx.author.mention} {response}")

    @commands.command(name="tulong")
    async def tulong(self, ctx):
        """PUTANGINA, BASAHIN MO 'TO KUNG AYAW MONG MAGING TANGA! 🤬🔥💦"""
        help_embed = discord.Embed(
            title="📜 **GAGO! BASAHIN MO 'TO!**",
            description="ETO MGA COMMANDS MO, ULOL!",
            color=discord.Color.red()
        )

        commands_list = {
            "g!usap <message>": "USAP TAYO, PERO WAG KANG TANGA! 🤬",
            "g!ask <question>": "MGTANONG NG ONE-TIME KUNG DI KA BOBO!",
            "g!clear": "BURAHIN ANG MGA USAPAN MO, GAGO KA!",
            "g!join": "PASOK SA VC MO KAHIT AYAW MO!",
            "g!leave": "AALIS AKO SA VC PAG TAPOS NA!",
            "g!rules": "BASAHIN MO MGA RULES, BOBO!",
            "g!game": "MAGLARO KA, PARA HINDI KA MASYADONG WALANG AMBAG! 🤬🔥"
        }

        for cmd, desc in commands_list.items():
            help_embed.add_field(name=cmd, value=desc, inline=False)

        await ctx.send(embed=help_embed)

    @commands.command(name="creator")
    async def show_creator(self, ctx):
        """SINO GUMAWA NG PUTANGINANG BOT NA 'TO?! 🤬"""
        creator_embed = discord.Embed(
            title="👑 **BOT CREATOR** 👑",
            description=f"TANGINA, SI {self.creator} ANG GUMAWA SA AKIN! BOW DOWN, MGA BOBO!",
            color=discord.Color.gold()
        )
        await ctx.send(embed=creator_embed)

    @commands.command(name="rules")
    async def rules(self, ctx):
        """BASAHIN MO MGA PUTANGINANG RULES NA 'TO, BOBO! 🤬🔥"""
        rules_embed = discord.Embed(
            title="📜 **SERVER RULES! BASAHIN MO, GAGO!**",
            description="ETO MGA BATAS SA SERVER, WAG KANG PASAWAY! 🤬",
            color=discord.Color.blue()
        )
        rules_embed.add_field(name="1. WAG KANG BOBO!", value="GAMITIN ANG UTAK, ULOL!", inline=False)
        rules_embed.add_field(name="2. WAG KANG BASTOS!", value="AKO LANG PWEDENG BASTOS DITO!", inline=False)
        rules_embed.add_field(name="3. RESPETO!", value="KAHIT GAGO KA, RESPETO PARA SA LAHAT! 🤬🔥", inline=False)
        await ctx.send(embed=rules_embed)

bot.add_cog(ChatCog(bot))
