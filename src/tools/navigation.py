"""Navigation tool implementations."""

from patchright.async_api import Page


class NavigationTools:
    """Tools for browser navigation."""

    def __init__(self, page: Page):
        self.page = page

    async def navigate(self, url: str, wait_until: str = "load") -> str:
        """Navigate to URL."""
        await self.page.goto(url, wait_until=wait_until)
        return f"Navigated to {url}"

    async def go_back(self) -> str:
        """Navigate back in history."""
        await self.page.go_back()
        return "Navigated back"

    async def reload(self) -> str:
        """Reload current page."""
        await self.page.reload()
        return "Page reloaded"
