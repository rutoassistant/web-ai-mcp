#!/bin/bash
# Build the image if it doesn't exist (optional check)
# docker build -t web-ai-mcp .

# Run the container with interactive stdio
# -i: Keep stdin open
# --rm: Remove container after exit
docker run -i --rm web-ai-mcp
