"""
Tests for BrowserInstance in src/browser/instance.py
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from collections import OrderedDict


class TestTabInfo:
    """Test cases for TabInfo class."""

    def test_init(self):
        """Test TabInfo initialization."""
        from src.browser.instance import TabInfo

        page = MagicMock()
        tab = TabInfo(page=page, url="https://example.com")

        assert tab.page is page
        assert tab.url == "https://example.com"
        assert tab.created_at > 0
        assert tab.last_accessed > 0

    def test_touch(self):
        """Test TabInfo touch updates last_accessed."""
        from src.browser.instance import TabInfo

        page = MagicMock()
        tab = TabInfo(page=page)

        old_last_accessed = tab.last_accessed

        import time

        time.sleep(0.01)
        tab.touch()

        assert tab.last_accessed > old_last_accessed


class TestBrowserInstance:
    """Test cases for BrowserInstance class."""

    @pytest.fixture
    def mock_browser(self):
        """Create mock browser."""
        return MagicMock()

    @pytest.fixture
    def mock_context(self):
        """Create mock context."""
        ctx = MagicMock()
        ctx.new_page = AsyncMock()
        return ctx

    def test_init(self, mock_browser, mock_context):
        """Test BrowserInstance initialization."""
        from src.browser.instance import BrowserInstance

        instance = BrowserInstance(
            session_id="test-session", browser=mock_browser, context=mock_context
        )

        assert instance.session_id == "test-session"
        assert instance.browser is mock_browser
        assert instance.context is mock_context
        assert instance.tabs == {}
        assert instance.is_active is True
        assert instance._closed is False

    @pytest.mark.asyncio
    async def test_create_tab(self, mock_browser, mock_context):
        """Test create_tab creates new tab."""
        from src.browser.instance import BrowserInstance

        mock_page = MagicMock()
        mock_page.set_viewport_size = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        instance = BrowserInstance("session1", mock_browser, mock_context)

        tab_id, page = await instance.create_tab(url="https://example.com")

        assert page is mock_page
        assert tab_id in instance.tabs
        assert instance.tabs[tab_id].url == "https://example.com"

    @pytest.mark.asyncio
    async def test_create_tab_eviction(self, mock_browser, mock_context):
        """Test create_tab evicts oldest tab when at limit."""
        from src.browser.instance import BrowserInstance, TabInfo

        instance = BrowserInstance("session1", mock_browser, mock_context)
        instance.MAX_TABS = 2

        mock_page = MagicMock()
        mock_page.set_viewport_size = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.close = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        tab1_id, _ = await instance.create_tab(url="http://test1.com")
        tab2_id, _ = await instance.create_tab(url="http://test2.com")

        assert len(instance.tabs) == 2

        await instance.create_tab(url="http://test3.com")

        assert len(instance.tabs) == 2
        assert tab1_id not in instance.tabs
        assert tab2_id in instance.tabs

    @pytest.mark.asyncio
    async def test_create_tab_closed_instance(self, mock_browser, mock_context):
        """Test create_tab raises when instance closed."""
        from src.browser.instance import BrowserInstance

        instance = BrowserInstance("session1", mock_browser, mock_context)
        instance._closed = True

        with pytest.raises(RuntimeError, match="closed"):
            await instance.create_tab()

    @pytest.mark.asyncio
    async def test_get_tab(self, mock_browser, mock_context):
        """Test get_tab returns page and updates LRU."""
        from src.browser.instance import BrowserInstance, TabInfo

        mock_page = MagicMock()
        instance = BrowserInstance("session1", mock_browser, mock_context)

        tab_info = TabInfo(page=mock_page, url="http://test.com")
        instance.tabs["tab1"] = tab_info

        result = await instance.get_tab("tab1")

        assert result is mock_page
        assert list(instance.tabs.keys()) == ["tab1"]

    @pytest.mark.asyncio
    async def test_get_tab_not_found(self, mock_browser, mock_context):
        """Test get_tab returns None for nonexistent tab."""
        from src.browser.instance import BrowserInstance

        instance = BrowserInstance("session1", mock_browser, mock_context)

        result = await instance.get_tab("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_tab_closed_instance(self, mock_browser, mock_context):
        """Test get_tab returns None when instance closed."""
        from src.browser.instance import BrowserInstance

        instance = BrowserInstance("session1", mock_browser, mock_context)
        instance._closed = True

        result = await instance.get_tab("tab1")

        assert result is None

    @pytest.mark.asyncio
    async def test_close_tab(self, mock_browser, mock_context):
        """Test close_tab closes specific tab."""
        from src.browser.instance import BrowserInstance, TabInfo

        mock_page = MagicMock()
        mock_page.close = AsyncMock()

        instance = BrowserInstance("session1", mock_browser, mock_context)

        tab_info = TabInfo(page=mock_page)
        instance.tabs["tab1"] = tab_info

        result = await instance.close_tab("tab1")

        assert result is True
        mock_page.close.assert_called_once()
        assert "tab1" not in instance.tabs

    @pytest.mark.asyncio
    async def test_close_tab_not_found(self, mock_browser, mock_context):
        """Test close_tab returns False for nonexistent tab."""
        from src.browser.instance import BrowserInstance

        instance = BrowserInstance("session1", mock_browser, mock_context)

        result = await instance.close_tab("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_close_tab_closed_instance(self, mock_browser, mock_context):
        """Test close_tab returns False when instance closed."""
        from src.browser.instance import BrowserInstance

        instance = BrowserInstance("session1", mock_browser, mock_context)
        instance._closed = True

        result = await instance.close_tab("tab1")

        assert result is False

    @pytest.mark.asyncio
    async def test_list_tabs(self, mock_browser, mock_context):
        """Test list_tabs returns tab metadata."""
        from src.browser.instance import BrowserInstance, TabInfo

        mock_page1 = MagicMock()
        mock_page2 = MagicMock()

        instance = BrowserInstance("session1", mock_browser, mock_context)

        instance.tabs["tab1"] = TabInfo(page=mock_page1, url="http://test1.com")
        instance.tabs["tab2"] = TabInfo(page=mock_page2, url="http://test2.com")

        tabs = await instance.list_tabs()

        assert len(tabs) == 2
        assert "tab1" in tabs
        assert tabs["tab1"]["url"] == "http://test1.com"

    @pytest.mark.asyncio
    async def test_list_tabs_closed_instance(self, mock_browser, mock_context):
        """Test list_tabs returns empty when instance closed."""
        from src.browser.instance import BrowserInstance

        instance = BrowserInstance("session1", mock_browser, mock_context)
        instance._closed = True

        tabs = await instance.list_tabs()

        assert tabs == {}

    @pytest.mark.asyncio
    async def test_close_all_tabs(self, mock_browser, mock_context):
        """Test close_all_tabs closes all tabs."""
        from src.browser.instance import BrowserInstance, TabInfo

        mock_page1 = MagicMock()
        mock_page2 = MagicMock()
        mock_page1.close = AsyncMock()
        mock_page2.close = AsyncMock()

        instance = BrowserInstance("session1", mock_browser, mock_context)

        instance.tabs["tab1"] = TabInfo(page=mock_page1)
        instance.tabs["tab2"] = TabInfo(page=mock_page2)

        await instance.close_all_tabs()

        mock_page1.close.assert_called_once()
        mock_page2.close.assert_called_once()
        assert len(instance.tabs) == 0

    @pytest.mark.asyncio
    async def test_close(self, mock_browser, mock_context):
        """Test close cleans up instance."""
        from src.browser.instance import BrowserInstance, TabInfo

        mock_page = MagicMock()
        mock_page.close = AsyncMock()
        mock_context.close = AsyncMock()

        instance = BrowserInstance("session1", mock_browser, mock_context)

        tab_info = TabInfo(page=mock_page)
        instance.tabs["tab1"] = tab_info

        await instance.close()

        assert instance._closed is True
        assert instance.is_active is False
        mock_page.close.assert_called_once()
        mock_context.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_idempotent(self, mock_browser, mock_context):
        """Test close is idempotent."""
        from src.browser.instance import BrowserInstance

        instance = BrowserInstance("session1", mock_browser, mock_context)
        instance._closed = True

        await instance.close()

        assert instance._closed is True

    def test_tab_count_property(self, mock_browser, mock_context):
        """Test tab_count property returns correct count."""
        from src.browser.instance import BrowserInstance, TabInfo

        instance = BrowserInstance("session1", mock_browser, mock_context)

        instance.tabs["tab1"] = TabInfo(page=MagicMock())
        instance.tabs["tab2"] = TabInfo(page=MagicMock())

        assert instance.tab_count == 2

    def test_is_idle_not_idle(self, mock_browser, mock_context):
        """Test is_idle returns False when recently active."""
        from src.browser.instance import BrowserInstance

        instance = BrowserInstance("session1", mock_browser, mock_context)

        assert instance.is_idle(timeout_seconds=300) is False

    def test_is_idle_timeout(self, mock_browser, mock_context):
        """Test is_idle returns True when idle too long."""
        from src.browser.instance import BrowserInstance

        instance = BrowserInstance("session1", mock_browser, mock_context)
        instance.last_activity = 0

        assert instance.is_idle(timeout_seconds=300) is True

    def test_get_stats(self, mock_browser, mock_context):
        """Test get_stats returns instance statistics."""
        from src.browser.instance import BrowserInstance, TabInfo

        instance = BrowserInstance("session1", mock_browser, mock_context)

        instance.tabs["tab1"] = TabInfo(page=MagicMock())

        stats = instance.get_stats()

        assert stats["session_id"] == "session1"
        assert stats["tab_count"] == 1
        assert stats["max_tabs"] == 15
        assert stats["is_active"] is True
        assert stats["closed"] is False

    def test_update_activity(self, mock_browser, mock_context):
        """Test update_activity updates timestamp."""
        from src.browser.instance import BrowserInstance

        instance = BrowserInstance("session1", mock_browser, mock_context)
        old_time = instance.last_activity

        import time

        time.sleep(0.01)
        instance.update_activity()

        assert instance.last_activity > old_time
        assert instance.is_active is True


class TestEviction:
    """Test tab eviction logic."""

    @pytest.mark.asyncio
    async def test_evict_oldest_tab(self):
        """Test _evict_oldest_tab removes oldest tab."""
        from src.browser.instance import BrowserInstance, TabInfo

        mock_browser = MagicMock()
        mock_context = MagicMock()

        mock_page_old = MagicMock()
        mock_page_old.close = AsyncMock()

        mock_page_new = MagicMock()

        instance = BrowserInstance("session1", mock_browser, mock_context)

        tab_old = TabInfo(page=mock_page_old, url="http://old.com")
        tab_new = TabInfo(page=mock_page_new, url="http://new.com")

        instance.tabs["tab_old"] = tab_old
        instance.tabs["tab_new"] = tab_new

        await instance._evict_oldest_tab()

        mock_page_old.close.assert_called_once()
        assert "tab_old" not in instance.tabs

    @pytest.mark.asyncio
    async def test_evict_oldest_empty(self):
        """Test _evict_oldest_tab does nothing with no tabs."""
        from src.browser.instance import BrowserInstance

        mock_browser = MagicMock()
        mock_context = MagicMock()

        instance = BrowserInstance("session1", mock_browser, mock_context)

        await instance._evict_oldest_tab()
