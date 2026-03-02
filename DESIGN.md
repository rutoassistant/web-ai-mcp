# Web AI MCP Server Design (No-Login Target)

## Goal
Create an MCP server running in Docker that uses **Patchright** (stealth Playwright) to automate **DuckDuckGo AI Chat**.
This meets the requirement of "Gemini web like sites which don't need login". DuckDuckGo AI provides free access to models like GPT-4o mini, Claude 3 Haiku, and Llama 3.1 without an account.

## Architecture

### 1. Core Components
- **MCP Server (Python)**: Exposes tools via stdio.
- **Browser Automation (Patchright)**: Handles the chat interface interaction.
- **Docker Container**: Encapsulates Python + Browsers + Xvfb.

### 2. Tools Exposed
- `chat_send(message: str, model: str = "gpt-4o-mini") -> str`: Send a message and return the response.
- `chat_reset() -> str`: Clear the conversation history (start new chat).
- `screenshot() -> str (base64)`: Debug view.

### 3. Target: DuckDuckGo AI Chat
- **URL**: `https://duckduckgo.com/?q=DuckDuckGo&ia=chat`
- **Flow**:
  1.  Navigate to URL.
  2.  Click "Get Started" (if present).
  3.  Agree to terms (if present).
  4.  Input message into textarea.
  5.  Wait for streaming response to complete.
  6.  Extract text.

### 4. Stealth Strategy
- **Patchright**: Essential to avoid bot detection on DDG (they have some protections).
- **User-Agent**: Standard Chrome/Firefox.
- **Headless**: False (Xvfb) to mimic real user.

## File Structure
```
web-ai-mcp/
├── Dockerfile          # Setup environment
├── requirements.txt    # patchright, mcp, xvfbwrapper
├── server.py           # Main MCP server + DDG logic
└── run.sh              # Helper script
```

## Implementation Plan
1.  **Dependencies**: `mcp`, `patchright`.
2.  **Server Logic**:
    -   `ensure_browser()`: Launches browser if not running.
    -   `ensure_chat()`: Navigates to DDG, handles "Get Started" / "Terms" clicks.
    -   `chat_send()`: Enters text, clicks send, waits for response (stops streaming).
