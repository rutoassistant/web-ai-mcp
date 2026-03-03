"""Gemini Web Chat tool implementations using Playwright."""

import asyncio
import logging
from typing import Optional

from patchright.async_api import Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)


class GeminiChatTools:
    """Tools for interacting with Gemini web interface."""

    GEMINI_URL = "https://gemini.google.com"

    INPUT_SELECTORS = [
        "textarea[aria-label*='message']",
        "textarea[aria-label*='prompt']",
        "div[contenteditable='true'][role='textbox']",
        "rich-textarea div[contenteditable='true']",
        "input[placeholder*='message']",
        "textarea#prompt-input",
    ]

    SEND_BUTTON_SELECTORS = [
        "button[aria-label*='Send']",
        "button[aria-label*='Generate']",
        "div[role='button'][aria-label*='Send']",
        "button.submit-button",
        "button[data-testid='send-button']",
    ]

    RESPONSE_SELECTORS = [
        "gemini-response-viewer div",
        "response-content div",
        "div[role='presentation']:not([aria-hidden='true'])",
        "message-content .response",
    ]

    RESET_BUTTON_SELECTORS = [
        "button[aria-label*='Reset']",
        "button[aria-label*='Clear']",
        "button[aria-label*='New chat']",
        "button[data-testid='reset-button']",
    ]

    def __init__(self, page: Page):
        self.page = page
        self._chat_initialized = False

    async def _find_element(
        self, selectors: list[str], timeout: int = 5000
    ) -> Optional:
        """Try multiple selectors to find an element."""
        for selector in selectors:
            try:
                element = await self.page.wait_for_selector(selector, timeout=timeout)
                if element:
                    return element
            except PlaywrightTimeoutError:
                continue
        return None

    async def _ensure_chat_page(self) -> bool:
        """Navigate to Gemini and ensure chat interface is ready."""
        try:
            await self.page.goto(
                self.GEMINI_URL, wait_until="networkidle", timeout=30000
            )
            await asyncio.sleep(2)

            await self._handle_popups()

            input_element = await self._find_element(
                self.INPUT_SELECTORS, timeout=10000
            )
            if input_element:
                self._chat_initialized = True
                return True

            logger.warning("Could not find chat input after navigation")
            return False

        except Exception as e:
            logger.error(f"Failed to initialize chat page: {e}")
            return False

    async def _handle_popups(self):
        """Handle common popups and overlays."""
        popup_close_selectors = [
            "button[aria-label='Close']",
            "button[aria-label='Dismiss']",
            "button.close-button",
            "div[role='button'][aria-label='Close']",
            "button:has-text('Got it')",
            "button:has-text('Accept')",
            "button:has-text('Agree')",
        ]

        for selector in popup_close_selectors:
            try:
                button = await self.page.wait_for_selector(selector, timeout=2000)
                if button:
                    await button.click()
                    await asyncio.sleep(0.5)
            except PlaywrightTimeoutError:
                continue

    async def send_message(self, message: str, timeout: int = 60000) -> str:
        """Send a message to Gemini and return the response."""
        try:
            if not self._chat_initialized:
                ready = await self._ensure_chat_page()
                if not ready:
                    return "Error: Failed to initialize Gemini chat interface"

            input_element = await self._find_element(
                self.INPUT_SELECTORS, timeout=10000
            )
            if not input_element:
                return "Error: Could not find message input field"

            await input_element.fill(message)
            await asyncio.sleep(0.5)

            send_button = await self._find_element(
                self.SEND_BUTTON_SELECTORS, timeout=5000
            )
            if send_button:
                await send_button.click()
            else:
                await input_element.press("Enter")

            await asyncio.sleep(2)

            response = await self._wait_for_response(timeout)
            return response

        except PlaywrightTimeoutError:
            return "Error: Timeout waiting for response"
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return f"Error: {str(e)}"

    async def _wait_for_response(self, timeout: int) -> str:
        """Wait for and extract Gemini's response."""
        try:
            await self.page.wait_for_load_state("networkidle", timeout=timeout)

            await asyncio.sleep(3)

            response_element = await self._find_element(
                self.RESPONSE_SELECTORS, timeout=15000
            )
            if response_element:
                response_text = await response_element.inner_text()
                if response_text and response_text.strip():
                    return response_text.strip()

            response_text = await self.page.evaluate("""
                () => {
                    const candidates = document.querySelectorAll('gemini-response-viewer, response-content, div[role="presentation"]');
                    for (const candidate of candidates) {
                        const text = candidate.innerText || candidate.textContent;
                        if (text && text.length > 10) return text;
                    }
                    return '';
                }
            """)

            if response_text and response_text.strip():
                return response_text.strip()

            return "Error: Could not extract response text"

        except PlaywrightTimeoutError:
            return "Error: Timeout waiting for response to complete"
        except Exception as e:
            logger.error(f"Error extracting response: {e}")
            return f"Error extracting response: {str(e)}"

    async def reset_chat(self) -> str:
        """Reset the chat by starting a new conversation."""
        try:
            reset_button = await self._find_element(
                self.RESET_BUTTON_SELECTORS, timeout=5000
            )
            if reset_button:
                await reset_button.click()
                await asyncio.sleep(1)
                self._chat_initialized = False
                return "Chat reset successfully"

            try:
                await self.page.goto(
                    self.GEMINI_URL, wait_until="networkidle", timeout=30000
                )
                await asyncio.sleep(2)
                self._chat_initialized = False
                return "Chat reset successfully (page refreshed)"
            except Exception as e:
                return f"Error resetting chat: {str(e)}"

        except Exception as e:
            logger.error(f"Error resetting chat: {e}")
            return f"Error resetting chat: {str(e)}"
