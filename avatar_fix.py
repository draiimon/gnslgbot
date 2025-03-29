import discord
from discord.ext import commands
import re
import os

def update_code():
    """
    This script fixes all avatar_url references in bot/cog.py and replaces them with avatar.url
    with proper error handling. For use with Discord.py 2.0+
    """
    print("Starting avatar_url fix...")
    
    # Read the cog file
    try:
        with open("bot/cog.py", "r") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return False
        
    # Pattern 1: Replace avatar_url with avatar.url with proper checks
    pattern1 = r"([a-zA-Z0-9_]+)\.avatar_url"
    replacement1 = r"\1.avatar.url if \1 and \1.avatar else None"
    content = re.sub(pattern1, replacement1, content)
    
    # Save the updated file
    try:
        with open("bot/cog.py", "w") as f:
            f.write(content)
        print("✅ Fixed all avatar_url references with proper checks")
        return True
    except Exception as e:
        print(f"Error writing file: {e}")
        return False

if __name__ == "__main__":
    update_code()