"""
Browser lifecycle management using Patchright.
Phase 2: Stealth browser with Xvfb and anti-detection.
Phase 8: Isolated contexts per request for concurrency safety.
"""

import os
import asyncio
import logging
import uuid
from typing import Optional
from contextlib import asynccontextmanager

from patchright.async_api import async_playwright, Browser, BrowserContext, Page

from src.browser.stealth import StealthConfig, XvfbManager, detect_display, setup_xvfb_env
from src.browser.subagent_manager import SubAgentBrowserManager, get_subagent_manager

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages browser lifecycle with stealth capabilities and isolated contexts.

    Architecture:
    - Single browser process (kept alive for speed)
    - Isolated incognito context per request (for data isolation)
    - Async lock prevents race conditions
    - Each request gets its own page in its own context
    """

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        # Legacy single context/page (deprecated, kept for compatibility)
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        # Request isolation
        self._lock = asyncio.Lock()
        self._active_contexts: dict[str, BrowserContext] = {}

        # Stealth configuration
        self.stealth_config = StealthConfig()
        self.xvfb_manager: Optional[XvfbManager] = None

        # Setup display environment
        self.display = setup_xvfb_env()

        # Sub-agent browser manager
        self.subagent_manager: Optional[SubAgentBrowserManager] = None

    async def start(self):
        """Start browser instance with stealth configuration."""
        logger.info("Starting browser with stealth configuration...")
        logger.info(f"Stealth mode: {self.stealth_config.stealth_mode}")
        logger.info(f"Display: {self.display}")

        # Start Xvfb if needed for stealth mode
        if self.stealth_config.use_xvfb:
            await self._start_xvfb()

        self.playwright = await async_playwright().start()

        # Always launch browser process (not persistent context)
        # Contexts will be created per-request for isolation
        await self._launch_browser_process()

        logger.info("Browser started successfully")

        # Initialize sub-agent browser manager with timeout from environment
        import os

        idle_timeout_minutes = int(os.environ.get("BROWSER_TIMEOUT_MINUTES", "30"))
        self.subagent_manager = await get_subagent_manager(
            idle_timeout_minutes=idle_timeout_minutes
        )

    async def _launch_browser_process(self):
        """Launch browser process only (contexts created per-request)."""
        logger.info("Launching browser process...")

        launch_args = self.stealth_config.get_launch_args()

        try:
            # Launch browser with Chrome channel for stealth
            self.browser = await self.playwright.chromium.launch(
                channel=self.stealth_config.channel,
                headless=self.stealth_config.headless,
                args=launch_args,
            )
            logger.info(f"Browser process started: {self.stealth_config.channel}")

            # Create a default context/page for backward compatibility
            context_options = self.stealth_config.get_context_options()
            self.context = await self.browser.new_context(**context_options)
            self.page = await self.context.new_page()
            logger.info("Default context created for backward compatibility")

        except Exception as e:
            logger.warning(f"Failed to launch with Chrome channel: {e}")
            logger.info("Falling back to standard Chromium...")

            self.browser = await self.playwright.chromium.launch(
                headless=self.stealth_config.headless,
                args=launch_args,
            )
            context_options = self.stealth_config.get_context_options()
            self.context = await self.browser.new_context(**context_options)
            self.page = await self.context.new_page()

    async def _start_xvfb(self):
        """Start Xvfb virtual display if needed."""
        self.xvfb_manager = XvfbManager(display=self.display)
        success = await self.xvfb_manager.start()

        if not success:
            logger.warning(
                "Failed to start Xvfb. Falling back to headless mode. "
                "Some stealth features may not work."
            )
            # Fall back to headless if Xvfb fails
            self.stealth_config.headless = True

    async def _launch_stealth_browser(self):
        """Launch browser with maximum stealth configuration (deprecated - use _launch_browser_process)."""
        logger.info("Launching browser in stealth mode...")

        launch_args = self.stealth_config.get_launch_args()
        context_options = self.stealth_config.get_context_options()

        try:
            # Attempt to use persistent context with Chrome channel for maximum stealth
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=self.stealth_config.user_data_dir,
                channel=self.stealth_config.channel,  # Use real Chrome if available
                headless=self.stealth_config.headless,
                args=launch_args,
                no_viewport=True,  # Let browser use natural viewport
                **{k: v for k, v in context_options.items() if k != "viewport"},
            )

            # Get the default page from persistent context
            pages = self.context.pages
            if pages:
                self.page = pages[0]
            else:
                self.page = await self.context.new_page()

            logger.info(f"Using channel: {self.stealth_config.channel}")
            logger.info(f"Headless: {self.stealth_config.headless}")

        except Exception as e:
            logger.warning(f"Failed to launch with Chrome channel: {e}")
            logger.info("Falling back to standard Chromium...")

            # Fallback to regular Chromium
            await self._launch_basic_browser()

    async def _launch_basic_browser(self):
        """Launch basic browser without stealth optimizations."""
        logger.info("Launching basic browser...")

        self.browser = await self.playwright.chromium.launch(
            headless=self.stealth_config.headless,
            args=self.stealth_config.get_launch_args(),
        )

        context_options = self.stealth_config.get_context_options()
        self.context = await self.browser.new_context(**context_options)
        self.page = await self.context.new_page()

    @asynccontextmanager
    async def isolated_context(self):
        """Create an isolated browser context for a single request.

        This ensures:
        - No cookie/session data leakage between requests
        - No race conditions between concurrent requests (serialized access)
        - Clean state for each search

        Note: This holds a lock for the entire duration of the request to
        prevent race conditions in the shared browser process.
        """
        context_id = str(uuid.uuid4())[:8]
        logger.info(f"Creating isolated context {context_id}")

        async with self._lock:
            if not self.browser:
                raise RuntimeError("Browser not initialized")

            context_options = self.stealth_config.get_context_options()
            context = await self.browser.new_context(**context_options)
            page = await context.new_page()
            self._active_contexts[context_id] = context

            logger.info(f"Isolated context {context_id} created and locked")

            try:
                yield page
            finally:
                # Cleanup: close context to free resources
                logger.info(f"Closing isolated context {context_id} and releasing lock")
                try:
                    await context.close()
                except Exception as e:
                    logger.debug(f"Error closing context {context_id}: {e}")
                finally:
                    self._active_contexts.pop(context_id, None)

    async def create_isolated_page(self) -> tuple[str, Page]:
        """Create an isolated page in a new context. Returns (context_id, page).

        Caller is responsible for calling close_isolated_page(context_id) when done.
        """
        context_id = str(uuid.uuid4())[:8]

        async with self._lock:
            if not self.browser:
                raise RuntimeError("Browser not initialized")

            context_options = self.stealth_config.get_context_options()
            context = await self.browser.new_context(**context_options)
            page = await context.new_page()
            self._active_contexts[context_id] = context

        logger.info(f"Created isolated page {context_id}")
        return context_id, page

    async def close_isolated_page(self, context_id: str):
        """Close an isolated page and its context."""
        context = self._active_contexts.pop(context_id, None)
        if context:
            logger.info(f"Closing isolated page {context_id}")
            try:
                await context.close()
            except Exception as e:
                logger.debug(f"Error closing context {context_id}: {e}")

    async def stop(self):
        """Stop browser and cleanup resources."""
        logger.info("Stopping browser...")

        # Stop sub-agent browser manager
        if self.subagent_manager:
            await self.subagent_manager.stop()
            self.subagent_manager = None

        if self.page:
            try:
                await self.page.close()
            except Exception as e:
                logger.debug(f"Error closing page: {e}")
            self.page = None

        if self.context:
            try:
                await self.context.close()
            except Exception as e:
                logger.debug(f"Error closing context: {e}")
            self.context = None

        if self.browser:
            try:
                await self.browser.close()
            except Exception as e:
                logger.debug(f"Error closing browser: {e}")
            self.browser = None

        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception as e:
                logger.debug(f"Error stopping playwright: {e}")
            self.playwright = None

        # Stop Xvfb if we started it
        if self.xvfb_manager:
            await self.xvfb_manager.stop()
            self.xvfb_manager = None

        logger.info("Browser stopped")

    async def new_page(self) -> Page:
        """Create a new page in the context."""
        if not self.context:
            raise RuntimeError("Browser not initialized")
        return await self.context.new_page()

    async def check_stealth(self) -> dict:
        """Check stealth status and browser fingerprint.

        Returns:
            Dictionary with stealth detection information.
        """
        if not self.page:
            return {"error": "Browser not initialized"}

        # JavaScript to check for automation indicators
        stealth_check_script = """
        () => {
            return {
                webdriver: navigator.webdriver,
                plugins: navigator.plugins.length,
                languages: navigator.languages,
                platform: navigator.platform,
                userAgent: navigator.userAgent,
                vendor: navigator.vendor,
                deviceMemory: navigator.deviceMemory,
                hardwareConcurrency: navigator.hardwareConcurrency,
                maxTouchPoints: navigator.maxTouchPoints,
                chrome: typeof window.chrome !== 'undefined',
                notificationPermission: Notification.permission,
                // Check for common automation indicators
                automationControlled: navigator.webdriver === true,
                hasPlugins: navigator.plugins.length > 0,
                hasMimeTypes: navigator.mimeTypes.length > 0,
            };
        }
        """

        try:
            result = await self.page.evaluate(stealth_check_script)
            result["stealth_mode"] = self.stealth_config.stealth_mode
            result["display"] = self.display
            result["channel"] = self.stealth_config.channel
            return result
        except Exception as e:
            return {"error": str(e)}

    async def get_subagent_browser(self, session_id: str):
        """Get or create a browser instance for a sub-agent.

        Args:
            session_id: The sub-agent session ID

        Returns:
            BrowserInstance for the sub-agent
        """
        if not self.subagent_manager:
            raise RuntimeError("SubAgentBrowserManager not initialized")
        return await self.subagent_manager.get_or_create_browser(session_id)

    async def close_subagent_browser(self, session_id: str) -> bool:
        """Close a sub-agent's browser instance.

        Args:
            session_id: The sub-agent session ID

        Returns:
            True if closed, False if not found
        """
        if not self.subagent_manager:
            return False
        return await self.subagent_manager.close_browser(session_id)

    async def list_subagent_sessions(self) -> list:
        """List all active sub-agent browser sessions.

        Returns:
            List of session information dictionaries
        """
        if not self.subagent_manager:
            return []
        return await self.subagent_manager.list_sessions()

    async def get_subagent_stats(self) -> dict:
        """Get statistics about sub-agent browser manager.

        Returns:
            Dictionary with manager statistics
        """
        if not self.subagent_manager:
            return {"error": "SubAgentBrowserManager not initialized"}
        return self.subagent_manager.get_stats()
