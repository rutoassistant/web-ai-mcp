#!/usr/bin/env python3
"""
Stealth Browser MCP Server - Phase 1: Core Server
MCP server with basic browser automation tools.
Supports both stdio and streamable-http transports.
"""

import argparse
import asyncio
import logging
import os
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from src.browser.manager import BrowserManager
from src.browser.captcha import CaptchaSolver
from src.tools.navigation import NavigationTools
from src.tools.interaction import InteractionTools
from src.tools.extraction import ExtractionTools
from src.tools.stealth_search import StealthSearchTools, SearchResult, ExtractedContent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stealth-browser-mcp")

# Environment variable configuration
BROWSER_TIMEOUT_MINUTES = int(os.environ.get("BROWSER_TIMEOUT_MINUTES", "30"))


class StealthBrowserServer:
    """MCP Server for Stealth Browser with web scraping capabilities."""

    def __init__(self):
        self.server = Server("stealth-browser-mcp")
        self.browser_manager: Optional[BrowserManager] = None
        self.nav_tools: Optional[NavigationTools] = None
        self.interact_tools: Optional[InteractionTools] = None
        self.extract_tools: Optional[ExtractionTools] = None
        self.stealth_search_tools: Optional[StealthSearchTools] = None

        self._setup_handlers()

    def _setup_handlers(self):
        """Register MCP tool handlers."""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """List all available tools."""
            return [
                # Navigation Tools
                Tool(
                    name="browser_navigate",
                    description="Navigate browser to specified URL",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "minLength": 1,
                                "description": "URL to navigate to",
                            },
                            "wait_until": {
                                "type": "string",
                                "enum": ["load", "domcontentloaded", "networkidle"],
                                "default": "load",
                                "description": "When to consider navigation complete",
                            },
                        },
                        "required": ["url"],
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="browser_back",
                    description="Navigate back in browser history",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                ),
                # Interaction Tools
                Tool(
                    name="browser_click",
                    description="Click on element matching selector",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "selector": {
                                "type": "string",
                                "minLength": 1,
                                "description": "CSS selector for element",
                            }
                        },
                        "required": ["selector"],
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="browser_fill",
                    description="Fill input field with value",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "selector": {
                                "type": "string",
                                "minLength": 1,
                                "description": "CSS selector for input",
                            },
                            "value": {
                                "type": "string",
                                "minLength": 1,
                                "description": "Value to fill",
                            },
                        },
                        "required": ["selector", "value"],
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="browser_hover",
                    description="Hover over element matching selector",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "selector": {
                                "type": "string",
                                "minLength": 1,
                                "description": "CSS selector for element",
                            }
                        },
                        "required": ["selector"],
                        "additionalProperties": False,
                    },
                ),
                # Extraction Tools
                Tool(
                    name="browser_screenshot",
                    description="Capture screenshot of page or element",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "minLength": 1,
                                "description": "Screenshot filename",
                            },
                            "selector": {
                                "type": "string",
                                "description": "Optional: CSS selector for element",
                            },
                            "full_page": {
                                "type": "boolean",
                                "default": False,
                                "description": "Capture full page",
                            },
                        },
                        "required": ["name"],
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="browser_evaluate",
                    description="Execute JavaScript in browser context",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "script": {
                                "type": "string",
                                "minLength": 1,
                                "description": "JavaScript code to execute",
                            }
                        },
                        "required": ["script"],
                        "additionalProperties": False,
                    },
                ),
                # CAPTCHA Solver Tool
                Tool(
                    name="browser_solve_captcha",
                    description="Auto-detect and solve CAPTCHA challenges (Cloudflare Turnstile, hCaptcha, reCAPTCHA)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "timeout": {
                                "type": "integer",
                                "default": 30,
                                "description": "Maximum time to wait for CAPTCHA solving (seconds)",
                            }
                        },
                        "additionalProperties": False,
                    },
                ),
                # Stealth Search Tools
                Tool(
                    name="stealth_search",
                    description="Search and return structured results",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "minLength": 1,
                                "description": "Search query string",
                            },
                            "count": {
                                "type": "integer",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 20,
                                "description": "Number of results to return (1-20, default: 10)",
                            },
                            "page": {
                                "type": "integer",
                                "default": 1,
                                "minimum": 1,
                                "maximum": 10,
                                "description": "Page number for pagination (1-10, default: 1)",
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Optional: Sub-agent session ID for browser isolation",
                            },
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="stealth_extract",
                    description="Extract clean, readable content from a URL",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "minLength": 1,
                                "description": "URL to extract content from",
                            },
                            "max_length": {
                                "type": "integer",
                                "default": 5000,
                                "description": "Maximum content length in characters (default: 5000)",
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Optional: Sub-agent session ID for browser isolation",
                            },
                        },
                        "required": ["url"],
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="stealth_scrape",
                    description="Deep page scraper that fetches and extracts the full content of a URL in Markdown format",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "minLength": 1,
                                "description": "URL to scrape",
                            },
                            "include_images": {
                                "type": "boolean",
                                "default": False,
                                "description": "Include image URLs in markdown",
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Optional: Sub-agent session ID for browser isolation",
                            },
                        },
                        "required": ["url"],
                        "additionalProperties": False,
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            """Execute tool by name."""
            return await self.call_tool_handler(name, arguments)

    async def call_tool_handler(self, name: str, arguments: dict) -> list[TextContent]:
        """Core logic for executing tools with error handling."""
        logger.info(f"Calling tool: {name} with args: {arguments}")

        if not self.browser_manager:
            return [TextContent(type="text", text="Error: Browser not initialized")]

        try:
            # Use isolated context for search/extract/scrape to prevent race conditions
            if name in ("stealth_search", "stealth_extract", "stealth_scrape"):
                result = await self._execute_tool_isolated(name, arguments)
            else:
                result = await self._execute_tool(name, arguments)
            return [TextContent(type="text", text=str(result))]
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def _execute_tool_isolated(self, name: str, arguments: dict) -> str:
        """Execute tool in an isolated browser context (for search/extract).

        Supports session_id for sub-agent browser isolation:
        - If session_id is provided, uses SubAgentBrowserManager
        - Otherwise uses shared browser with isolated context
        """
        session_id = arguments.get("session_id")

        if session_id and self.browser_manager.subagent_manager:
            # Use sub-agent browser isolation
            logger.info(f"Using sub-agent browser for session: {session_id}")
            browser_instance = await self.browser_manager.get_subagent_browser(session_id)

            # Get or create a page in the sub-agent's browser
            tabs = await browser_instance.list_tabs()
            if tabs:
                # Reuse existing tab
                page = await browser_instance.get_tab(list(tabs.keys())[0])
            else:
                # Create new tab
                _, page = await browser_instance.create_tab()

            try:
                if name == "stealth_search":
                    stealth_tools = StealthSearchTools(page)
                    response = await stealth_tools.search(
                        query=arguments["query"],
                        count=arguments.get("count", 10),
                        page=arguments.get("page", 1),
                    )
                    return self._format_search_response(response)
                elif name == "stealth_extract":
                    stealth_tools = StealthSearchTools(page)
                    content = await stealth_tools.extract(
                        url=arguments["url"], max_length=arguments.get("max_length", 5000)
                    )
                    return self._format_extract_response(content)
                elif name == "stealth_scrape":
                    stealth_tools = StealthSearchTools(page)
                    markdown = await stealth_tools.scrape_page(
                        url=arguments["url"], include_images=arguments.get("include_images", False)
                    )
                    return markdown
            finally:
                # Update activity timestamp
                browser_instance.update_activity()
        else:
            # Use shared browser with isolated context (default behavior)
            async with self.browser_manager.isolated_context() as page:
                if name == "stealth_search":
                    stealth_tools = StealthSearchTools(page)
                    response = await stealth_tools.search(
                        query=arguments["query"],
                        count=arguments.get("count", 10),
                        page=arguments.get("page", 1),
                    )
                    return self._format_search_response(response)
                elif name == "stealth_extract":
                    stealth_tools = StealthSearchTools(page)
                    content = await stealth_tools.extract(
                        url=arguments["url"], max_length=arguments.get("max_length", 5000)
                    )
                    return self._format_extract_response(content)
                elif name == "stealth_scrape":
                    stealth_tools = StealthSearchTools(page)
                    markdown = await stealth_tools.scrape_page(
                        url=arguments["url"], include_images=arguments.get("include_images", False)
                    )
                    return markdown

        return "Unknown tool"

    def _format_search_response(self, response) -> str:
        """Format search response as readable text."""
        formatted_output = []

        # Add AI Summary if available
        if response.ai_summary:
            formatted_output.append("🤖 AI SUMMARY")
            formatted_output.append("=" * 20)
            formatted_output.append(response.ai_summary.text)
            if response.ai_summary.sources:
                formatted_output.append("\nSources:")
                for source in response.ai_summary.sources:
                    formatted_output.append(f"- {source['title']}: {source['url']}")
            formatted_output.append("\n" + "=" * 20 + "\n")

        # Add Web Results
        formatted_output.append(f"Web Results for '{response.query}':")
        for result in response.results:
            formatted_output.append(
                f"{result.position}. {result.title}\n   URL: {result.url}\n   {result.snippet}\n"
            )

        if not response.results and not response.ai_summary:
            return "No results found"

        return "\n".join(formatted_output)

    def _format_extract_response(self, content) -> str:
        """Format extracted content as readable text."""
        result_text = f"Title: {content.title}\n"
        result_text += f"URL: {content.url}\n"
        result_text += f"Word Count: {content.word_count}\n\n"

        if content.summary:
            result_text += f"Summary:\n{content.summary}\n\n"

        result_text += f"Content:\n{content.content}"
        return result_text

    async def _execute_tool(self, name: str, arguments: dict) -> str:
        """Route tool call to appropriate handler (uses shared page for non-isolated tools)."""
        page = self.browser_manager.page

        if not page:
            return "Error: Browser page not available"

        # Navigation tools
        if name == "browser_navigate":
            await page.goto(arguments["url"], wait_until=arguments.get("wait_until", "load"))
            return f"Navigated to {arguments['url']}"

        elif name == "browser_back":
            await page.go_back()
            return "Navigated back"

        # Interaction tools
        elif name == "browser_click":
            selector = arguments["selector"]
            if not selector or not selector.strip():
                raise ValueError("Selector cannot be empty")
            await page.click(selector)
            return f"Clicked element: {selector}"

        elif name == "browser_fill":
            selector = arguments["selector"]
            if not selector or not selector.strip():
                raise ValueError("Selector cannot be empty")
            await page.fill(selector, arguments["value"])
            return f"Filled {selector} with value"

        elif name == "browser_hover":
            selector = arguments["selector"]
            if not selector or not selector.strip():
                raise ValueError("Selector cannot be empty")
            await page.hover(selector)
            return f"Hovered over {selector}"

        # Extraction tools
        elif name == "browser_screenshot":
            path = f"/tmp/{arguments['name']}.png"
            if arguments.get("selector"):
                element = await page.query_selector(arguments["selector"])
                if element:
                    await element.screenshot(path=path)
                else:
                    return f"Element not found: {arguments['selector']}"
            else:
                await page.screenshot(path=path, full_page=arguments.get("full_page", False))
            return f"Screenshot saved: {path}"

        elif name == "browser_evaluate":
            result = await page.evaluate(arguments["script"])
            return str(result)

        elif name == "browser_solve_captcha":
            timeout = arguments.get("timeout", 30)
            captcha_solver = CaptchaSolver()
            result = await captcha_solver.solve(page, timeout=timeout)
            if result.get("success"):
                return f"CAPTCHA solved successfully in {result.get('duration', 0):.2f}s"
            else:
                error_msg = result.get("error", "Unknown error")
                return f"Failed to solve CAPTCHA: {error_msg}"

        elif name == "stealth_scrape":
            stealth_tools = StealthSearchTools(page)
            markdown = await stealth_tools.scrape_page(
                url=arguments["url"], include_images=arguments.get("include_images", False)
            )
            return markdown

        else:
            return f"Unknown tool: {name}"

    async def initialize(self):
        """Initialize browser manager."""
        logger.info("Initializing browser manager...")
        self.browser_manager = BrowserManager()
        await self.browser_manager.start()
        logger.info("Browser manager initialized")

    async def cleanup(self):
        """Cleanup browser resources."""
        if self.browser_manager:
            await self.browser_manager.stop()
            logger.info("Browser manager stopped")

    async def run_stdio(self):
        """Run the MCP server with stdio transport."""
        await self.initialize()

        try:
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream, write_stream, self.server.create_initialization_options()
                )
        finally:
            await self.cleanup()

    async def run_http(self, port: int = 8080):
        """Run the MCP server with streamable HTTP transport."""
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        from starlette.applications import Starlette
        from starlette.routing import Route, Mount
        from starlette.responses import JSONResponse
        from contextlib import asynccontextmanager

        await self.initialize()

        # Health endpoint
        async def health_check(request):
            """Health check endpoint for Docker/container orchestration."""
            return JSONResponse({"status": "healthy", "server": "stealth-browser-mcp"})

        # Create session manager
        session_manager = StreamableHTTPSessionManager(self.server, stateless=True)

        @asynccontextmanager
        async def lifespan(app):
            async with session_manager.run():
                yield

        app = Starlette(
            lifespan=lifespan,
            routes=[
                Route("/health", health_check, methods=["GET"]),
                Mount("/mcp", session_manager.handle_request),
            ],
        )

        # Run with uvicorn
        import uvicorn

        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
        server = uvicorn.Server(config)

        try:
            await server.serve()
        finally:
            await self.cleanup()


async def main():
    """Entry point with transport selection."""
    parser = argparse.ArgumentParser(description="Stealth Browser MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport protocol to use",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for HTTP transport (default: 8080)",
    )
    args = parser.parse_args()

    server = StealthBrowserServer()

    if args.transport == "stdio":
        await server.run_stdio()
    else:
        await server.run_http(port=args.port)


if __name__ == "__main__":
    asyncio.run(main())
