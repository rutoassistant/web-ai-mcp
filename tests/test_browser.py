"""
Tests for ensure_browser and browser lifecycle.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import server

def make_mock_locator(enable=True, count=1):
    m = MagicMock()
    m.count = AsyncMock(return_value=count)
    m.is_visible = AsyncMock(return_value=True)
    m.is_enabled = AsyncMock(return_value=enable)
    m.fill = AsyncMock()
    m.check = AsyncMock()
    return m

def make_mock_page():
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.get_by_role = MagicMock()
    role_mock = MagicMock()
    role_mock.count = AsyncMock(return_value=0)
    role_mock.is_visible = AsyncMock(return_value=False)
    role_mock.click = AsyncMock()
    page.get_by_role.return_value = role_mock
    # locator: differentiate iframe
    def locator_side_effect(selector):
        if selector == 'iframe#jsa':
            m = MagicMock()
            m.count = AsyncMock(return_value=0)
            m.is_visible = AsyncMock(return_value=False)
            return m
        return make_mock_locator(enable=True, count=0 if 'checkbox' in selector else 1)
    page.locator = MagicMock(side_effect=locator_side_effect)
    page.fill = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.reload = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"img")
    page.all_text_contents = AsyncMock(return_value=["hi"])
    page.content = AsyncMock(return_value="<html>Mock</html>")
    page.content_frame = AsyncMock(return_value=page)
    return page

@pytest.fixture(autouse=True)
def reset_globals():
    server.playwright_instance = None
    server.browser_instance = None
    server.page_instance = None
    yield
    server.playwright_instance = None
    server.browser_instance = None
    server.page_instance = None

@pytest.mark.asyncio
async def test_ensure_browser_creates_browser():
    mock_playwright = MagicMock()
    mock_playwright.start = AsyncMock(return_value=mock_playwright)
    mock_chromium = MagicMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = make_mock_page()

    mock_playwright.chromium = mock_chromium
    mock_chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)

    with patch('server.async_playwright', return_value=mock_playwright), \
         patch('server.dismiss_overlays', new_callable=AsyncMock, return_value=False):
        page = await server.ensure_browser()

    assert page is mock_page
    mock_playwright.start.assert_awaited_once()
    mock_chromium.launch.assert_awaited_once()
    mock_browser.new_context.assert_awaited_once()
    mock_context.new_page.assert_awaited_once()
    mock_page.goto.assert_awaited_once()

@pytest.mark.asyncio
async def test_ensure_browser_reuses_on_second_call():
    mock_playwright = MagicMock()
    mock_playwright.start = AsyncMock(return_value=mock_playwright)
    mock_chromium = MagicMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = make_mock_page()

    mock_playwright.chromium = mock_chromium
    mock_chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)

    with patch('server.async_playwright', return_value=mock_playwright), \
         patch('server.dismiss_overlays', new_callable=AsyncMock, return_value=False):
        page1 = await server.ensure_browser()
        mock_playwright.start.reset_mock()
        mock_chromium.launch.reset_mock()
        page2 = await server.ensure_browser()

    assert page1 is page2
    mock_playwright.start.assert_not_called()
    mock_chromium.launch.assert_not_called()
