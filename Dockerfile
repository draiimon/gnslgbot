FROM python:3.11-slim

# Install system dependencies including FFmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg libffi-dev libnacl-dev libsodium-dev gcc g++ make && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy custom requirements file
COPY docker-requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r docker-requirements.txt

# Copy project files
COPY . .

# Create necessary directories if they don't exist
RUN mkdir -p temp_audio temp_music

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the bot
CMD ["python", "main.py"]