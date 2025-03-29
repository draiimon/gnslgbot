#!/bin/bash

echo "Starting Lavalink server on port 2333..."

# Check if Java is installed
if command -v java &> /dev/null; then
    echo "Java found: $(java -version 2>&1 | head -n 1)"
else
    echo "ERROR: Java not found! Please make sure Java 11+ is installed."
    exit 1
fi

# Create logs directory if it doesn't exist
mkdir -p logs

# Download Lavalink.jar if it doesn't exist
if [ ! -f "Lavalink.jar" ]; then
    echo "Downloading Lavalink.jar..."
    curl -s https://github.com/freyacodes/Lavalink/releases/latest/download/Lavalink.jar -o Lavalink.jar
    
    if [ $? -ne 0 ]; then
        echo "Failed to download Lavalink.jar. Please check your internet connection."
        exit 1
    fi
    
    echo "Downloaded Lavalink.jar."
fi

# Start Lavalink
echo "Starting Lavalink server..."
java -jar Lavalink.jar