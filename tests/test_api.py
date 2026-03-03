"""
Tests for the MCP server handlers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import base64

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
    page.content = AsyncMock(
        return_value="<html><body>Hello Mock response</body></html>"
    )

    # locator side effect based on selector
    def locator_side_effect(selector):
        if selector == "iframe#jsa":
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
    with (
        patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page),
        patch("server.dismiss_overlays", new_callable=AsyncMock, return_value=False),
    ):
        result = await call_tool("chat_send", {"message": "Hello"})
    assert len(result) >= 1
    assert result[0].type == "text"
    # The mock locator returns "Mock response"
    assert "Mock response" in result[0].text


@pytest.mark.asyncio
async def test_chat_reset(mock_page):
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("chat_reset", {})
    assert len(result) == 1
    assert result[0].type == "text"
    assert "reset" in result[0].text.lower()


@pytest.mark.asyncio
async def test_screenshot(mock_page):
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("screenshot", {})
    assert len(result) == 1
    assert result[0].type == "image"
    assert result[0].mimeType == "image/png"
    assert isinstance(result[0].data, str) and len(result[0].data) > 0


@pytest.mark.asyncio
async def test_list_tools_contains_all_tools():
    """Test that list_tools returns expected tools."""
    tools = await list_tools()
    names = [t.name for t in tools]

    expected_tools = [
        "chat_send",
        "chat_reset",
        "screenshot",
        "navigate",
        "go_back",
        "reload",
        "click",
        "fill",
        "hover",
        "scroll",
        "get_text",
        "get_html",
        "evaluate",
        "search",
        "extract",
    ]

    for tool in expected_tools:
        assert tool in names, f"Tool {tool} not found in tools list"


@pytest.mark.asyncio
async def test_call_tool_unknown_tool():
    """Test calling unknown tool returns error."""
    result = await call_tool("unknown_tool", {})

    assert len(result) >= 1
    assert result[0].type == "text"
    assert "error" in result[0].text.lower() or "not found" in result[0].text.lower()


@pytest.mark.asyncio
async def test_call_tool_empty_message(mock_page):
    """Test chat_send with empty message."""
    with (
        patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page),
        patch("server.dismiss_overlays", new_callable=AsyncMock, return_value=False),
    ):
        result = await call_tool("chat_send", {"message": ""})

    assert len(result) >= 1


@pytest.mark.asyncio
async def test_call_tool_long_message(mock_page):
    """Test chat_send with long message."""
    long_message = "A" * 10000

    with (
        patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page),
        patch("server.dismiss_overlays", new_callable=AsyncMock, return_value=False),
    ):
        result = await call_tool("chat_send", {"message": long_message})

    assert len(result) >= 1


@pytest.mark.asyncio
async def test_navigate_tool(mock_page):
    """Test navigate tool."""
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("navigate", {"url": "https://example.com"})

    assert len(result) >= 1
    assert result[0].type == "text"


@pytest.mark.asyncio
async def test_go_back_tool(mock_page):
    """Test go_back tool."""
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("go_back", {})

    assert len(result) >= 1
    assert result[0].type == "text"


@pytest.mark.asyncio
async def test_reload_tool(mock_page):
    """Test reload tool."""
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("reload", {})

    assert len(result) >= 1
    assert result[0].type == "text"


@pytest.mark.asyncio
async def test_click_tool(mock_page):
    """Test click tool."""
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("click", {"selector": "#button"})

    assert len(result) >= 1
    assert result[0].type == "text"


@pytest.mark.asyncio
async def test_fill_tool(mock_page):
    """Test fill tool."""
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("fill", {"selector": "#input", "value": "test"})

    assert len(result) >= 1
    assert result[0].type == "text"


@pytest.mark.asyncio
async def test_hover_tool(mock_page):
    """Test hover tool."""
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("hover", {"selector": "#element"})

    assert len(result) >= 1
    assert result[0].type == "text"


@pytest.mark.asyncio
async def test_scroll_tool(mock_page):
    """Test scroll tool."""
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("scroll", {"x": 0, "y": 100})

    assert len(result) >= 1
    assert result[0].type == "text"


@pytest.mark.asyncio
async def test_get_text_tool(mock_page):
    """Test get_text tool."""
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("get_text", {"selector": "body"})

    assert len(result) >= 1
    assert result[0].type == "text"


@pytest.mark.asyncio
async def test_get_html_tool(mock_page):
    """Test get_html tool."""
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("get_html", {})

    assert len(result) >= 1
    assert result[0].type == "text"


@pytest.mark.asyncio
async def test_evaluate_tool(mock_page):
    """Test evaluate tool."""
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("evaluate", {"script": "return document.title"})

    assert len(result) >= 1
    assert result[0].type == "text"


@pytest.mark.asyncio
async def test_search_tool(mock_page):
    """Test search tool."""
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("search", {"query": "test query"})

    assert len(result) >= 1


@pytest.mark.asyncio
async def test_extract_tool(mock_page):
    """Test extract tool."""
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("extract", {"url": "https://example.com"})

    assert len(result) >= 1


@pytest.mark.asyncio
async def test_screenshot_with_name(mock_page):
    """Test screenshot tool with custom name."""
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("screenshot", {"name": "custom_name"})

    assert len(result) == 1
    assert result[0].type == "image"


@pytest.mark.asyncio
async def test_screenshot_full_page(mock_page):
    """Test screenshot tool with full_page option."""
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("screenshot", {"full_page": True})

    assert len(result) == 1
    assert result[0].type == "image"


@pytest.mark.asyncio
async def test_chat_send_with_special_characters(mock_page):
    """Test chat_send with special characters in message."""
    special_message = "Hello <world> & 'test' \"quotes\""

    with (
        patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page),
        patch("server.dismiss_overlays", new_callable=AsyncMock, return_value=False),
    ):
        result = await call_tool("chat_send", {"message": special_message})

    assert len(result) >= 1


@pytest.mark.asyncio
async def test_chat_send_with_unicode(mock_page):
    """Test chat_send with unicode characters."""
    unicode_message = "Hello 世界 🌍 émojis"

    with (
        patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page),
        patch("server.dismiss_overlays", new_callable=AsyncMock, return_value=False),
    ):
        result = await call_tool("chat_send", {"message": unicode_message})

    assert len(result) >= 1


@pytest.mark.asyncio
async def test_scroll_with_coordinates(mock_page):
    """Test scroll tool with various coordinates."""
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool("scroll", {"x": 50, "y": 200})

    assert len(result) >= 1
    assert result[0].type == "text"


@pytest.mark.asyncio
async def test_navigate_with_wait_until(mock_page):
    """Test navigate tool with custom wait_until."""
    with patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page):
        result = await call_tool(
            "navigate", {"url": "https://example.com", "wait_until": "networkidle"}
        )

    assert len(result) >= 1
