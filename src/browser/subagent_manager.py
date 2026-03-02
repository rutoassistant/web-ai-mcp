"""
Sub-agent browser manager for isolated browser instances per sub-agent.

Each sub-agent gets its own browser instance with isolated tabs
to prevent data leakage and resource conflicts.
"""

import asyncio
import logging
import uuid
import time
from typing import Optional, Dict, List
from datetime import datetime

from patchright.async_api import async_playwright, Browser, BrowserContext

from src.browser.instance import BrowserInstance
from src.browser.stealth import StealthConfig, setup_xvfb_env

logger = logging.getLogger(__name__)


class SubAgentBrowserManager:
    """Manages browser instances for multiple sub-agents.

    Features:
    - One browser instance per sub-agent session
    - Automatic cleanup of inactive sessions
    - Thread-safe operations with async locks
    - Centralized resource management
    """

    # Cleanup configuration
    CLEANUP_INTERVAL_SECONDS = 60  # Check for inactive sessions every minute
    IDLE_TIMEOUT_SECONDS = 300  # Close sessions idle for 5 minutes (default)

    def __init__(self, idle_timeout_minutes: int = 30):
        # Dictionary to track all sub-agent browsers
        self._browsers: Dict[str, BrowserInstance] = {}
        self._browser_refs: Dict[str, Browser] = {}  # Browser references for cleanup
        self._playwright = None

        # Thread safety
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

        # Configuration
        self.stealth_config = StealthConfig()
        self.display = setup_xvfb_env()
        self.IDLE_TIMEOUT_SECONDS = idle_timeout_minutes * 60

        logger.info(f"SubAgentBrowserManager initialized (timeout: {idle_timeout_minutes}min)")

    async def start(self):
        """Start the manager and initialize Playwright."""
        async with self._lock:
            if self._running:
                return

            logger.info("Starting SubAgentBrowserManager...")
            self._playwright = await async_playwright().start()
            self._running = True

            # Start background cleanup task
            self._cleanup_task = asyncio.create_task(
                self._cleanup_inactive_loop(), name="browser_cleanup"
            )

            logger.info("SubAgentBrowserManager started")

    async def stop(self):
        """Stop the manager and cleanup all browser instances."""
        if not self._running:
            return

        logger.info("Stopping SubAgentBrowserManager...")
        self._running = False

        # Cancel cleanup task BEFORE acquiring lock to avoid deadlock
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        async with self._lock:
            # Close all browser instances
            for session_id, instance in list(self._browsers.items()):
                try:
                    await instance.close()
                    logger.info(f"Closed browser instance for session {session_id}")
                except Exception as e:
                    logger.warning(f"Error closing browser instance {session_id}: {e}")

            self._browsers.clear()

            # Close all browser references
            for browser in self._browser_refs.values():
                try:
                    await browser.close()
                except Exception as e:
                    logger.debug(f"Error closing browser: {e}")
            self._browser_refs.clear()

            # Stop playwright
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception as e:
                    logger.debug(f"Error stopping playwright: {e}")
                self._playwright = None

            logger.info("SubAgentBrowserManager stopped")

    async def create_browser(self, session_id: Optional[str] = None) -> BrowserInstance:
        """Create a new browser instance for a sub-agent.

        Args:
            session_id: Optional session ID (auto-generated if not provided)

        Returns:
            BrowserInstance for the sub-agent
        """
        async with self._lock:
            if not self._running:
                raise RuntimeError("SubAgentBrowserManager not started")

            # Generate session ID if not provided
            if session_id is None:
                session_id = str(uuid.uuid4())[:12]

            # Check if session already exists
            if session_id in self._browsers:
                logger.info(f"Reusing existing browser for session {session_id}")
                instance = self._browsers[session_id]
                instance.update_activity()
                return instance

            logger.info(f"Creating new browser instance for session {session_id}")

            try:
                # Launch browser process
                launch_args = self.stealth_config.get_launch_args()

                try:
                    browser = await self._playwright.chromium.launch(
                        channel=self.stealth_config.channel,
                        headless=self.stealth_config.headless,
                        args=launch_args,
                    )
                except Exception as e:
                    logger.warning(f"Failed to launch with channel {self.stealth_config.channel}: {e}")
                    logger.info("Falling back to default Chromium...")
                    browser = await self._playwright.chromium.launch(
                        headless=self.stealth_config.headless,
                        args=launch_args,
                    )

                # Store browser reference for cleanup
                self._browser_refs[session_id] = browser

                # Create isolated context
                context_options = self.stealth_config.get_context_options()
                context = await browser.new_context(**context_options)

                # Create browser instance
                instance = BrowserInstance(session_id=session_id, browser=browser, context=context)

                # Store instance
                self._browsers[session_id] = instance

                logger.info(f"Browser instance created for session {session_id}")
                return instance

            except Exception as e:
                logger.error(f"Failed to create browser for session {session_id}: {e}")
                raise

    async def get_browser(self, session_id: str) -> Optional[BrowserInstance]:
        """Get an existing browser instance by session ID.

        Args:
            session_id: The session ID

        Returns:
            BrowserInstance or None if not found
        """
        async with self._lock:
            instance = self._browsers.get(session_id)
            if instance and not instance._closed:
                instance.update_activity()
                return instance
            return None

    async def close_browser(self, session_id: str) -> bool:
        """Close a specific browser instance.

        Args:
            session_id: The session ID to close

        Returns:
            True if closed, False if not found
        """
        async with self._lock:
            instance = self._browsers.pop(session_id, None)
            if instance:
                try:
                    await instance.close()
                    logger.info(f"Closed browser instance for session {session_id}")
                except Exception as e:
                    logger.warning(f"Error closing browser instance {session_id}: {e}")

                # Also close the browser reference
                browser = self._browser_refs.pop(session_id, None)
                if browser:
                    try:
                        await browser.close()
                    except Exception as e:
                        logger.debug(f"Error closing browser: {e}")

                return True
            return False

    async def list_sessions(self) -> List[dict]:
        """Get a list of all active sessions.

        Returns:
            List of session information dictionaries
        """
        async with self._lock:
            sessions = []
            for session_id, instance in self._browsers.items():
                if not instance._closed:
                    sessions.append(instance.get_stats())
            return sessions

    async def _cleanup_inactive_loop(self):
        """Background task that periodically cleans up inactive browser instances."""
        logger.info("Starting cleanup task")

        while self._running:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL_SECONDS)

                if not self._running:
                    break

                await self._cleanup_inactive()

            except asyncio.CancelledError:
                logger.info("Cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")

    async def _cleanup_inactive(self):
        """Clean up browser instances that have been idle too long."""
        async with self._lock:
            current_time = time.time()
            to_close = []

            for session_id, instance in self._browsers.items():
                idle_time = current_time - instance.last_activity
                if idle_time > self.IDLE_TIMEOUT_SECONDS:
                    to_close.append(session_id)
                    logger.info(
                        f"Session {session_id} idle for {idle_time:.0f}s, marking for cleanup"
                    )

            # Close marked sessions
            for session_id in to_close:
                instance = self._browsers.pop(session_id, None)
                if instance:
                    try:
                        await instance.close()
                        logger.info(f"Cleaned up inactive session {session_id}")
                    except Exception as e:
                        logger.warning(f"Error cleaning up session {session_id}: {e}")

                # Also cleanup browser reference
                browser = self._browser_refs.pop(session_id, None)
                if browser:
                    try:
                        await browser.close()
                    except Exception as e:
                        logger.debug(f"Error closing browser: {e}")

            if to_close:
                logger.info(f"Cleaned up {len(to_close)} inactive browser sessions")

    async def get_or_create_browser(self, session_id: str) -> BrowserInstance:
        """Get existing browser or create new one for session.

        Args:
            session_id: The session ID

        Returns:
            BrowserInstance (existing or new)
        """
        instance = await self.get_browser(session_id)
        if instance:
            return instance
        return await self.create_browser(session_id)

    async def cleanup_session(self, session_id: str) -> bool:
        """Alias for close_browser for consistency with naming conventions.

        Args:
            session_id: The session ID to cleanup

        Returns:
            True if cleaned up, False if not found
        """
        return await self.close_browser(session_id)

    def get_stats(self) -> dict:
        """Get statistics about the manager state.

        Returns:
            Dictionary with manager statistics
        """
        return {
            "active_sessions": len(self._browsers),
            "running": self._running,
            "cleanup_interval": self.CLEANUP_INTERVAL_SECONDS,
            "idle_timeout": self.IDLE_TIMEOUT_SECONDS,
            "stealth_mode": self.stealth_config.stealth_mode,
        }


# Global singleton instance
_subagent_manager: Optional[SubAgentBrowserManager] = None


async def get_subagent_manager(idle_timeout_minutes: int = 30) -> SubAgentBrowserManager:
    """Get or create the global SubAgentBrowserManager singleton.

    Args:
        idle_timeout_minutes: Minutes before idle sessions are cleaned up (default: 30)
    """
    global _subagent_manager
    if _subagent_manager is None:
        _subagent_manager = SubAgentBrowserManager(idle_timeout_minutes=idle_timeout_minutes)
        await _subagent_manager.start()
    return _subagent_manager


async def shutdown_subagent_manager():
    """Shutdown the global SubAgentBrowserManager."""
    global _subagent_manager
    if _subagent_manager:
        await _subagent_manager.stop()
        _subagent_manager = None
