#!/usr/bin/env bash
set -e

echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

echo "⬇️  Installing latest yt-dlp binary..."
curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
     -o /usr/local/bin/yt-dlp
chmod a+rx /usr/local/bin/yt-dlp

echo "✅ yt-dlp version: $(yt-dlp --version)"
echo "✅ Build complete!"
