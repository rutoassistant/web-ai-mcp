"""
Tests for InteractionTools in src/tools/interaction.py
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.tools.interaction import InteractionTools


def create_mock_page():
    """Create a mock Playwright page object."""
    page = MagicMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.hover = AsyncMock()
    page.evaluate = AsyncMock()
    return page


class TestInteractionTools:
    """Test cases for InteractionTools class."""

    def test_init(self):
        """Test initialization of InteractionTools."""
        page = create_mock_page()
        tools = InteractionTools(page)

        assert tools.page is page

    @pytest.mark.asyncio
    async def test_click(self):
        """Test click action."""
        page = create_mock_page()

        tools = InteractionTools(page)
        result = await tools.click("#button")

        page.click.assert_called_once_with("#button")
        assert "#button" in result
        assert "Clicked" in result

    @pytest.mark.asyncio
    async def test_click_various_selectors(self):
        """Test click with various selector formats."""
        page = create_mock_page()
        tools = InteractionTools(page)

        selectors = [
            ".class-selector",
            "[data-testid=test]",
            "button.submit",
            "#main-button",
        ]

        for selector in selectors:
            page.click.reset_mock()
            result = await tools.click(selector)
            page.click.assert_called_once_with(selector)
            assert selector in result

    @pytest.mark.asyncio
    async def test_fill(self):
        """Test fill action."""
        page = create_mock_page()

        tools = InteractionTools(page)
        result = await tools.fill("#input", "test value")

        page.fill.assert_called_once_with("#input", "test value")
        assert "#input" in result
        assert "Filled" in result

    @pytest.mark.asyncio
    async def test_fill_empty_value(self):
        """Test fill with empty value."""
        page = create_mock_page()

        tools = InteractionTools(page)
        result = await tools.fill("#input", "")

        page.fill.assert_called_once_with("#input", "")

    @pytest.mark.asyncio
    async def test_fill_special_characters(self):
        """Test fill with special characters."""
        page = create_mock_page()

        tools = InteractionTools(page)
        special_value = "Test <script>alert('xss')</script>"
        result = await tools.fill("#input", special_value)

        page.fill.assert_called_once_with("#input", special_value)

    @pytest.mark.asyncio
    async def test_hover(self):
        """Test hover action."""
        page = create_mock_page()

        tools = InteractionTools(page)
        result = await tools.hover("#element")

        page.hover.assert_called_once_with("#element")
        assert "#element" in result
        assert "Hovered" in result

    @pytest.mark.asyncio
    async def test_hover_various_selectors(self):
        """Test hover with various selector formats."""
        page = create_mock_page()
        tools = InteractionTools(page)

        selectors = [".menu-item", "[data-role=menu]", "li.nav-item"]

        for selector in selectors:
            page.hover.reset_mock()
            result = await tools.hover(selector)
            page.hover.assert_called_once_with(selector)

    @pytest.mark.asyncio
    async def test_scroll_default(self):
        """Test scroll with default parameters."""
        page = create_mock_page()

        tools = InteractionTools(page)
        result = await tools.scroll()

        page.evaluate.assert_called_once()
        assert "(0, 0)" in result

    @pytest.mark.asyncio
    async def test_scroll_x_only(self):
        """Test scroll with x offset only."""
        page = create_mock_page()

        tools = InteractionTools(page)
        result = await tools.scroll(x=100)

        page.evaluate.assert_called_once()
        assert "(100, 0)" in result

    @pytest.mark.asyncio
    async def test_scroll_y_only(self):
        """Test scroll with y offset only."""
        page = create_mock_page()

        tools = InteractionTools(page)
        result = await tools.scroll(y=200)

        page.evaluate.assert_called_once()
        assert "(0, 200)" in result

    @pytest.mark.asyncio
    async def test_scroll_both(self):
        """Test scroll with both x and y offsets."""
        page = create_mock_page()

        tools = InteractionTools(page)
        result = await tools.scroll(x=150, y=300)

        page.evaluate.assert_called_once()
        assert "(150, 300)" in result

    @pytest.mark.asyncio
    async def test_scroll_negative(self):
        """Test scroll with negative offsets."""
        page = create_mock_page()

        tools = InteractionTools(page)
        result = await tools.scroll(x=-50, y=-100)

        page.evaluate.assert_called_once()
        assert "(-50, -100)" in result


class TestInteractionToolsReturnValues:
    """Test return value formats."""

    @pytest.mark.asyncio
    async def test_click_return_format(self):
        """Test click returns expected format."""
        page = create_mock_page()
        tools = InteractionTools(page)

        result = await tools.click(".btn")

        assert result == "Clicked: .btn"

    @pytest.mark.asyncio
    async def test_fill_return_format(self):
        """Test fill returns expected format."""
        page = create_mock_page()
        tools = InteractionTools(page)

        result = await tools.fill("#field", "value")

        assert result == "Filled #field"

    @pytest.mark.asyncio
    async def test_hover_return_format(self):
        """Test hover returns expected format."""
        page = create_mock_page()
        tools = InteractionTools(page)

        result = await tools.hover(".el")

        assert result == "Hovered: .el"

    @pytest.mark.asyncio
    async def test_scroll_return_format(self):
        """Test scroll returns expected format."""
        page = create_mock_page()
        tools = InteractionTools(page)

        result = await tools.scroll(x=10, y=20)

        assert "Scrolled by (10, 20)" == result
