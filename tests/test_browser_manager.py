"""
Tests for BrowserManager in src/browser/manager.py
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


class TestBrowserManager:
    """Test cases for BrowserManager class."""

    @pytest.fixture
    def mock_playwright(self):
        """Create mock Playwright instance."""
        mock_pw = MagicMock()
        mock_pw.start = AsyncMock()
        mock_pw.stop = AsyncMock()
        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock()
        mock_pw.chromium = mock_chromium
        return mock_pw

    @pytest.fixture
    def mock_browser(self):
        """Create mock browser."""
        browser = MagicMock()
        browser.close = AsyncMock()
        return browser

    @pytest.fixture
    def mock_context(self):
        """Create mock context."""
        ctx = MagicMock()
        ctx.close = AsyncMock()
        ctx.new_page = AsyncMock()
        return ctx

    @pytest.fixture
    def mock_page(self):
        """Create mock page."""
        page = MagicMock()
        page.close = AsyncMock()
        return page

    def test_init(self):
        """Test BrowserManager initialization."""
        with patch("src.browser.manager.StealthConfig") as mock_config:
            with patch("src.browser.manager.setup_xvfb_env", return_value=":99"):
                with patch(
                    "src.browser.manager.get_subagent_manager"
                ) as mock_get_manager:
                    mock_get_manager.return_value = AsyncMock()

                    from src.browser.manager import BrowserManager

                    manager = BrowserManager()

                    assert manager.playwright is None
                    assert manager.browser is None
                    assert manager.context is None
                    assert manager.page is None

    @pytest.mark.asyncio
    async def test_start_initializes_components(self):
        """Test start initializes browser and subagent manager."""
        with patch("src.browser.manager.async_playwright") as mock_ap:
            mock_playwright = MagicMock()
            mock_playwright.start = AsyncMock()
            mock_chromium = MagicMock()
            mock_browser = MagicMock()
            mock_context = MagicMock()
            mock_page = MagicMock()

            mock_chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_context.new_page = AsyncMock(return_value=mock_page)
            mock_playwright.chromium = mock_chromium
            mock_ap.return_value = mock_playwright

            with patch("src.browser.manager.StealthConfig") as mock_config_class:
                mock_config = MagicMock()
                mock_config.use_xvfb = False
                mock_config.headless = False
                mock_config.channel = "chrome"
                mock_config.get_launch_args.return_value = []
                mock_config.get_context_options.return_value = {}
                mock_config_class.return_value = mock_config

                with patch("src.browser.manager.setup_xvfb_env", return_value=":99"):
                    with patch(
                        "src.browser.manager.get_subagent_manager",
                        new_callable=AsyncMock,
                    ) as mock_get_manager:
                        mock_subagent_mgr = MagicMock()
                        mock_get_manager.return_value = mock_subagent_mgr

                        from src.browser.manager import BrowserManager

                        manager = BrowserManager()
                        manager.stealth_config = mock_config
                        await manager.start()

                        mock_playwright.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop(self):
        """Test stop cleans up all resources."""
        with patch("src.browser.manager.async_playwright"):
            from src.browser.manager import BrowserManager

            manager = BrowserManager()

            manager.playwright = MagicMock()
            manager.playwright.stop = AsyncMock()
            manager.browser = MagicMock()
            manager.browser.close = AsyncMock()
            manager.context = MagicMock()
            manager.context.close = AsyncMock()
            manager.page = MagicMock()
            manager.page.close = AsyncMock()
            manager.subagent_manager = MagicMock()
            manager.subagent_manager.stop = AsyncMock()

            await manager.stop()

            manager.subagent_manager.stop.assert_called_once()
            manager.page.close.assert_called_once()
            manager.context.close.assert_called_once()
            manager.browser.close.assert_called_once()
            manager.playwright.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_new_page(self):
        """Test new_page creates a new page."""
        from src.browser.manager import BrowserManager

        manager = BrowserManager()

        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        manager.context = mock_context

        result = await manager.new_page()

        mock_context.new_page.assert_called_once()
        assert result is mock_page

    @pytest.mark.asyncio
    async def test_new_page_no_context(self):
        """Test new_page raises error when context is None."""
        from src.browser.manager import BrowserManager

        manager = BrowserManager()
        manager.context = None

        with pytest.raises(RuntimeError, match="Browser not initialized"):
            await manager.new_page()

    @pytest.mark.asyncio
    async def test_check_stealth(self):
        """Test check_stealth returns stealth information."""
        from src.browser.manager import BrowserManager

        manager = BrowserManager()

        mock_page = MagicMock()
        mock_page.evaluate = AsyncMock(return_value={"webdriver": False})
        manager.page = mock_page

        mock_config = MagicMock()
        mock_config.stealth_mode = True
        manager.stealth_config = mock_config
        manager.display = ":99"

        result = await manager.check_stealth()

        assert "webdriver" in result
        assert result["stealth_mode"] is True

    @pytest.mark.asyncio
    async def test_check_stealth_no_page(self):
        """Test check_stealth returns error when no page."""
        from src.browser.manager import BrowserManager

        manager = BrowserManager()
        manager.page = None

        result = await manager.check_stealth()

        assert "error" in result


class TestBrowserManagerIsolation:
    """Test cases for isolated context functionality."""

    @pytest.mark.asyncio
    async def test_isolated_context(self):
        """Test isolated context creation."""
        with patch("src.browser.manager.async_playwright"):
            from src.browser.manager import BrowserManager

            manager = BrowserManager()

            mock_browser = MagicMock()
            mock_browser.new_context = AsyncMock()
            mock_context = MagicMock()
            mock_page = MagicMock()

            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_context.new_page = AsyncMock(return_value=mock_page)

            manager.browser = mock_browser
            manager._lock = AsyncMock()
            manager._lock.__aenter__ = AsyncMock(return_value=MagicMock())
            manager._lock.__aexit__ = AsyncMock(return_value=None)

            mock_config = MagicMock()
            mock_config.get_context_options.return_value = {}
            manager.stealth_config = mock_config

            async with manager.isolated_context() as page:
                pass

            mock_browser.new_context.assert_called_once()
            mock_context.new_page.assert_called_once()
            mock_context.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_isolated_context_no_browser(self):
        """Test isolated context raises when browser not initialized."""
        with patch("src.browser.manager.async_playwright"):
            from src.browser.manager import BrowserManager

            manager = BrowserManager()
            manager.browser = None

            manager._lock = MagicMock()
            manager._lock.__aenter__ = AsyncMock(return_value=MagicMock())
            manager._lock.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(RuntimeError, match="Browser not initialized"):
                async with manager.isolated_context() as page:
                    pass

    @pytest.mark.asyncio
    async def test_create_isolated_page(self):
        """Test create_isolated_page creates isolated page."""
        from src.browser.manager import BrowserManager

        manager = BrowserManager()

        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_context.new_page = AsyncMock(return_value=mock_page)
        manager.browser = mock_browser

        mock_config = MagicMock()
        mock_config.get_context_options.return_value = {}
        manager.stealth_config = mock_config

        manager._lock = MagicMock()

        context_id, page = await manager.create_isolated_page()

        assert page is mock_page
        assert len(context_id) > 0

    @pytest.mark.asyncio
    async def test_close_isolated_page(self):
        """Test close_isolated_page closes context."""
        from src.browser.manager import BrowserManager

        manager = BrowserManager()

        mock_context = MagicMock()
        manager._active_contexts["test-id"] = mock_context

        await manager.close_isolated_page("test-id")

        mock_context.close.assert_called_once()
        assert "test-id" not in manager._active_contexts


class TestSubAgentMethods:
    """Test sub-agent related methods."""

    @pytest.mark.asyncio
    async def test_get_subagent_browser(self):
        """Test get_subagent_browser delegates to manager."""
        from src.browser.manager import BrowserManager

        manager = BrowserManager()

        mock_manager = MagicMock()
        mock_instance = MagicMock()
        mock_manager.get_or_create_browser = AsyncMock(return_value=mock_instance)
        manager.subagent_manager = mock_manager

        result = await manager.get_subagent_browser("session-123")

        mock_manager.get_or_create_browser.assert_called_once_with("session-123")
        assert result is mock_instance

    @pytest.mark.asyncio
    async def test_get_subagent_browser_no_manager(self):
        """Test get_subagent_browser raises when manager not initialized."""
        from src.browser.manager import BrowserManager

        manager = BrowserManager()
        manager.subagent_manager = None

        with pytest.raises(
            RuntimeError, match="SubAgentBrowserManager not initialized"
        ):
            await manager.get_subagent_browser("session-123")

    @pytest.mark.asyncio
    async def test_close_subagent_browser(self):
        """Test close_subagent_browser delegates to manager."""
        from src.browser.manager import BrowserManager

        manager = BrowserManager()

        mock_manager = MagicMock()
        mock_manager.close_browser = AsyncMock(return_value=True)
        manager.subagent_manager = mock_manager

        result = await manager.close_subagent_browser("session-123")

        mock_manager.close_browser.assert_called_once_with("session-123")
        assert result is True

    @pytest.mark.asyncio
    async def test_list_subagent_sessions(self):
        """Test list_subagent_sessions delegates to manager."""
        from src.browser.manager import BrowserManager

        manager = BrowserManager()

        mock_manager = MagicMock()
        mock_manager.list_sessions = AsyncMock(return_value=[{"session_id": "s1"}])
        manager.subagent_manager = mock_manager

        result = await manager.list_subagent_sessions()

        mock_manager.list_sessions.assert_called_once()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_subagent_sessions_no_manager(self):
        """Test list_subagent_sessions returns empty when no manager."""
        from src.browser.manager import BrowserManager

        manager = BrowserManager()
        manager.subagent_manager = None

        result = await manager.list_subagent_sessions()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_subagent_stats(self):
        """Test get_subagent_stats returns manager stats."""
        from src.browser.manager import BrowserManager

        manager = BrowserManager()

        mock_manager = MagicMock()
        mock_manager.get_stats.return_value = {"active_sessions": 2}
        manager.subagent_manager = mock_manager

        result = await manager.get_subagent_stats()

        assert result["active_sessions"] == 2

    @pytest.mark.asyncio
    async def test_get_subagent_stats_no_manager(self):
        """Test get_subagent_stats returns error when no manager."""
        from src.browser.manager import BrowserManager

        manager = BrowserManager()
        manager.subagent_manager = None

        result = await manager.get_subagent_stats()

        assert "error" in result
