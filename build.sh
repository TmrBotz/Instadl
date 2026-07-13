#!/usr/bin/env bash
set -e

echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

echo "⬇️  Installing ffmpeg..."
apt-get update -qq && apt-get install -y -qq ffmpeg

echo "✅ yt-dlp version: $(python -m yt_dlp --version)"
echo "✅ ffmpeg version: $(ffmpeg -version 2>&1 | head -1)"
echo "✅ Build complete!"
