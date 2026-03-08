"""
Tests for StealthConfig and XvfbManager in src/browser/stealth.py
"""

import asyncio
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from src.browser import StealthConfig, XvfbManager, detect_display, setup_xvfb_env


class TestStealthConfig:
    """Test cases for StealthConfig class."""

    def test_init_defaults(self):
        """Test default initialization of StealthConfig."""
        with patch.dict(os.environ, {}, clear=False):
            config = StealthConfig()

            assert config.display == ":99"
            assert config.stealth_mode is True
            assert config.headless is False

    def test_init_from_env(self):
        """Test initialization from environment variables."""
        env_vars = {
            "DISPLAY": ":0",
            "STEALTH_MODE": "false",
            "HEADLESS": "true",
            "USER_DATA_DIR": "/custom/path",
            "BROWSER_CHANNEL": "chromium",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = StealthConfig()

            assert config.display == ":0"
            assert config.stealth_mode is False
            assert config.headless is True
            assert config.user_data_dir == "/custom/path"
            assert config.channel == "chromium"

    def test_use_xvfb_property(self):
        """Test use_xvfb property logic."""
        with patch.dict(os.environ, {"STEALTH_MODE": "true", "HEADLESS": "false"}):
            config = StealthConfig()
            assert config.use_xvfb is True

        with patch.dict(os.environ, {"STEALTH_MODE": "false", "HEADLESS": "false"}):
            config = StealthConfig()
            assert config.use_xvfb is False

        with patch.dict(os.environ, {"STEALTH_MODE": "true", "HEADLESS": "true"}):
            config = StealthConfig()
            assert config.use_xvfb is False

    def test_display_value_property(self):
        """Test display_value property."""
        with patch.dict(os.environ, {"DISPLAY": ":42"}):
            config = StealthConfig()
            assert config.display_value == ":42"

    def test_get_launch_args_no_stealth(self):
        """Test get_launch_args when stealth is disabled."""
        with patch.dict(os.environ, {"STEALTH_MODE": "false"}):
            config = StealthConfig()
            args = config.get_launch_args()

            assert "--no-sandbox" in args
            assert "--disable-setuid-sandbox" in args
            assert len(args) == 2

    def test_get_launch_args_with_stealth(self):
        """Test get_launch_args with stealth enabled."""
        with patch.dict(
            os.environ, {"STEALTH_MODE": "true", "HEADLESS": "false", "DISPLAY": ":99"}
        ):
            config = StealthConfig()
            args = config.get_launch_args()

            assert "--no-sandbox" in args
            assert "--disable-setuid-sandbox" in args
            assert "--disable-blink-features=AutomationControlled" in args
            assert "--display=:99" in args

            assert len(args) > 10

    def test_get_launch_args_headless_no_xvfb(self):
        """Test get_launch_args in headless mode without Xvfb."""
        with patch.dict(
            os.environ, {"STEALTH_MODE": "true", "HEADLESS": "true", "DISPLAY": ":99"}
        ):
            config = StealthConfig()
            args = config.get_launch_args()

            assert "--display=:99" not in args

    def test_get_context_options(self):
        """Test get_context_options returns correct structure."""
        with patch.dict(os.environ, {"STEALTH_MODE": "true"}):
            config = StealthConfig()
            options = config.get_context_options()

            assert "viewport" in options
            assert options["viewport"]["width"] == 1920
            assert options["viewport"]["height"] == 1080

            assert "user_agent" in options
            assert "locale" in options
            assert options["locale"] == "en-US"

            assert "timezone_id" in options
            assert "permissions" in options

    def test_get_context_options_with_stealth_headers(self):
        """Test context options include extra HTTP headers in stealth mode."""
        with patch.dict(os.environ, {"STEALTH_MODE": "true"}):
            config = StealthConfig()
            options = config.get_context_options()

            assert "extra_http_headers" in options
            assert "Accept" in options["extra_http_headers"]
            assert "Accept-Language" in options["extra_http_headers"]

    def test_get_context_options_no_stealth_headers(self):
        """Test context options exclude extra headers when not in stealth mode."""
        with patch.dict(os.environ, {"STEALTH_MODE": "false"}):
            config = StealthConfig()
            options = config.get_context_options()

            assert "extra_http_headers" not in options


class TestXvfbManager:
    """Test cases for XvfbManager class."""

    def test_init(self):
        """Test initialization of XvfbManager."""
        manager = XvfbManager()

        assert manager.display == ":99"
        assert manager.screen == "1920x1080x24"
        assert manager.process is None
        assert manager._is_running is False

    def test_init_custom_display(self):
        """Test initialization with custom display."""
        manager = XvfbManager(display=":42", screen="1280x720x24")

        assert manager.display == ":42"
        assert manager.screen == "1280x720x24"

    @pytest.mark.asyncio
    async def test_start_already_running(self):
        """Test start when Xvfb already running."""
        manager = XvfbManager()

        with patch.object(
            manager, "_is_xvfb_running", new_callable=AsyncMock, return_value=True
        ):
            result = await manager.start()

            assert result is True
            assert manager._is_running is True

    @pytest.mark.asyncio
    async def test_start_success(self):
        """Test successful Xvfb start."""
        manager = XvfbManager()

        async def mock_is_running():
            manager.process = MagicMock()
            return True

        with patch.object(
            manager,
            "_is_xvfb_running",
            new_callable=AsyncMock,
            side_effect=[False, True],
        ):
            with patch(
                "asyncio.create_subprocess_exec", new_callable=AsyncMock
            ) as mock_exec:
                mock_proc = MagicMock()
                mock_proc.wait = AsyncMock(return_value=0)
                mock_exec.return_value = mock_proc

                result = await manager.start()

                assert result is True
                assert manager._is_running is True

    @pytest.mark.asyncio
    async def test_start_xvfb_not_found(self):
        """Test start when Xvfb is not installed."""
        manager = XvfbManager()

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()):
            result = await manager.start()

            assert result is False

    @pytest.mark.asyncio
    async def test_start_failure(self):
        """Test start failure."""
        manager = XvfbManager()

        with patch.object(
            manager, "_is_xvfb_running", new_callable=AsyncMock, return_value=False
        ):
            with patch(
                "asyncio.create_subprocess_exec", new_callable=AsyncMock
            ) as mock_exec:
                mock_proc = MagicMock()
                mock_proc.wait = AsyncMock(return_value=1)
                mock_exec.return_value = mock_proc

                result = await manager.start()

                assert result is False

    @pytest.mark.asyncio
    async def test_stop(self):
        """Test Xvfb stop."""
        manager = XvfbManager()

        mock_process = MagicMock()
        mock_process.terminate = MagicMock()
        mock_process.wait = AsyncMock(return_value=0)
        manager.process = mock_process
        manager._is_running = True

        await manager.stop()

        mock_process.terminate.assert_called_once()
        assert manager.process is None
        assert manager._is_running is False

    @pytest.mark.asyncio
    async def test_stop_kill_on_timeout(self):
        """Test Xvfb stop kills process on timeout."""
        manager = XvfbManager()

        mock_process = MagicMock()
        mock_process.terminate = MagicMock()
        mock_process.wait = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_process.kill = MagicMock()
        manager.process = mock_process
        manager._is_running = True

        await manager.stop()

        mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_xvfb_running_true(self):
        """Test _is_xvfb_running returns True when running."""
        manager = XvfbManager()

        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_exec:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.wait = AsyncMock(return_value=0)
            mock_exec.return_value = mock_proc

            result = await manager._is_xvfb_running()

            assert result is True

    @pytest.mark.asyncio
    async def test_is_xvfb_running_false(self):
        """Test _is_xvfb_running returns False when not running."""
        manager = XvfbManager()

        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_exec:
            mock_proc = MagicMock()
            mock_proc.returncode = 1
            mock_proc.wait = AsyncMock(return_value=1)
            mock_exec.return_value = mock_proc

            result = await manager._is_xvfb_running()

            assert result is False

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test XvfbManager as context manager."""
        with (
            patch(
                "src.browser.stealth.XvfbManager.start", new_callable=AsyncMock
            ) as mock_start,
            patch(
                "src.browser.stealth.XvfbManager.stop", new_callable=AsyncMock
            ) as mock_stop,
        ):
            mock_start.return_value = True

            manager = XvfbManager()

            async with manager as m:
                assert m is manager

            mock_stop.assert_called_once()


class TestDetectDisplay:
    """Test cases for detect_display function."""

    @patch.dict(os.environ, {"DISPLAY": ":0"})
    def test_detect_display_from_env(self):
        """Test detect_display returns DISPLAY from environment."""
        result = detect_display()

        assert result == ":0"

    @patch.dict(os.environ, {}, clear=True)
    def test_detect_display_no_display(self):
        """Test detect_display returns default when no display."""
        with patch("subprocess.run", side_effect=Exception("No display")):
            result = detect_display()

            assert result == ":99"


class TestSetupXvfbEnv:
    """Test cases for setup_xvfb_env function."""

    @patch.dict(os.environ, {"DISPLAY": ":42"}, clear=False)
    def test_setup_xvfb_env_existing(self):
        """Test setup_xvfb_env returns existing DISPLAY."""
        result = setup_xvfb_env()

        assert result == ":42"

    @patch.dict(os.environ, {}, clear=True)
    def test_setup_xvfb_env_sets_default(self):
        """Test setup_xvfb_env sets default DISPLAY."""
        result = setup_xvfb_env()

        assert result == ":99"
        assert os.environ.get("DISPLAY") == ":99"
