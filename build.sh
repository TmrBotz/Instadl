#!/usr/bin/env bash
set -e

echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

echo "✅ yt-dlp version: $(python -m yt_dlp --version)"
echo "✅ Build complete!"
