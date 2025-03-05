import os
import discord
from discord.ext import commands
from flask import Flask
import threading
import asyncio
import random
import time
from datetime import datetime, timedelta

# Load environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "g!")  # Default prefix

# Flask Web Server (Keeps Render Service Alive)
app = Flask(__name__)

@app.route("/")
def home():
    return "🔥 BOT IS ONLINE, MGA PUTANGINA NYO! 🔥"

def run_web():
    port = int(os.environ.get("PORT", 8080))  # Render uses dynamic ports
    app.run(host="0.0.0.0", port=port, debug=False)

# Start Flask in a separate thread
threading.Thread(target=run_web, daemon=True).start()

# Initialize Discord bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=COMMAND_PREFIX, 
                   intents=intents,
                   help_command=None)

# User bank system (keeps track of money)
user_bank = defaultdict(lambda: 1_000_000)
last_claim = {}

@bot.event
async def on_ready():
    print(f'🔥 LOGGED IN AS {bot.user.name}! 🔥')
    print(f'BOT ID: {bot.user.id}')
    print('------')

# Function to update user balance
def update_balance(user_id, amount):
    user_bank[user_id] += amount

# Game: Daily Bonus
@bot.command(name="daily")
async def daily(ctx):
    """Claim ₱10,000 every 24 hours"""
    user_id = ctx.author.id
    now = datetime.now()
    
    if user_id in last_claim and now - last_claim[user_id] < timedelta(days=1):
        await ctx.send(f"Hoy {ctx.author.mention}, puta ka wag kang swapang! Balik ka bukas!")
        return
    
    last_claim[user_id] = now
    update_balance(user_id, 10_000)
    await ctx.send(f"{ctx.author.mention} nakakuha ka ng ₱10,000! Sana di mo lang ipambili ng jowa yan, tanga!")

# Game: Coin Toss
@bot.command(name="toss")
async def toss(ctx, bet: int, choice: str):
    """Toss a coin, bet on 'heads' or 'tails'"""
    user_id = ctx.author.id
    balance = user_bank[user_id]
    
    if bet > balance:
        await ctx.send(f"Tanga! Wala kang ganyang pera! Balance mo: ₱{balance}")
        return
    
    if choice.lower() not in ["heads", "tails"]:
        await ctx.send("Ano ba yan? Pili ka lang ng 'heads' o 'tails'! Gago ka ba?")
        return
    
    result = random.choice(["heads", "tails"])
    if choice.lower() == result:
        update_balance(user_id, bet)
        await ctx.send(f"Tangina mo {ctx.author.mention}, nanalo ka! (+₱{bet}) Pero di ka pa rin magka-jowa!")
    else:
        update_balance(user_id, -bet)
        await ctx.send(f"HAHAHAHA! Talunan ka {ctx.author.mention}! (-₱{bet}) Buti nga sa'yo!")

# Game: Blackjack
@bot.command(name="blackjack")
async def blackjack(ctx, bet: int):
    """Play Blackjack against the bot"""
    user_id = ctx.author.id
    balance = user_bank[user_id]
    
    if bet > balance:
        await ctx.send(f"Hoy gago ka, wala kang ₱{bet}! Balance mo lang ₱{balance}!")
        return
    
    def draw_card():
        return random.randint(1, 11)
    
    player_hand = draw_card() + draw_card()
    bot_hand = draw_card() + draw_card()
    
    if player_hand > 21:
        update_balance(user_id, -bet)
        await ctx.send(f"Putangina ka {ctx.author.mention}, nag-bust ka agad! (-₱{bet})")
        return
    
    while bot_hand < 17:
        bot_hand += draw_card()
    
    result_msg = f"Blackjack Game:\n\n{ctx.author.mention}: {player_hand}\nBot: {bot_hand}\n"
    
    if bot_hand > 21 or player_hand > bot_hand:
        update_balance(user_id, bet)
        result_msg += "Panalo ka! (+₱{bet}) Pero di ka pa rin pogi."
    elif player_hand < bot_hand:
        update_balance(user_id, -bet)
        result_msg += "HAHAHA Talo ka! (-₱{bet}) Maghanap ka na lang ng ibang trabaho!"
    else:
        result_msg += "Draw! Wala kang nakuha, pero at least di ka natalo."
    
    await ctx.send(result_msg)

# Command: Check Balance
@bot.command(name="balance")
async def balance(ctx):
    """Check your balance"""
    user_id = ctx.author.id
    bal = user_bank[user_id]
    await ctx.send(f"{ctx.author.mention}, pera mo ngayon: ₱{bal}. Sana di mo lang ipang-libre yan sa crush mo!")

def main():
    if not DISCORD_TOKEN:
        print("Error: Discord token not found in environment variables")
        return

    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"Error running bot: {e}")

if __name__ == "__main__":
    main()
