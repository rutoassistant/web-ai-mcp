"""
Tests for NavigationTools in src/tools/navigation.py
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.tools.navigation import NavigationTools


def create_mock_page():
    """Create a mock Playwright page object."""
    page = MagicMock()
    page.goto = AsyncMock()
    page.go_back = AsyncMock()
    page.reload = AsyncMock()
    return page


class TestNavigationTools:
    """Test cases for NavigationTools class."""

    def test_init(self):
        """Test initialization of NavigationTools."""
        page = create_mock_page()
        tools = NavigationTools(page)

        assert tools.page is page

    @pytest.mark.asyncio
    async def test_navigate_default(self):
        """Test navigate with default wait_until."""
        page = create_mock_page()

        tools = NavigationTools(page)
        result = await tools.navigate("https://example.com")

        page.goto.assert_called_once_with("https://example.com", wait_until="load")
        assert "example.com" in result

    @pytest.mark.asyncio
    async def test_navigate_networkidle(self):
        """Test navigate with networkidle wait_until."""
        page = create_mock_page()

        tools = NavigationTools(page)
        result = await tools.navigate("https://example.com", wait_until="networkidle")

        page.goto.assert_called_once_with(
            "https://example.com", wait_until="networkidle"
        )
        assert "example.com" in result

    @pytest.mark.asyncio
    async def test_navigate_domcontentloaded(self):
        """Test navigate with domcontentloaded wait_until."""
        page = create_mock_page()

        tools = NavigationTools(page)
        result = await tools.navigate(
            "https://example.com", wait_until="domcontentloaded"
        )

        page.goto.assert_called_once_with(
            "https://example.com", wait_until="domcontentloaded"
        )
        assert "example.com" in result

    @pytest.mark.asyncio
    async def test_go_back(self):
        """Test go_back navigation."""
        page = create_mock_page()

        tools = NavigationTools(page)
        result = await tools.go_back()

        page.go_back.assert_called_once()
        assert "back" in result.lower()

    @pytest.mark.asyncio
    async def test_reload(self):
        """Test page reload."""
        page = create_mock_page()

        tools = NavigationTools(page)
        result = await tools.reload()

        page.reload.assert_called_once()
        assert "reload" in result.lower()


class TestNavigationToolsReturnValues:
    """Test return values for navigation methods."""

    @pytest.mark.asyncio
    async def test_navigate_returns_correct_message(self):
        """Test navigate returns expected message format."""
        page = create_mock_page()

        tools = NavigationTools(page)
        result = await tools.navigate("https://test.com")

        assert "Navigated to https://test.com" == result

    @pytest.mark.asyncio
    async def test_go_back_returns_correct_message(self):
        """Test go_back returns expected message."""
        page = create_mock_page()

        tools = NavigationTools(page)
        result = await tools.go_back()

        assert result == "Navigated back"

    @pytest.mark.asyncio
    async def test_reload_returns_correct_message(self):
        """Test reload returns expected message."""
        page = create_mock_page()

        tools = NavigationTools(page)
        result = await tools.reload()

        assert result == "Page reloaded"
