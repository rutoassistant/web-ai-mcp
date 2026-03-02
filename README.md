# Web AI MCP Server (No-Login Edition)

This MCP server uses **Patchright** (stealth Playwright) to automate **DuckDuckGo AI Chat**, providing free access to GPT-4o mini, Claude 3 Haiku, and Llama 3.1 without an account.

## Features

- **No Login Required**: Uses DuckDuckGo's public AI chat interface.
- **Stealth**: Uses Patchright and `xvfb` to mimic a real browser session.
- **Tools**:
  - `chat_send(message)`: Send a prompt and get the response.
  - `chat_reset()`: Clear the session.
  - `screenshot()`: Debug view.

## Setup

### 1. Build the Docker Image

```bash
docker build -t web-ai-mcp .
```

### 2. Run the Container

```bash
docker run -i --rm \
  web-ai-mcp
```

(No volume mount needed since we don't need persistent login sessions for DDG AI).

## Usage with MCP Client

Configure your MCP client (e.g., Claude Desktop, OpenClaw) to run the docker command:

```json
{
  "mcpServers": {
    "web-ai": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "web-ai-mcp"
      ]
    }
  }
}
```
