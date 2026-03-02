"""Interaction tool implementations."""

from patchright.async_api import Page


class InteractionTools:
    """Tools for DOM interaction."""

    def __init__(self, page: Page):
        self.page = page

    async def click(self, selector: str) -> str:
        """Click element."""
        await self.page.click(selector)
        return f"Clicked: {selector}"

    async def fill(self, selector: str, value: str) -> str:
        """Fill input field."""
        await self.page.fill(selector, value)
        return f"Filled {selector}"

    async def hover(self, selector: str) -> str:
        """Hover over element."""
        await self.page.hover(selector)
        return f"Hovered: {selector}"

    async def scroll(self, x: int = 0, y: int = 0) -> str:
        """Scroll page."""
        await self.page.evaluate(f"window.scrollBy({x}, {y})")
        return f"Scrolled by ({x}, {y})"
