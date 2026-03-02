"""
Tests for the MCP server handlers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from server import list_tools, call_tool

def make_mock_locator(enable=True, count=1, texts=None):
    m = MagicMock()
    m.count = AsyncMock(return_value=count)
    m.is_visible = AsyncMock(return_value=True)
    m.is_enabled = AsyncMock(return_value=enable)
    m.fill = AsyncMock()
    m.press = AsyncMock()
    if texts is not None:
        m.all_text_contents = AsyncMock(return_value=texts)
    else:
        m.all_text_contents = AsyncMock(return_value=["Mock response"])
    m.text_content = AsyncMock(return_value="Mock response")
    m.content = AsyncMock(return_value="<div>Mock</div>")
    return m

@pytest.fixture
def mock_page():
    page = MagicMock()
    # Async methods
    page.fill = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.reload = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"fakeimage")
    page.content = AsyncMock(return_value="<html>Mock</html>")
    # locator side effect based on selector
    def locator_side_effect(selector):
        if selector == 'iframe#jsa':
            # No iframe in tests
            m = MagicMock()
            m.count = AsyncMock(return_value=0)
            m.is_visible = AsyncMock(return_value=False)
            return m
        # For other selectors, return a standard enabled locator
        return make_mock_locator(enable=True, count=1)
    page.locator = MagicMock(side_effect=locator_side_effect)
    # get_by_role chain
    role_mock = MagicMock()
    role_mock.count = AsyncMock(return_value=0)
    role_mock.is_visible = AsyncMock(return_value=False)
    role_mock.click = AsyncMock()
    page.get_by_role = MagicMock(return_value=role_mock)
    # Ensure content_frame not accidentally used
    page.content_frame = AsyncMock(return_value=page)  # fallback if somehow used
    return page

@pytest.mark.asyncio
async def test_list_tools():
    tools = await list_tools()
    names = [t.name for t in tools]
    assert "chat_send" in names
    assert "chat_reset" in names
    assert "screenshot" in names

@pytest.mark.asyncio
async def test_chat_send(mock_page):
    with patch('server.ensure_browser', new_callable=AsyncMock, return_value=mock_page), \
         patch('server.dismiss_overlays', new_callable=AsyncMock, return_value=False):
        result = await call_tool("chat_send", {"message": "Hello"})
    assert len(result) >= 1
    assert result[0].type == "text"
    # The mock locator returns "Mock response"
    assert "Mock response" in result[0].text

@pytest.mark.asyncio
async def test_chat_reset(mock_page):
    with patch('server.ensure_browser', new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("chat_reset", {})
    assert len(result) == 1
    assert result[0].type == "text"
    assert "reset" in result[0].text.lower()

@pytest.mark.asyncio
async def test_screenshot(mock_page):
    with patch('server.ensure_browser', new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("screenshot", {})
    assert len(result) == 1
    assert result[0].type == "image"
    assert result[0].mimeType == "image/png"
    assert isinstance(result[0].data, str) and len(result[0].data) > 0
