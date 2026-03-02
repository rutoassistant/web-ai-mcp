"""
Stealth layer for anti-detection browser automation.
Provides Xvfb support and anti-detection configurations.
"""

import os
import asyncio
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class StealthConfig:
    """Configuration for stealth browser automation."""

    def __init__(self):
        self.display = os.getenv("DISPLAY", ":99")
        self.stealth_mode = os.getenv("STEALTH_MODE", "true").lower() == "true"
        self.user_data_dir = os.getenv("USER_DATA_DIR", "/tmp/browser_data")
        self.headless = os.getenv("HEADLESS", "false").lower() == "true"
        self.channel = os.getenv("BROWSER_CHANNEL", "chrome")

    @property
    def use_xvfb(self) -> bool:
        """Check if Xvfb virtual display should be used."""
        # Use Xvfb if DISPLAY is set (indicating virtual display available)
        # or if we're in stealth mode and not explicitly headless
        return self.stealth_mode and not self.headless

    @property
    def display_value(self) -> str:
        """Get the display value for Xvfb."""
        return self.display

    def get_launch_args(self) -> List[str]:
        """Get browser launch arguments for stealth."""
        if not self.stealth_mode:
            return ["--no-sandbox", "--disable-setuid-sandbox"]

        args = [
            # Security
            "--no-sandbox",
            "--disable-setuid-sandbox",
            # Anti-detection
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            # Disable automation indicators
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--disable-gpu",
            "--window-size=1920,1080",
            "--start-maximized",
            # Disable automation flags
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            # Additional privacy
            "--disable-notifications",
            "--disable-popup-blocking",
            "--disable-default-apps",
            "--disable-extensions",
        ]

        # Add display argument if using Xvfb
        if self.use_xvfb and self.display:
            args.append(f"--display={self.display}")

        return args

    def get_context_options(self) -> Dict[str, Any]:
        """Get browser context options for stealth."""
        options: Dict[str, Any] = {
            "viewport": {"width": 1920, "height": 1080},
            "screen": {"width": 1920, "height": 1080},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "locale": "en-US",
            "timezone_id": "America/New_York",
            "geolocation": {"latitude": 40.7128, "longitude": -74.0060},  # NYC
            "permissions": [],
            "color_scheme": "light",
            "reduced_motion": "no-preference",
            "forced_colors": "none",
        }

        if self.stealth_mode:
            # Add extra HTTP headers for realism
            options["extra_http_headers"] = {
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,image/apng,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            }

        return options


class XvfbManager:
    """Manages Xvfb virtual display for headful browser automation."""

    def __init__(self, display: str = ":99", screen: str = "1920x1080x24"):
        self.display = display
        self.screen = screen
        self.process: Optional[Any] = None
        self._is_running = False

    async def start(self) -> bool:
        """Start Xvfb virtual display."""
        # Check if Xvfb is already running on this display
        if await self._is_xvfb_running():
            logger.info(f"Xvfb already running on display {self.display}")
            self._is_running = True
            return True

        try:
            cmd = [
                "Xvfb",
                self.display,
                "-screen",
                "0",
                self.screen,
                "-ac",
                "+extension",
                "RANDR",
                "+extension",
                "RENDER",
                "+extension",
                "GLX",
                "-noreset",
            ]

            logger.info(f"Starting Xvfb on display {self.display}")
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )

            # Wait for Xvfb to be ready
            await asyncio.sleep(1)

            if await self._is_xvfb_running():
                logger.info(f"Xvfb started successfully on {self.display}")
                self._is_running = True
                return True
            else:
                logger.error("Xvfb failed to start")
                return False

        except FileNotFoundError:
            logger.warning("Xvfb not found. Install with: apt-get install xvfb")
            return False
        except Exception as e:
            logger.error(f"Error starting Xvfb: {e}")
            return False

    async def stop(self):
        """Stop Xvfb virtual display."""
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except Exception:
                self.process.kill()
            finally:
                self.process = None
                self._is_running = False
                logger.info("Xvfb stopped")

    async def _is_xvfb_running(self) -> bool:
        """Check if Xvfb is running on the configured display."""
        try:
            # Check if display is accessible
            env = os.environ.copy()
            env["DISPLAY"] = self.display

            proc = await asyncio.create_subprocess_exec(
                "xdpyinfo",
                env=env,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=2.0)
            return proc.returncode == 0
        except Exception:
            return False

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.process:
            asyncio.create_task(self.stop())


def detect_display() -> Optional[str]:
    """Detect available display for browser automation.

    Returns:
        Display string (e.g., ":99") or None if no display available.
    """
    # Check for existing DISPLAY environment variable
    display = os.getenv("DISPLAY")
    if display:
        logger.info(f"Using existing DISPLAY: {display}")
        return display

    # Check if Xvfb is running
    for disp_num in range(99, 110):
        display = f":{disp_num}"
        env = os.environ.copy()
        env["DISPLAY"] = display

        try:
            import subprocess

            result = subprocess.run(
                ["xdpyinfo"],
                env=env,
                capture_output=True,
                timeout=1,
            )
            if result.returncode == 0:
                logger.info(f"Found running Xvfb on {display}")
                return display
        except Exception:
            continue

    logger.warning("No display detected. Will attempt to use :99 for Xvfb.")
    return ":99"


def setup_xvfb_env() -> str:
    """Setup Xvfb environment variables.

    Returns:
        The display value that was set.
    """
    display = os.getenv("DISPLAY")
    if not display:
        display = ":99"
        os.environ["DISPLAY"] = display
        logger.info(f"Set DISPLAY={display}")
    return display
