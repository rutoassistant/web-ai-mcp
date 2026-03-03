"""
Tests for ExtractionTools in src/tools/extraction.py
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.tools.extraction import ExtractionTools


def create_mock_page():
    """Create a mock Playwright page object."""
    page = MagicMock()
    page.screenshot = AsyncMock()
    page.evaluate = AsyncMock()
    page.query_selector = AsyncMock()
    page.content = AsyncMock()
    return page


def create_mock_element():
    """Create a mock element."""
    element = MagicMock()
    element.screenshot = AsyncMock()
    element.text_content = AsyncMock(return_value="Element text")
    return element


class TestExtractionTools:
    """Test cases for ExtractionTools class."""

    def test_init(self):
        """Test initialization of ExtractionTools."""
        page = create_mock_page()
        tools = ExtractionTools(page)

        assert tools.page is page

    @pytest.mark.asyncio
    async def test_screenshot_full_page(self):
        """Test full page screenshot."""
        page = create_mock_page()

        tools = ExtractionTools(page)
        result = await tools.screenshot("test_image")

        page.screenshot.assert_called_once()
        call_kwargs = page.screenshot.call_args[1]
        assert call_kwargs.get("full_page", False) is False
        assert "/tmp/test_image.png" in result

    @pytest.mark.asyncio
    async def test_screenshot_full_page_true(self):
        """Test screenshot with full_page=True."""
        page = create_mock_page()

        tools = ExtractionTools(page)
        result = await tools.screenshot("test", full_page=True)

        call_kwargs = page.screenshot.call_args[1]
        assert call_kwargs.get("full_page") is True

    @pytest.mark.asyncio
    async def test_screenshot_with_selector(self):
        """Test screenshot of specific element."""
        page = create_mock_page()
        mock_element = create_mock_element()
        page.query_selector = AsyncMock(return_value=mock_element)

        tools = ExtractionTools(page)
        result = await tools.screenshot("element_image", selector=".target")

        page.query_selector.assert_called_once_with(".target")
        mock_element.screenshot.assert_called_once()
        assert "/tmp/element_image.png" in result

    @pytest.mark.asyncio
    async def test_screenshot_element_not_found(self):
        """Test screenshot when element not found."""
        page = create_mock_page()
        page.query_selector = AsyncMock(return_value=None)

        tools = ExtractionTools(page)

        with pytest.raises(ValueError, match="Element not found"):
            await tools.screenshot("test", selector=".missing")

    @pytest.mark.asyncio
    async def test_evaluate_script(self):
        """Test JavaScript evaluation."""
        page = create_mock_page()
        page.evaluate = AsyncMock(return_value="evaluated result")

        tools = ExtractionTools(page)
        result = await tools.evaluate("return document.title")

        page.evaluate.assert_called_once_with("return document.title")
        assert result == "evaluated result"

    @pytest.mark.asyncio
    async def test_evaluate_complex_script(self):
        """Test evaluation of complex JavaScript."""
        page = create_mock_page()
        page.evaluate = AsyncMock(return_value={"key": "value"})

        tools = ExtractionTools(page)
        result = await tools.evaluate("() => ({key: 'value'})")

        page.evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_text_with_selector(self):
        """Test get_text with element selector."""
        page = create_mock_page()
        mock_element = create_mock_element()
        page.query_selector = AsyncMock(return_value=mock_element)

        tools = ExtractionTools(page)
        result = await tools.get_text(".content")

        page.query_selector.assert_called_once_with(".content")
        mock_element.text_content.assert_called_once()
        assert result == "Element text"

    @pytest.mark.asyncio
    async def test_get_text_element_not_found(self):
        """Test get_text when element not found."""
        page = create_mock_page()
        page.query_selector = AsyncMock(return_value=None)

        tools = ExtractionTools(page)
        result = await tools.get_text(".missing")

        assert result == ""

    @pytest.mark.asyncio
    async def test_get_text_no_selector(self):
        """Test get_text without selector gets page text."""
        page = create_mock_page()
        page.evaluate = AsyncMock(return_value="Page text content")

        tools = ExtractionTools(page)
        result = await tools.get_text()

        page.evaluate.assert_called_once_with("document.body.innerText")
        assert result == "Page text content"

    @pytest.mark.asyncio
    async def test_get_html(self):
        """Test get_html returns page content."""
        page = create_mock_page()
        page.content = AsyncMock(return_value="<html><body>Test</body></html>")

        tools = ExtractionTools(page)
        result = await tools.get_html()

        page.content.assert_called_once()
        assert "<html>" in result


class TestExtractionToolsReturnValues:
    """Test return values for extraction methods."""

    @pytest.mark.asyncio
    async def test_screenshot_returns_path(self):
        """Test screenshot returns file path."""
        page = create_mock_page()

        tools = ExtractionTools(page)
        result = await tools.screenshot("my_screenshot")

        assert result == "/tmp/my_screenshot.png"

    @pytest.mark.asyncio
    async def test_screenshot_custom_name(self):
        """Test screenshot with custom name."""
        page = create_mock_page()

        tools = ExtractionTools(page)
        result = await tools.screenshot("custom-name-123")

        assert result == "/tmp/custom-name-123.png"


class TestExtractionToolsEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_evaluate_returns_none(self):
        """Test evaluate when script returns None."""
        page = create_mock_page()
        page.evaluate = AsyncMock(return_value=None)

        tools = ExtractionTools(page)
        result = await tools.evaluate("() => null")

        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_returns_number(self):
        """Test evaluate when script returns number."""
        page = create_mock_page()
        page.evaluate = AsyncMock(return_value=42)

        tools = ExtractionTools(page)
        result = await tools.evaluate("() => 42")

        assert result == 42

    @pytest.mark.asyncio
    async def test_evaluate_returns_array(self):
        """Test evaluate when script returns array."""
        page = create_mock_page()
        page.evaluate = AsyncMock(return_value=[1, 2, 3])

        tools = ExtractionTools(page)
        result = await tools.evaluate("() => [1, 2, 3]")

        assert result == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_get_text_whitespace_handling(self):
        """Test get_text properly handles whitespace."""
        page = create_mock_page()
        mock_element = create_mock_element()
        mock_element.text_content = AsyncMock(return_value="  Text  with   spaces  ")
        page.query_selector = AsyncMock(return_value=mock_element)

        tools = ExtractionTools(page)
        result = await tools.get_text(".text")

        assert "Text" in result
