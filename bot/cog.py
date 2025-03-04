import discord
from discord.ext import commands
from groq import Groq
import asyncio
from collections import deque, defaultdict
import time
import random
from .config import Config

class ChatCog(commands.Cog):
    """Cog for handling chat interactions with the Groq AI model"""

    def __init__(self, bot):
        """Initialize the ChatCog with necessary attributes"""
        self.bot = bot
        self.groq_client = Groq(api_key=Config.GROQ_API_KEY)
        self.conversation_history = defaultdict(lambda: deque(maxlen=Config.MAX_CONTEXT_MESSAGES))
        self.user_message_timestamps = defaultdict(list)
        self.creator = Config.BOT_CREATOR
        print("ChatCog initialized")

    async def get_ai_response(self, conversation_history):
        """Get response from Groq AI with conversation context"""
        try:
            print(f"Generating AI response with {len(conversation_history)} messages in history")

            # Create system message and conversation history for the API call
            messages = [
                {"role": "system", "content": """I am a helpful and friendly AI assistant. I respond in a conversational, polite manner. I provide accurate and helpful information. I can assist with various questions and tasks to the best of my abilities."""}
            ]

            # Add conversation history to the message list
            for msg in conversation_history:
                messages.append({
                    "role": "user" if msg["is_user"] else "assistant",
                    "content": msg["content"]
                })

            print("Calling Groq API...")
            # Make the API call using asyncio to prevent blocking
            completion = await asyncio.to_thread(
                self.groq_client.chat.completions.create,
                model=Config.GROQ_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=800
            )

            response = completion.choices[0].message.content
            print(f"Got response from Groq API: {response[:50]}...")
            return response

        except Exception as e:
            print(f"Error getting AI response: {e}")
            return "Sorry, I encountered an error. Please try again later."

    def is_rate_limited(self, user_id):
        """Check if a user has exceeded the rate limit"""
        current_time = time.time()
        # Filter out old timestamps
        self.user_message_timestamps[user_id] = [
            ts for ts in self.user_message_timestamps[user_id]
            if current_time - ts < Config.RATE_LIMIT_PERIOD
        ]
        # Check if the user has sent too many messages in the time period
        return len(self.user_message_timestamps[user_id]) >= Config.RATE_LIMIT_MESSAGES

    def add_to_conversation(self, channel_id, is_user, content):
        """Add a message to the conversation history"""
        self.conversation_history[channel_id].append({
            "is_user": is_user,
            "content": content
        })
        return len(self.conversation_history[channel_id])

    @commands.command(name="usap")
    async def usap(self, ctx, *, message: str):
        """Chat with GROQ AI"""
        try:
            print(f"Received g!usap command from {ctx.author.name}: {message}")

            # Check rate limiting
            if self.is_rate_limited(ctx.author.id):
                await ctx.send(f"Hi {ctx.author.mention}, you're sending messages too quickly. Please wait a moment before trying again.")
                return

            # Record timestamp for rate limiting
            self.user_message_timestamps[ctx.author.id].append(time.time())

            # Get existing conversation history
            channel_history = list(self.conversation_history[ctx.channel.id])
            channel_history.append({"is_user": True, "content": message})

            async with ctx.typing():
                # Get AI response
                response = await self.get_ai_response(channel_history)

                # Add both messages to conversation history
                self.add_to_conversation(ctx.channel.id, True, message)
                self.add_to_conversation(ctx.channel.id, False, response)

                print(f"Updated conversation history length: {len(self.conversation_history[ctx.channel.id])}")
                await ctx.send(f"{ctx.author.mention} {response}")

        except Exception as e:
            print(f"Error in usap command: {e}")
            await ctx.send(f"Sorry {ctx.author.mention}, I encountered an error processing your request. Please try again.")

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

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for messages and respond to mentions"""
        if message.author == self.bot.user:
            return

        # Only respond to mentions if it's not a command
        if self.bot.user in message.mentions and not message.content.startswith(Config.COMMAND_PREFIX):
            await message.reply(f"Hi {message.author.mention}! To chat with me, use `g!usap <message>` command.")

    # Voice channel commands
    @commands.command(name="join")
    async def join(self, ctx):
        """Join voice channel with enhanced error handling"""
        if not ctx.author.voice:
            await ctx.send("You need to be in a voice channel first!")
            return

        channel = ctx.author.voice.channel
        try:
            print(f"Attempting to join VC: {channel.name}")

            # Check if already in the same voice channel
            if ctx.voice_client and ctx.voice_client.channel == channel:
                await ctx.send("I'm already in your voice channel! Use `g!leave` if you want me to leave.")
                return

            # Disconnect from current VC if in a different one
            if ctx.voice_client:
                print("Disconnecting from current VC")
                await ctx.voice_client.disconnect()

            # Connect to new VC
            print("Connecting to new VC")
            await channel.connect(timeout=60, reconnect=True)
            print(f"Successfully connected to VC: {channel.name}")
            await ctx.send(f"Joined {channel.name}! Use `g!leave` when you want me to leave.")

        except Exception as e:
            print(f"Error joining VC: {str(e)}")
            await ctx.send(f"Sorry, I couldn't join the voice channel. Error: {str(e)}")

    @commands.command(name="leave")
    async def leave(self, ctx):
        """Leave voice channel"""
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("I've left the voice channel. Call me again if you need me!")
        else:
            await ctx.send("I'm not in a voice channel!")

    # Help and info commands
    @commands.command(name="tulong")
    async def tulong(self, ctx):
        """Show help information"""
        help_embed = discord.Embed(
            title="Bot Commands",
            description="Here are the commands you can use:",
            color=discord.Color.blue()
        )

        commands = {
            "g!usap <message>": "Chat with the AI assistant",
            "g!ask <question>": "Ask a one-off question without storing conversation",
            "g!clear": "Clear the conversation history",
            "g!join": "Join your voice channel",
            "g!leave": "Leave the voice channel",
            "g!rules": "Display server rules",
            "g!announcement": "Make an announcement",
            "g!creator": "Show bot creator information",
            "g!game": "Play a simple number guessing game"
        }

        for cmd, desc in commands.items():
            help_embed.add_field(name=cmd, value=desc, inline=False)

        await ctx.send(embed=help_embed)

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