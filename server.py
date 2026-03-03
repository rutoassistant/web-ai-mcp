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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("web-ai-mcp")

app = Server("web-ai-mcp")

playwright_instance: Optional[Playwright] = None
browser_instance: Optional[Browser] = None
page_instance: Optional[Page] = None
current_model: str = "gpt-4o-mini"


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
            for attempt in range(3):
                input_selectors = [
                    'textarea[name="user-prompt"]',
                    'textarea[placeholder*="Ask"]',
                    "textarea",
                ]
                input_el = None
                for sel in input_selectors:
                    el = page.locator(sel)
                    if await el.count() > 0:
                        input_el = el
                        break
                if input_el:
                    is_enabled = await input_el.is_enabled()
                    if is_enabled:
                        logger.info("Input is enabled, ready.")
                        break
                    else:
                        logger.info(
                            f"Input disabled (attempt {attempt + 1}), dismissing overlays..."
                        )
                        clicked = await dismiss_overlays(page)
                        if not clicked and attempt == 0:
                            logger.info("Reloading page for clean state...")
                            await page.reload(wait_until="domcontentloaded")
                else:
                    logger.warning("Textarea not found")
                    break
        except Exception as e:
            logger.warning(f"Error during setup: {e}")
    return page_instance


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
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
            input_selectors = [
                'textarea[name="user-prompt"]',
                'textarea[placeholder*="Ask"]',
                "textarea",
            ]
            input_selector = None
            for sel in input_selectors:
                if await target.locator(sel).count() > 0:
                    input_selector = sel
                    break
            if not input_selector:
                raise Exception("Input textarea not found")
            await target.wait_for_selector(
                input_selector, state="visible", timeout=10000
            )
            input_el = target.locator(input_selector)
            if not await input_el.is_enabled():
                await dismiss_overlays(page)
                await page.wait_for_timeout(1000)
                if not await input_el.is_enabled():
                    await page.reload(wait_until="domcontentloaded")
                    await page.wait_for_timeout(3000)
                    await dismiss_overlays(page)
                    await page.wait_for_timeout(1000)
                    try:
                        iframe_el = page.locator("iframe#jsa")
                        if await iframe_el.count() > 0:
                            frame = await iframe_el.content_frame()
                            target = frame if frame else page
                    except:
                        target = page
                    input_el = target.locator(input_selector)
                    if await input_el.count() == 0 or not await input_el.is_enabled():
                        raise Exception("Input textarea not available after reload")
            await target.fill(input_selector, message)
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
