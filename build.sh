#!/usr/bin/env bash
set -e

echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

echo "⬇️  Installing ffmpeg via static binary..."
mkdir -p $HOME/bin

# Static ffmpeg binary — no apt-get needed
curl -L https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz \
     -o /tmp/ffmpeg.tar.xz

tar -xf /tmp/ffmpeg.tar.xz -C /tmp/
cp /tmp/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg $HOME/bin/ffmpeg
cp /tmp/ffmpeg-master-latest-linux64-gpl/bin/ffprobe $HOME/bin/ffprobe
chmod +x $HOME/bin/ffmpeg $HOME/bin/ffprobe
rm -rf /tmp/ffmpeg*

echo "✅ yt-dlp: $(python -m yt_dlp --version)"
echo "✅ ffmpeg: $($HOME/bin/ffmpeg -version 2>&1 | head -1)"
echo "✅ Build complete!"
