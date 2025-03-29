import os

# Read the file content
with open('bot/optimized_audio_cog.py', 'r') as file:
    content = file.read()

# Update all FFmpeg comments
content = content.replace(
    "# Create audio source from the MP3 file with optimized settings for Replit\n                    # Low bitrate, mono, smaller buffer - perfect for Replit's limited RAM",
    "# Create audio source from the MP3 file with HIGH QUALITY settings\n                    # Stereo audio, high bitrate, optimal buffer - for crisp clear audio"
)

# Also update the comment for the PCMStream
content = content.replace(
    "# Convert using pydub with optimized settings (mono, lower quality)",
    "# Convert using pydub with HIGH QUALITY settings (stereo, highest quality)"
)

# Write the modified content back to the file
with open('bot/optimized_audio_cog.py', 'w') as file:
    file.write(content)

print("Updated all comments to reflect higher audio quality!")
