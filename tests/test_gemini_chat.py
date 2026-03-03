"""
Tests for GeminiChatTools in src/tools/gemini_chat.py
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from patchright.async_api import TimeoutError as PlaywrightTimeoutError

from src.tools.gemini_chat import GeminiChatTools


def create_mock_page():
    """Create a mock Playwright page object."""
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.evaluate = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.press = AsyncMock()
    return page


def create_mock_element():
    """Create a mock element."""
    element = MagicMock()
    element.fill = AsyncMock()
    element.click = AsyncMock()
    element.inner_text = AsyncMock(return_value="Test response")
    element.text_content = AsyncMock(return_value="Test content")
    return element


class TestGeminiChatTools:
    """Test cases for GeminiChatTools class."""

    def test_init(self):
        """Test initialization of GeminiChatTools."""
        page = create_mock_page()
        tools = GeminiChatTools(page)

        assert tools.page is page
        assert tools.GEMINI_URL == "https://gemini.google.com"
        assert tools._chat_initialized is False

    def test_input_selectors_defined(self):
        """Test that input selectors are properly defined."""
        page = create_mock_page()
        tools = GeminiChatTools(page)

        assert len(tools.INPUT_SELECTORS) > 0
        assert any("textarea" in s for s in tools.INPUT_SELECTORS)

    def test_send_button_selectors_defined(self):
        """Test that send button selectors are properly defined."""
        page = create_mock_page()
        tools = GeminiChatTools(page)

        assert len(tools.SEND_BUTTON_SELECTORS) > 0

    def test_response_selectors_defined(self):
        """Test that response selectors are properly defined."""
        page = create_mock_page()
        tools = GeminiChatTools(page)

        assert len(tools.RESPONSE_SELECTORS) > 0

    @pytest.mark.asyncio
    async def test_find_element_success(self):
        """Test _find_element finds an element."""
        page = create_mock_page()
        mock_element = create_mock_element()
        page.wait_for_selector = AsyncMock(return_value=mock_element)

        tools = GeminiChatTools(page)
        result = await tools._find_element(["selector1", "selector2"], timeout=1000)

        assert result is mock_element

    @pytest.mark.asyncio
    async def test_find_element_timeout(self):
        """Test _find_element returns None on timeout."""
        page = create_mock_page()
        page.wait_for_selector = AsyncMock(side_effect=PlaywrightTimeoutError())

        tools = GeminiChatTools(page)
        result = await tools._find_element(["selector1", "selector2"], timeout=1000)

        assert result is None

    @pytest.mark.asyncio
    async def test_ensure_chat_page_success(self):
        """Test _ensure_chat_page successfully initializes."""
        page = create_mock_page()
        mock_element = create_mock_element()
        page.wait_for_selector = AsyncMock(return_value=mock_element)
        page.goto = AsyncMock()

        tools = GeminiChatTools(page)
        result = await tools._ensure_chat_page()

        assert result is True
        assert tools._chat_initialized is True

    @pytest.mark.asyncio
    async def test_ensure_chat_page_failure(self):
        """Test _ensure_chat_page fails when no input found."""
        page = create_mock_page()
        page.wait_for_selector = AsyncMock(return_value=None)
        page.goto = AsyncMock()

        tools = GeminiChatTools(page)
        result = await tools._ensure_chat_page()

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_popups(self):
        """Test _handle_popups handles popup dismissals."""
        page = create_mock_page()
        mock_button = create_mock_element()
        page.wait_for_selector = AsyncMock(return_value=mock_button)

        tools = GeminiChatTools(page)
        await tools._handle_popups()

        mock_button.click.assert_called()

    @pytest.mark.asyncio
    async def test_handle_popups_no_popup(self):
        """Test _handle_popups when no popup present."""
        page = create_mock_page()
        page.wait_for_selector = AsyncMock(side_effect=PlaywrightTimeoutError())

        tools = GeminiChatTools(page)
        await tools._handle_popups()

    @pytest.mark.asyncio
    async def test_send_message_initialization_failure(self):
        """Test send_message when chat initialization fails."""
        page = create_mock_page()
        page.goto = AsyncMock()
        page.wait_for_selector = AsyncMock(return_value=None)

        tools = GeminiChatTools(page)
        result = await tools.send_message("Hello")

        assert "Error: Failed to initialize" in result

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        """Test send_message successfully sends and gets response."""
        page = create_mock_page()
        mock_element = create_mock_element()
        mock_element.inner_text = AsyncMock(return_value="Test response text")

        page.wait_for_selector = AsyncMock(return_value=mock_element)
        page.wait_for_load_state = AsyncMock()
        page.evaluate = AsyncMock(return_value="")

        tools = GeminiChatTools(page)
        tools._chat_initialized = True

        result = await tools.send_message("Hello")

        assert "Test response text" in result or "response" in result.lower()

    @pytest.mark.asyncio
    async def test_send_message_timeout(self):
        """Test send_message handles timeout."""
        page = create_mock_page()
        mock_element = create_mock_element()

        page.wait_for_selector = AsyncMock(return_value=mock_element)
        page.wait_for_load_state = AsyncMock(side_effect=PlaywrightTimeoutError())

        tools = GeminiChatTools(page)
        tools._chat_initialized = True

        result = await tools.send_message("Hello")

        assert "Error" in result

    @pytest.mark.asyncio
    async def test_send_message_press_enter(self):
        """Test send_message uses Enter when no send button found."""
        page = create_mock_page()
        mock_element = create_mock_element()
        mock_element.inner_text = AsyncMock(return_value="Response")

        def selector_side_effect(selector, timeout=None):
            if "button" in selector.lower():
                return None
            return mock_element

        page.wait_for_selector = AsyncMock(side_effect=selector_side_effect)
        page.wait_for_load_state = AsyncMock()

        tools = GeminiChatTools(page)
        tools._chat_initialized = True

        result = await tools.send_message("Hello")

        mock_element.press.assert_called_with("Enter")

    @pytest.mark.asyncio
    async def test_wait_for_response_success(self):
        """Test _wait_for_response successfully extracts response."""
        page = create_mock_page()
        mock_element = create_mock_element()
        mock_element.inner_text = AsyncMock(return_value="Gemini response text")

        page.wait_for_selector = AsyncMock(return_value=mock_element)
        page.wait_for_load_state = AsyncMock()

        tools = GeminiChatTools(page)
        result = await tools._wait_for_response(timeout=5000)

        assert "Gemini response text" in result

    @pytest.mark.asyncio
    async def test_wait_for_response_fallback(self):
        """Test _wait_for_response uses fallback evaluation."""
        page = create_mock_page()

        page.wait_for_selector = AsyncMock(return_value=None)
        page.wait_for_load_state = AsyncMock()
        page.evaluate = AsyncMock(return_value="Fallback response text")

        tools = GeminiChatTools(page)
        result = await tools._wait_for_response(timeout=5000)

        assert "Fallback response text" in result

    @pytest.mark.asyncio
    async def test_reset_chat_button_found(self):
        """Test reset_chat when reset button found."""
        page = create_mock_page()
        mock_button = create_mock_element()
        page.wait_for_selector = AsyncMock(return_value=mock_button)
        page.goto = AsyncMock()

        tools = GeminiChatTools(page)
        tools._chat_initialized = True

        result = await tools.reset_chat()

        assert "successfully" in result.lower() or "reset" in result.lower()
        assert tools._chat_initialized is False

    @pytest.mark.asyncio
    async def test_reset_chat_refresh_page(self):
        """Test reset_chat refreshes page when no button found."""
        page = create_mock_page()
        page.wait_for_selector = AsyncMock(return_value=None)
        page.goto = AsyncMock()

        tools = GeminiChatTools(page)
        tools._chat_initialized = True

        result = await tools.reset_chat()

        assert "successfully" in result.lower() or "refreshed" in result.lower()
        assert tools._chat_initialized is False


class TestGeminiChatToolsModels:
    """Test model validation for GeminiChatTools."""

    def test_selectors_are_strings(self):
        """Test all selectors are properly formatted strings."""
        page = create_mock_page()
        tools = GeminiChatTools(page)

        for selector in tools.INPUT_SELECTORS:
            assert isinstance(selector, str)
            assert len(selector) > 0

        for selector in tools.SEND_BUTTON_SELECTORS:
            assert isinstance(selector, str)
            assert len(selector) > 0

        for selector in tools.RESPONSE_SELECTORS:
            assert isinstance(selector, str)
            assert len(selector) > 0
