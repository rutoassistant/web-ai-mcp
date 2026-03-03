"""
Tests for SubAgentBrowserManager in src/browser/subagent_manager.py
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


class TestSubAgentBrowserManager:
    """Test cases for SubAgentBrowserManager class."""

    @pytest.fixture
    def mock_browser_instance(self):
        """Create mock BrowserInstance."""
        instance = MagicMock()
        instance.close = AsyncMock()
        instance.update_activity = MagicMock()
        instance._closed = False
        return instance

    def test_init(self):
        """Test SubAgentBrowserManager initialization."""
        with patch("src.browser.subagent_manager.StealthConfig"):
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                from src.browser.subagent_manager import SubAgentBrowserManager

                manager = SubAgentBrowserManager(idle_timeout_minutes=15)

                assert manager._browsers == {}
                assert manager._playwright is None
                assert manager.IDLE_TIMEOUT_SECONDS == 15 * 60

    @pytest.mark.asyncio
    async def test_start(self):
        """Test start initializes Playwright."""
        with patch("src.browser.subagent_manager.StealthConfig"):
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                with patch("src.browser.subagent_manager.async_playwright") as mock_ap:
                    mock_playwright = MagicMock()
                    mock_playwright.start = AsyncMock()
                    mock_ap.return_value = mock_playwright

                    from src.browser.subagent_manager import SubAgentBrowserManager

                    manager = SubAgentBrowserManager()
                    await manager.start()

                    mock_playwright.start.assert_called_once()
                    assert manager._running is True

    @pytest.mark.asyncio
    async def test_start_already_running(self):
        """Test start does nothing when already running."""
        with patch("src.browser.subagent_manager.StealthConfig"):
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                with patch("src.browser.subagent_manager.async_playwright"):
                    from src.browser.subagent_manager import SubAgentBrowserManager

                    manager = SubAgentBrowserManager()
                    manager._running = True

                    await manager.start()

                    assert manager._running is True

    @pytest.mark.asyncio
    async def test_stop(self):
        """Test stop cleans up all resources."""
        with patch("src.browser.subagent_manager.StealthConfig"):
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                from src.browser.subagent_manager import SubAgentBrowserManager

                manager = SubAgentBrowserManager()

                manager._running = True
                manager._playwright = MagicMock()
                manager._playwright.stop = AsyncMock()

                manager._cleanup_task = asyncio.create_task(asyncio.sleep(10))

                mock_instance = MagicMock()
                mock_instance.close = AsyncMock()
                manager._browsers = {"session1": mock_instance}
                manager._browser_refs = {"session1": MagicMock()}

                await manager.stop()

                assert manager._running is False

    @pytest.mark.asyncio
    async def test_create_browser(self):
        """Test create_browser creates new browser instance."""
        with patch("src.browser.subagent_manager.StealthConfig") as mock_config_class:
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                mock_config = MagicMock()
                mock_config.get_launch_args.return_value = []
                mock_config.get_context_options.return_value = {}
                mock_config.channel = "chrome"
                mock_config.headless = False
                mock_config_class.return_value = mock_config

                with patch("src.browser.subagent_manager.async_playwright") as mock_ap:
                    mock_playwright = MagicMock()
                    mock_chromium = MagicMock()
                    mock_browser = MagicMock()
                    mock_context = MagicMock()
                    mock_page = MagicMock()

                    mock_chromium.launch = AsyncMock(return_value=mock_browser)
                    mock_browser.new_context = AsyncMock(return_value=mock_context)
                    mock_playwright.chromium = mock_chromium
                    mock_playwright.start = AsyncMock()
                    mock_ap.return_value = mock_playwright

                    from src.browser.subagent_manager import SubAgentBrowserManager

                    manager = SubAgentBrowserManager()
                    manager._running = True
                    manager._playwright = mock_playwright
                    manager.stealth_config = mock_config

                    instance = await manager.create_browser("test-session")

                    assert instance is not None
                    assert "test-session" in manager._browsers

    @pytest.mark.asyncio
    async def test_create_browser_already_exists(self):
        """Test create_browser reuses existing browser."""
        with patch("src.browser.subagent_manager.StealthConfig"):
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                from src.browser.subagent_manager import SubAgentBrowserManager

                manager = SubAgentBrowserManager()

                mock_instance = MagicMock()
                mock_instance.update_activity = MagicMock()
                manager._browsers = {"existing-session": mock_instance}
                manager._running = True

                instance = await manager.create_browser("existing-session")

                assert instance is mock_instance
                mock_instance.update_activity.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_browser_not_started(self):
        """Test create_browser raises when manager not started."""
        with patch("src.browser.subagent_manager.StealthConfig"):
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                from src.browser.subagent_manager import SubAgentBrowserManager

                manager = SubAgentBrowserManager()
                manager._running = False

                with pytest.raises(RuntimeError, match="not started"):
                    await manager.create_browser("session-1")

    @pytest.mark.asyncio
    async def test_get_browser(self):
        """Test get_browser retrieves existing browser."""
        with patch("src.browser.subagent_manager.StealthConfig"):
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                from src.browser.subagent_manager import SubAgentBrowserManager

                manager = SubAgentBrowserManager()

                mock_instance = MagicMock()
                mock_instance._closed = False
                mock_instance.update_activity = MagicMock()
                manager._browsers = {"session1": mock_instance}

                result = await manager.get_browser("session1")

                assert result is mock_instance

    @pytest.mark.asyncio
    async def test_get_browser_closed_instance(self):
        """Test get_browser returns None for closed browser."""
        with patch("src.browser.subagent_manager.StealthConfig"):
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                from src.browser.subagent_manager import SubAgentBrowserManager

                manager = SubAgentBrowserManager()

                mock_instance = MagicMock()
                mock_instance._closed = True
                manager._browsers = {"session1": mock_instance}

                result = await manager.get_browser("session1")

                assert result is None

    @pytest.mark.asyncio
    async def test_get_browser_not_found(self):
        """Test get_browser returns None when not found."""
        with patch("src.browser.subagent_manager.StealthConfig"):
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                from src.browser.subagent_manager import SubAgentBrowserManager

                manager = SubAgentBrowserManager()

                result = await manager.get_browser("nonexistent")

                assert result is None

    @pytest.mark.asyncio
    async def test_close_browser(self):
        """Test close_browser closes and removes browser."""
        with patch("src.browser.subagent_manager.StealthConfig"):
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                from src.browser.subagent_manager import SubAgentBrowserManager

                manager = SubAgentBrowserManager()

                mock_instance = MagicMock()
                mock_instance.close = AsyncMock()
                manager._browsers = {"session1": mock_instance}
                manager._browser_refs = {"session1": MagicMock()}

                result = await manager.close_browser("session1")

                assert result is True
                assert "session1" not in manager._browsers

    @pytest.mark.asyncio
    async def test_close_browser_not_found(self):
        """Test close_browser returns False when not found."""
        with patch("src.browser.subagent_manager.StealthConfig"):
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                from src.browser.subagent_manager import SubAgentBrowserManager

                manager = SubAgentBrowserManager()

                result = await manager.close_browser("nonexistent")

                assert result is False

    @pytest.mark.asyncio
    async def test_list_sessions(self):
        """Test list_sessions returns active sessions."""
        with patch("src.browser.subagent_manager.StealthConfig"):
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                from src.browser.subagent_manager import SubAgentBrowserManager

                manager = SubAgentBrowserManager()

                mock_instance1 = MagicMock()
                mock_instance1._closed = False
                mock_instance1.get_stats.return_value = {"session_id": "s1"}

                mock_instance2 = MagicMock()
                mock_instance2._closed = True

                manager._browsers = {"s1": mock_instance1, "s2": mock_instance2}

                sessions = await manager.list_sessions()

                assert len(sessions) == 1
                assert sessions[0]["session_id"] == "s1"

    @pytest.mark.asyncio
    async def test_get_or_create_browser(self):
        """Test get_or_create_browser gets existing or creates new."""
        with patch("src.browser.subagent_manager.StealthConfig"):
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                from src.browser.subagent_manager import SubAgentBrowserManager

                manager = SubAgentBrowserManager()

                mock_instance = MagicMock()
                mock_instance._closed = False
                mock_instance.update_activity = MagicMock()
                manager._browsers = {"session1": mock_instance}

                result = await manager.get_or_create_browser("session1")

                assert result is mock_instance

                mock_instance._closed = True
                mock_instance2 = MagicMock()

                with patch.object(
                    manager, "create_browser", return_value=mock_instance2
                ):
                    result = await manager.get_or_create_browser("new-session")
                    assert result is mock_instance2

    @pytest.mark.asyncio
    async def test_cleanup_session_alias(self):
        """Test cleanup_session is alias for close_browser."""
        with patch("src.browser.subagent_manager.StealthConfig"):
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                from src.browser.subagent_manager import SubAgentBrowserManager

                manager = SubAgentBrowserManager()

                with patch.object(
                    manager, "close_browser", return_value=True
                ) as mock_close:
                    result = await manager.cleanup_session("session1")

                    mock_close.assert_called_once_with("session1")
                    assert result is True

    def test_get_stats(self):
        """Test get_stats returns manager statistics."""
        with patch("src.browser.subagent_manager.StealthConfig") as mock_config_class:
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                mock_config = MagicMock()
                mock_config.stealth_mode = True
                mock_config_class.return_value = mock_config

                from src.browser.subagent_manager import SubAgentBrowserManager

                manager = SubAgentBrowserManager()
                manager._browsers = {"s1": MagicMock(), "s2": MagicMock()}
                manager._running = True

                stats = manager.get_stats()

                assert stats["active_sessions"] == 2
                assert stats["running"] is True
                assert stats["stealth_mode"] is True


class TestCleanupLoop:
    """Test cases for cleanup functionality."""

    @pytest.mark.asyncio
    async def test_cleanup_inactive(self):
        """Test cleanup removes idle sessions."""
        with patch("src.browser.subagent_manager.StealthConfig"):
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                import time

                from src.browser.subagent_manager import SubAgentBrowserManager

                manager = SubAgentBrowserManager(idle_timeout_minutes=1)

                mock_instance_old = MagicMock()
                mock_instance_old.last_activity = 0
                mock_instance_old.close = AsyncMock()

                mock_instance_new = MagicMock()
                mock_instance_new.last_activity = time.time()
                mock_instance_new.close = AsyncMock()

                manager._browsers = {
                    "old-session": mock_instance_old,
                    "new-session": mock_instance_new,
                }

                mock_browser = MagicMock()
                manager._browser_refs = {"old-session": mock_browser}

                await manager._cleanup_inactive()

                assert "old-session" not in manager._browsers

    @pytest.mark.asyncio
    async def test_cleanup_inactive_loop_cancelled(self):
        """Test cleanup loop handles cancellation."""
        with patch("src.browser.subagent_manager.StealthConfig"):
            with patch(
                "src.browser.subagent_manager.setup_xvfb_env", return_value=":99"
            ):
                from src.browser.subagent_manager import SubAgentBrowserManager

                manager = SubAgentBrowserManager()
                manager._running = True

                manager.CLEANUP_INTERVAL_SECONDS = 0

                async def mock_sleep(duration):
                    manager._running = False
                    raise asyncio.CancelledError()

                with patch("asyncio.sleep", side_effect=mock_sleep):
                    await manager._cleanup_inactive_loop()


class TestGlobalFunctions:
    """Test global singleton functions."""

    def test_get_subagent_manager_creates_singleton(self):
        """Test get_subagent_manager creates singleton."""
        import src.browser.subagent_manager as subagent_module

        original_manager = subagent_module._subagent_manager

        try:
            subagent_module._subagent_manager = None

            with patch(
                "src.browser.subagent_manager.SubAgentBrowserManager"
            ) as mock_class:
                mock_instance = MagicMock()
                mock_class.return_value = mock_instance

                async def mock_start():
                    pass

                mock_instance.start = mock_start

                result = subagent_module.get_subagent_manager(idle_timeout_minutes=20)

                mock_class.assert_called_once_with(idle_timeout_minutes=20)
        finally:
            subagent_module._subagent_manager = original_manager

    def test_get_subagent_manager_returns_existing(self):
        """Test get_subagent_manager returns existing singleton."""
        import src.browser.subagent_manager as subagent_module

        original_manager = subagent_module._subagent_manager
        mock_existing = MagicMock()

        try:
            subagent_module._subagent_manager = mock_existing

            result = subagent_module.get_subagent_manager()

            assert result is mock_existing
        finally:
            subagent_module._subagent_manager = original_manager

    @pytest.mark.asyncio
    async def test_shutdown_subagent_manager(self):
        """Test shutdown_subagent_manager clears singleton."""
        import src.browser.subagent_manager as subagent_module

        original_manager = subagent_module._subagent_manager

        try:
            mock_manager = MagicMock()
            mock_manager.stop = AsyncMock()
            subagent_module._subagent_manager = mock_manager

            await subagent_module.shutdown_subagent_manager()

            mock_manager.stop.assert_called_once()
            assert subagent_module._subagent_manager is None
        finally:
            subagent_module._subagent_manager = original_manager
