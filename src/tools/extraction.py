"""Extraction tool implementations."""

import base64
from typing import Any
from patchright.async_api import Page


class ExtractionTools:
    """Tools for content extraction."""

    def __init__(self, page: Page):
        self.page = page

    async def screenshot(self, name: str, selector: str = None, full_page: bool = False) -> str:
        """Capture screenshot."""
        path = f"/tmp/{name}.png"

        if selector:
            element = await self.page.query_selector(selector)
            if not element:
                raise ValueError(f"Element not found: {selector}")
            await element.screenshot(path=path)
        else:
            await self.page.screenshot(path=path, full_page=full_page)

        return path

    async def evaluate(self, script: str) -> Any:
        """Execute JavaScript and return result."""
        return await self.page.evaluate(script)

    async def get_text(self, selector: str = None) -> str:
        """Extract text content."""
        if selector:
            element = await self.page.query_selector(selector)
            if not element:
                return ""
            return await element.text_content()
        return await self.page.evaluate("document.body.innerText")

    async def get_html(self) -> str:
        """Get page HTML."""
        return await self.page.content()
