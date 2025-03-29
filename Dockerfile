FROM python:3.11-slim

# Install system dependencies including FFmpeg and PostgreSQL client
RUN apt-get update && \
    apt-get install -y ffmpeg libffi-dev libnacl-dev libsodium-dev gcc g++ make \
    openjdk-17-jre-headless curl postgresql-client libpq-dev && \
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

# Health check to ensure the bot is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:5000/ || exit 1

# Add a script to wait for database and then start the bot
RUN echo '#!/bin/bash\n\
echo "Waiting for PostgreSQL to be ready..."\n\
if [ -n "$DATABASE_URL" ]; then\n\
  # Extract host and port from DATABASE_URL\n\
  DB_HOST=$(echo $DATABASE_URL | sed -e "s/^.*@//" -e "s/:.*//" -e "s/\\/.*//")\n\
  DB_PORT=$(echo $DATABASE_URL | sed -e "s/^.*://" -e "s/\\/.*//")\n\
  # Wait for PostgreSQL\n\
  until pg_isready -h $DB_HOST -p $DB_PORT; do\n\
    echo "PostgreSQL is unavailable - sleeping"\n\
    sleep 2\n\
  done\n\
  echo "PostgreSQL is up - executing command"\n\
else\n\
  echo "No DATABASE_URL found, skipping PostgreSQL check"\n\
fi\n\
\n\
# Start the bot\n\
exec python main.py\n' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Run the entrypoint script
CMD ["/app/entrypoint.sh"]