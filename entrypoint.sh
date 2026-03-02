#!/bin/bash
# Entrypoint for Stealth Browser MCP Server
# Starts Xvfb virtual display and then runs the MCP server

set -e

echo "🚀 Starting Stealth Browser MCP Server..."

# Start Xvfb on display :99 with proper screen resolution
echo "📺 Starting Xvfb virtual display..."
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &
XVFB_PID=$!

# Wait for Xvfb to be ready
sleep 2

# Verify Xvfb is running
if ! kill -0 $XVFB_PID 2>/dev/null; then
    echo "❌ Xvfb failed to start"
    exit 1
fi

echo "✅ Xvfb started on display :99"

# Set display environment
export DISPLAY=:99

# Optional: Start window manager for better compatibility
# This can help with some JavaScript that checks for window management
if command -v fluxbox &> /dev/null; then
    echo "🖼️ Starting fluxbox window manager..."
    fluxbox &
    sleep 1
fi

# Print startup info
echo "🔧 Configuration:"
echo "   DISPLAY: $DISPLAY"
echo "   STEALTH_MODE: ${STEALTH_MODE:-true}"
echo "   CAPTCHA_AUTO_SOLVE: ${CAPTCHA_AUTO_SOLVE:-true}"
echo "   PORT: ${PORT:-8080}"

# Run the MCP server
echo "🌐 Starting MCP HTTP server on port ${PORT:-8080}..."
exec python -m src.server --transport streamable-http --port "${PORT:-8080}"
