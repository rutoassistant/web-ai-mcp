"""
Tests for DuckDuckGo AI Chat specific behavior.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from server import call_tool
from tests.selectors import INPUT_SELECTORS, MESSAGE_SELECTORS


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
    page.fill = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.reload = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"fakeimage")
    page.content = AsyncMock(
        return_value="<html><body><p>The answer is 42</p></body></html>"
    )

    def locator_side_effect(selector):
        if selector == "iframe#jsa":
            m = MagicMock()
            m.count = AsyncMock(return_value=0)
            m.is_visible = AsyncMock(return_value=False)
            return m
        return make_mock_locator(enable=True, count=1, texts=["The answer is 42"])

    page.locator = MagicMock(side_effect=locator_side_effect)
    role_mock = MagicMock()
    role_mock.count = AsyncMock(return_value=1)  # Return 1 so element is found
    role_mock.first = make_mock_locator(
        enable=True, count=1, texts=["The answer is 42"]
    )  # .first returns a locator
    role_mock.is_visible = AsyncMock(return_value=True)
    role_mock.is_enabled = AsyncMock(return_value=True)
    role_mock.click = AsyncMock()
    page.get_by_role = MagicMock(return_value=role_mock)
    page.get_by_label = MagicMock(return_value=role_mock)
    page.get_by_placeholder = MagicMock(return_value=role_mock)
    page.content_frame = AsyncMock(return_value=page)
    return page


@pytest.mark.asyncio
async def test_chat_send_uses_input_selector(mock_page):
    with (
        patch("server.ensure_browser", new_callable=AsyncMock, return_value=mock_page),
        patch("server.dismiss_overlays", new_callable=AsyncMock, return_value=False),
    ):
        result = await call_tool("chat_send", {"message": "Test"})
    assert len(result) >= 1
    assert result[0].type == "text"
    assert "42" in result[0].text


def test_selectors_exist():
    assert len(INPUT_SELECTORS) > 0
    assert len(MESSAGE_SELECTORS) > 0
