import asyncio
import json
import logging
from typing import Any, Optional
import os
from html_to_markdown import HTMLToMarkdownConverter

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
import patchright
from patchright.async_api import async_playwright, Browser, Page, Playwright

# Import Gemini tools (must be importable after uv sync)
try:
    from src.tools.gemini_chat import GeminiChatTools
except ImportError as e:
    GeminiChatTools = None  # type: ignore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("web-ai-mcp")

if GeminiChatTools is not None:
    logger.info("GeminiChatTools loaded")
else:
    logger.warning(f"GeminiChatTools import failed: {e}")

app = Server("web-ai-mcp")

playwright_instance: Optional[Playwright] = None
browser_instance: Optional[Browser] = None
page_instance: Optional[Page] = None
gemini_tools: Optional["GeminiChatTools"] = None


async def dismiss_overlays(page):
    try:
        await page.wait_for_timeout(1000)
        consent_texts = [
            "Accept",
            "I Accept",
            "Agree",
            "Continue",
            "Got it",
            "Start",
            "Start Chatting",
            "Get Started",
            "I Agree",
            "Allow",
            "OK",
            "Yes",
            "No thanks",
        ]
        for txt in consent_texts:
            btn = page.get_by_role("button", name=txt, exact=False)
            if await btn.count() > 0 and await btn.is_visible():
                logger.info(f"Dismiss overlay: clicking '{txt}'")
                await btn.click()
                await page.wait_for_timeout(500)
                return True
        chk = page.locator('input[type="checkbox"]')
        if await chk.count() > 0:
            for i in range(await chk.count()):
                cb = chk.nth(i)
                try:
                    if not await cb.is_checked():
                        await cb.check()
                        logger.info("Checked a consent checkbox")
                        await page.wait_for_timeout(500)
                        for txt in consent_texts:
                            btn = page.get_by_role("button", name=txt, exact=False)
                            if await btn.count() > 0 and await btn.is_visible():
                                await btn.click()
                                await page.wait_for_timeout(500)
                                return True
                except:
                    pass
        dialog = page.get_by_role("dialog")
        if await dialog.count() > 0 and await dialog.is_visible():
            close_btn = dialog.get_by_role("button", name="Close", exact=False)
            if close_btn.count() == 0:
                close_btn = dialog.locator('[aria-label="Close"]')
            if close_btn.count() > 0 and await close_btn.is_visible():
                logger.info("Closing dialog via close button")
                await close_btn.click()
                await page.wait_for_timeout(500)
                return True
    except Exception as e:
        logger.debug(f"dismiss_overlays error: {e}")
    return False


async def find_chat_input(page):
    """Resilient selector chain for DuckDuckGo AI Chat input."""
    import re

    strategies = [
        # Accessibility-first
        lambda: page.get_by_role("textbox", name=re.compile(r"prompt|message|ask", re.I)),
        lambda: page.get_by_label(re.compile(r"prompt|message|ask", re.I)),
        lambda: page.get_by_placeholder(re.compile(r"prompt|message|ask", re.I)),
        # Test/QA attributes
        lambda: page.locator('[data-testid*="prompt"]'),
        lambda: page.locator('[data-qa*="prompt"]'),
        lambda: page.locator('[data-test*="prompt"]'),
        # Name attributes
        lambda: page.locator('textarea[name*="prompt"]'),
        lambda: page.locator('textarea[name*="user-prompt"]'),
        lambda: page.locator('input[name*="prompt"]'),
        # Class heuristics
        lambda: page.locator('[class*="prompt"]'),
        lambda: page.locator('[class*="chat"]'),
        lambda: page.locator('[class*="input"]'),
        # Structural fallbacks
        lambda: page.locator("textarea"),
        lambda: page.locator('input[type="text"]'),
        lambda: page.locator('[contenteditable="true"]'),
    ]

    for strat in strategies:
        try:
            loc = strat()
            count = await loc.count()
            if count > 0:
                el = loc.first
                if await el.is_visible() and await el.is_enabled():
                    return el
        except Exception:
            continue
    raise Exception("Chat input not found with any strategy")


async def ensure_browser():
    global playwright_instance, browser_instance, page_instance
    if not playwright_instance:
        playwright_instance = await async_playwright().start()
    if not browser_instance:
        browser_instance = await playwright_instance.chromium.launch(
            headless=False, args=["--disable-blink-features=AutomationControlled"]
        )
    if not page_instance:
        context = await browser_instance.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
        )
        page = await context.new_page()
        page_instance = page
        logger.info("Navigating to DuckDuckGo AI Chat...")
        await page.goto(
            "https://duckduckgo.com/?q=DuckDuckGo&ia=chat",
            wait_until="domcontentloaded",
        )
        try:
            await page.wait_for_timeout(3000)
            # Try resilient input finder up to 3 attempts
            for attempt in range(3):
                try:
                    input_el = await find_chat_input(page)
                    if await input_el.is_enabled():
                        logger.info("Input is enabled, ready.")
                        break
                    else:
                        logger.info(f"Input disabled (attempt {attempt + 1}), dismissing overlays...")
                        clicked = await dismiss_overlays(page)
                        if not clicked and attempt == 0:
                            logger.info("Reloading page for clean state...")
                            await page.reload(wait_until="domcontentloaded")
                except Exception as e:
                    logger.warning(f"Could not find input (attempt {attempt + 1}): {e}")
                    if attempt == 0:
                        await page.reload(wait_until="domcontentloaded")
                    else:
                        break
        except Exception as e:
            logger.warning(f"Error during setup: {e}")
    return page_instance


async def ensure_gemini_browser():
    global playwright_instance, browser_instance, gemini_tools
    if GeminiChatTools is None:
        raise Exception("GeminiChatTools not available (import failed)")
    if not playwright_instance:
        playwright_instance = await async_playwright().start()
    if not browser_instance:
        browser_instance = await playwright_instance.chromium.launch(
            headless=False, args=["--disable-blink-features=AutomationControlled"]
        )
    if gemini_tools is None:
        context = await browser_instance.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
        )
        gemini_page = await context.new_page()
        gemini_tools = GeminiChatTools(gemini_page)
        logger.info("Gemini tools initialized with new page")
    return gemini_tools


@app.list_tools()
async def list_tools() -> list[Tool]:
    tools = [
        Tool(
            name="chat_send",
            description="Send a message to DuckDuckGo AI Chat (No login required)",
            inputSchema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        ),
        Tool(
            name="chat_reset",
            description="Clear the conversation history",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="screenshot",
            description="Take a screenshot",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Optional screenshot filename",
                    },
                    "full_page": {
                        "type": "boolean",
                        "description": "Capture full page",
                    },
                },
            },
        ),
        Tool(
            name="navigate",
            description="Navigate the browser to a specific URL",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "wait_until": {
                        "type": "string",
                        "enum": ["load", "domcontentloaded", "networkidle"],
                    },
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="go_back",
            description="Navigate back in browser history",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="reload",
            description="Reload the current page",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="click",
            description="Click on an element",
            inputSchema={
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"],
            },
        ),
        Tool(
            name="fill",
            description="Fill an input field with text",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["selector", "value"],
            },
        ),
        Tool(
            name="hover",
            description="Hover over an element",
            inputSchema={
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"],
            },
        ),
        Tool(
            name="scroll",
            description="Scroll the page",
            inputSchema={
                "type": "object",
                "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
            },
        ),
        Tool(
            name="get_text",
            description="Get text content from an element",
            inputSchema={
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"],
            },
        ),
        Tool(
            name="get_html",
            description="Get HTML content from an element or entire page",
            inputSchema={
                "type": "object",
                "properties": {"selector": {"type": "string"}},
            },
        ),
        Tool(
            name="evaluate",
            description="Execute JavaScript in the browser context",
            inputSchema={
                "type": "object",
                "properties": {"script": {"type": "string"}},
                "required": ["script"],
            },
        ),
        Tool(
            name="search",
            description="Search the web using DuckDuckGo",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="extract",
            description="Extract content from a URL",
            inputSchema={
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        ),
    ]

    if GeminiChatTools is not None:
        tools.extend([
            Tool(
                name="gemini_chat",
                description="Send a message to Gemini Web (gemini.google.com)",
                inputSchema={
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                },
            ),
            Tool(
                name="gemini_reset",
                description="Reset the Gemini chat conversation",
                inputSchema={"type": "object", "properties": {}},
            ),
        ])

    return tools


@app.call_tool()
async def call_tool(
    name: str, arguments: Any
) -> list[TextContent | ImageContent | EmbeddedResource]:
    try:
        page = await ensure_browser()
        if name == "chat_send":
            message = arguments.get("message")
            frame = None
            try:
                iframe_el = page.locator("iframe#jsa")
                if await iframe_el.count() > 0:
                    frame = await iframe_el.content_frame()
            except Exception as e:
                logger.debug(f"Iframe not found: {e}")
            target = frame if frame else page

            # Find input using resilient selector
            try:
                input_el = await find_chat_input(target)
            except Exception as e:
                raise Exception(f"Chat input not found: {e}")

            # Ensure input is enabled; if not, dismiss overlays and retry
            if not await input_el.is_enabled():
                await dismiss_overlays(page)
                await page.wait_for_timeout(1000)
                if not await input_el.is_enabled():
                    await page.reload(wait_until="domcontentloaded")
                    await page.wait_for_timeout(3000)
                    await dismiss_overlays(page)
                    await page.wait_for_timeout(1000)
                    # Re-acquire input after reload
                    try:
                        iframe_el = page.locator("iframe#jsa")
                        if await iframe_el.count() > 0:
                            frame = await iframe_el.content_frame()
                            target = frame if frame else page
                    except:
                        target = page
                    input_el = await find_chat_input(target)
                    if not await input_el.is_enabled():
                        raise Exception("Chat input not available after reload")

            await input_el.fill(message)
            await target.keyboard.press("Enter")
            await page.wait_for_timeout(2000)
            await page.wait_for_timeout(20000)  # longer wait for full response
            try:
                iframe_el = page.locator("iframe#jsa")
                if await iframe_el.count() > 0:
                    frame = await iframe_el.content_frame()
                    target = frame if frame else page
            except Exception as e:
                logger.debug(f"Re-acquire iframe failed: {e}")
            html_text = await target.content()
            # Convert HTML to Markdown using custom converter
            converter = HTMLToMarkdownConverter()
            md = converter.html_to_markdown(html_text)
            # Heuristic extraction: split by user message, take following block
            user_msg = message.strip()
            reply = ""
            if user_msg and user_msg in md:
                parts = md.split(user_msg)
                after = parts[-1]
                lines = [ln.strip() for ln in after.split("\n") if ln.strip()]
                if lines:
                    # Take up to first 15 lines or until a likely UI phrase appears
                    stop_phrases = [
                        "Ask privately",
                        "New Chat",
                        "New Voice Chat",
                        "New Image",
                        "Settings & More",
                        "Stop generating",
                        "Send",
                        "Duck.ai requires JavaScript",
                    ]
                    selected = []
                    for ln in lines:
                        if any(sp in ln for sp in stop_phrases):
                            break
                        selected.append(ln)
                    reply = "\n".join(selected).strip()
            if not reply:
                # Fallback: last non-empty paragraph in the Markdown
                paragraphs = [p.strip() for p in md.split("\n\n") if p.strip()]
                reply = paragraphs[-1] if paragraphs else "No response extracted."
            if not reply or len(reply) < 5:
                reply = "No response extracted."
            return [TextContent(type="text", text=reply)]
        elif name == "chat_reset":
            await page.reload()
            await page.wait_for_timeout(1000)
            return [TextContent(type="text", text="Chat reset (page reloaded).")]
        elif name == "screenshot":
            screenshot_bytes = await page.screenshot(type="png")
            import base64

            b64_img = base64.b64encode(screenshot_bytes).decode("utf-8")
            return [ImageContent(type="image", data=b64_img, mimeType="image/png")]
        elif name == "navigate":
            url = arguments.get("url")
            wait_until = arguments.get("wait_until", "domcontentloaded")
            await page.goto(url, wait_until=wait_until)
            await page.wait_for_timeout(3000)
            return [TextContent(type="text", text=f"Navigated to {url}")]
        elif name == "go_back":
            await page.go_back()
            await page.wait_for_timeout(1000)
            return [TextContent(type="text", text="Navigated back")]
        elif name == "reload":
            await page.reload()
            await page.wait_for_timeout(1000)
            return [TextContent(type="text", text="Page reloaded")]
        elif name == "click":
            selector = arguments.get("selector")
            await page.click(selector)
            await page.wait_for_timeout(500)
            return [TextContent(type="text", text=f"Clicked {selector}")]
        elif name == "fill":
            selector = arguments.get("selector")
            value = arguments.get("value")
            await page.fill(selector, value)
            return [TextContent(type="text", text=f"Filled {selector} with value")]
        elif name == "hover":
            selector = arguments.get("selector")
            await page.hover(selector)
            return [TextContent(type="text", text=f"Hovered over {selector}")]
        elif name == "scroll":
            x = arguments.get("x", 0)
            y = arguments.get("y", 0)
            await page.evaluate(f"window.scrollTo({x}, {y})")
            return [TextContent(type="text", text=f"Scrolled to ({x}, {y})")]
        elif name == "get_text":
            selector = arguments.get("selector")
            text = await page.locator(selector).text_content()
            return [TextContent(type="text", text=text or "")]
        elif name == "get_html":
            selector = arguments.get("selector")
            if selector:
                html = await page.locator(selector).inner_html()
            else:
                html = await page.content()
            return [TextContent(type="text", text=html or "")]
        elif name == "evaluate":
            script = arguments.get("script")
            result = await page.evaluate(script)
            return [TextContent(type="text", text=str(result))]
        elif name == "search":
            query = arguments.get("query")
            await page.goto(
                f"https://duckduckgo.com/?q={query}", wait_until="domcontentloaded"
            )
            await page.wait_for_timeout(2000)
            return [TextContent(type="text", text=f"Searched for: {query}")]
        elif name == "extract":
            url = arguments.get("url")
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            content = await page.content()
            converter = HTMLToMarkdownConverter()
            md = converter.html_to_markdown(content)
            return [
                TextContent(
                    type="text", text=f"Extracted content from {url}:\n{md[:1000]}"
                )
            ]
        elif name == "gemini_chat":
            if GeminiChatTools is None:
                raise Exception("Gemini tools not available (missing dependency)")
            tools = await ensure_gemini_browser()
            message = arguments.get("message")
            response = await tools.send_message(message)
            return [TextContent(type="text", text=response)]
        elif name == "gemini_reset":
            if GeminiChatTools is None:
                raise Exception("Gemini tools not available (missing dependency)")
            tools = await ensure_gemini_browser()
            result = await tools.reset_chat()
            return [TextContent(type="text", text=result)]
        else:
            raise ValueError(f"Unknown tool: {name}")
    except Exception as e:
        logger.exception(f"Error in tool {name}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
