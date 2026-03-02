"""
Browser instance management for sub-agent isolation.

Each sub-agent gets its own BrowserInstance with isolated tabs
to prevent data leakage between agents.
"""

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Optional, Dict
from dataclasses import dataclass, field

from patchright.async_api import Browser, BrowserContext, Page

logger = logging.getLogger(__name__)


@dataclass
class TabInfo:
    """Information about a browser tab."""

    page: Page
    url: str = ""
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)

    def touch(self):
        """Update last accessed time."""
        self.last_accessed = time.time()


class BrowserInstance:
    """Manages a single browser instance with tab tracking and LRU eviction.

    Features:
    - 15-tab maximum limit with LRU eviction
    - Activity tracking for session management
    - Thread-safe tab operations
    """

    MAX_TABS = 15
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self, session_id: str, browser: Browser, context: BrowserContext):
        self.session_id = session_id
        self.browser = browser
        self.context = context
        self.tabs: OrderedDict[str, TabInfo] = OrderedDict()
        self.last_activity = time.time()
        self.is_active = True
        self._lock = asyncio.Lock()
        self._closed = False

        logger.info(f"BrowserInstance created for session {session_id}")

    def update_activity(self):
        """Update the last activity timestamp."""
        self.last_activity = time.time()
        self.is_active = True

    async def create_tab(
        self, tab_id: Optional[str] = None, url: Optional[str] = None
    ) -> tuple[str, Page]:
        """Create a new tab with optional URL.

        Args:
            tab_id: Optional custom tab ID (auto-generated if not provided)
            url: Optional URL to navigate to

        Returns:
            Tuple of (tab_id, page)
        """
        async with self._lock:
            if self._closed:
                raise RuntimeError("Browser instance has been closed")

            # Evict tabs if at limit
            if len(self.tabs) >= self.MAX_TABS:
                await self._evict_oldest_tab()

            # Generate tab ID if not provided
            if tab_id is None:
                tab_id = f"tab_{int(time.time() * 1000)}_{len(self.tabs)}"

            # Create new page
            page = await self.context.new_page()

            # Set default viewport
            await page.set_viewport_size({"width": 1920, "height": 1080})

            # Navigate if URL provided
            if url:
                await page.goto(url, wait_until="domcontentloaded")

            # Create tab info
            tab_info = TabInfo(page=page, url=url or "about:blank")

            # Store tab (move to end for LRU)
            self.tabs[tab_id] = tab_info
            self.tabs.move_to_end(tab_id)

            self.update_activity()
            logger.debug(f"Created tab {tab_id} for session {self.session_id}")

            return tab_id, page

    async def get_tab(self, tab_id: str) -> Optional[Page]:
        """Get a tab by ID, updating its access time (LRU).

        Args:
            tab_id: The tab ID

        Returns:
            The Page object or None if not found
        """
        async with self._lock:
            if self._closed:
                return None

            tab_info = self.tabs.get(tab_id)
            if tab_info:
                tab_info.touch()
                self.tabs.move_to_end(tab_id)
                self.update_activity()
                return tab_info.page
            return None

    async def close_tab(self, tab_id: str) -> bool:
        """Close a specific tab.

        Args:
            tab_id: The tab ID to close

        Returns:
            True if tab was closed, False if not found
        """
        async with self._lock:
            if self._closed:
                return False

            tab_info = self.tabs.pop(tab_id, None)
            if tab_info:
                try:
                    await tab_info.page.close()
                    logger.debug(f"Closed tab {tab_id} for session {self.session_id}")
                except Exception as e:
                    logger.warning(f"Error closing tab {tab_id}: {e}")
                self.update_activity()
                return True
            return False

    async def list_tabs(self) -> Dict[str, dict]:
        """Get a list of all tabs with their info.

        Returns:
            Dictionary mapping tab_id to tab metadata
        """
        async with self._lock:
            if self._closed:
                return {}

            return {
                tab_id: {
                    "url": info.url,
                    "created_at": info.created_at,
                    "last_accessed": info.last_accessed,
                }
                for tab_id, info in self.tabs.items()
            }

    async def _evict_oldest_tab(self):
        """Evict the oldest (least recently used) tab.

        Must be called with _lock held.
        """
        if not self.tabs:
            return

        # Get the oldest tab (first in OrderedDict)
        oldest_id = next(iter(self.tabs))
        oldest_tab = self.tabs.pop(oldest_id)

        try:
            await oldest_tab.page.close()
            logger.info(f"Evicted oldest tab {oldest_id} due to tab limit")
        except Exception as e:
            logger.warning(f"Error evicting tab {oldest_id}: {e}")

    async def close_all_tabs(self):
        """Close all tabs except the browser itself."""
        async with self._lock:
            for tab_id, tab_info in list(self.tabs.items()):
                try:
                    await tab_info.page.close()
                except Exception as e:
                    logger.debug(f"Error closing tab {tab_id}: {e}")
            self.tabs.clear()
            self.update_activity()

    async def close(self):
        """Close the browser instance and all tabs."""
        async with self._lock:
            if self._closed:
                return

            self._closed = True
            self.is_active = False

            # Close all tabs
            await self.close_all_tabs()

            # Close context
            try:
                await self.context.close()
                logger.debug(f"Closed context for session {self.session_id}")
            except Exception as e:
                logger.debug(f"Error closing context: {e}")

            # Note: We don't close the browser here as it may be shared
            # The SubAgentBrowserManager handles browser lifecycle

            logger.info(f"BrowserInstance closed for session {self.session_id}")

    @property
    def tab_count(self) -> int:
        """Get the number of open tabs."""
        return len(self.tabs)

    @property
    def is_idle(self, timeout_seconds: float = 300) -> bool:
        """Check if the instance has been idle for too long.

        Args:
            timeout_seconds: Idle timeout in seconds (default 5 minutes)

        Returns:
            True if idle for longer than timeout
        """
        return (time.time() - self.last_activity) > timeout_seconds

    def get_stats(self) -> dict:
        """Get statistics about this browser instance.

        Returns:
            Dictionary with instance stats
        """
        return {
            "session_id": self.session_id,
            "tab_count": self.tab_count,
            "max_tabs": self.MAX_TABS,
            "is_active": self.is_active,
            "last_activity": self.last_activity,
            "idle_seconds": time.time() - self.last_activity,
            "closed": self._closed,
        }
