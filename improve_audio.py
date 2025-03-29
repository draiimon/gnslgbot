import os

# Read the file content
with open('bot/optimized_audio_cog.py', 'r') as file:
    content = file.read()

# Make the replacements
content = content.replace(
    'audio = audio.set_frame_rate(44100).set_channels(1)  # OPTIMIZED: mono, reduced quality',
    'audio = audio.set_frame_rate(48000).set_channels(2)  # HIGH QUALITY: stereo, highest sample rate'
)

content = content.replace(
    'audio.export(wav_filename, format="wav")',
    'audio.export(wav_filename, format="wav", parameters=["-q:a", "0"])'
)

# Volume boost for clearer audio
content = content.replace(
    'audio = discord.PCMVolumeTransformer(audio_source, volume=0.8)',
    'audio = discord.PCMVolumeTransformer(audio_source, volume=1.0)'
)

# Write the modified content back to the file
with open('bot/optimized_audio_cog.py', 'w') as file:
    file.write(content)

print("Audio quality improvements applied!")
