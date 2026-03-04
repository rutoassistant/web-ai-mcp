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
        # Duck.ai specific
        "textarea[name='user-prompt']",
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
        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                # Use 'load' wait state with longer timeout; Gemini can be slow
                await self.page.goto(
                    self.GEMINI_URL, wait_until="load", timeout=120000
                )
                await asyncio.sleep(3)

                await self._handle_popups()

                # Check if we were redirected to Duck.ai (common issue)
                current_url = self.page.url
                if "duck.ai" in current_url:
                    logger.warning("Redirected to Duck.ai detected. Dismissing dialogs...")
                    await self._dismiss_duckai_dialog()
                    await asyncio.sleep(2)

                input_element = await self._find_element(
                    self.INPUT_SELECTORS, timeout=20000
                )
                if input_element:
                    self._chat_initialized = True
                    logger.info("Gemini chat page initialized successfully")
                    return True

                logger.warning(f"Could not find chat input after navigation (attempt {attempt+1})")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(3)
                    continue
                return False

            except Exception as e:
                logger.error(f"Failed to initialize chat page (attempt {attempt+1}): {e}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(3)
                    continue
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

    async def _dismiss_duckai_dialog(self):
        """Dismiss the Duck.ai consent dialog that blocks input."""
        # The dialog appears with dynamic classes; try multiple strategies
        strategies = [
            # Close button with specific aria-label
            lambda: self.page.locator("div[role='dialog'] button[aria-label='Close']").first,
            # Buttons with common text
            lambda: self.page.locator("div[role='dialog'] button:has-text('Accept')").first,
            lambda: self.page.locator("div[role='dialog'] button:has-text('Got it')").first,
            lambda: self.page.locator("div[role='dialog'] button:has-text('Continue')").first,
            lambda: self.page.locator("div[role='dialog'] button:has-text('Start')").first,
            # The actual button on Duck.ai: "Agree and Continue"
            lambda: self.page.get_by_role("button", name="Agree and Continue"),
            # Any button containing "Agree"
            lambda: self.page.locator("div[role='dialog'] button:has-text('Agree')").first,
            # Any close button on page
            lambda: self.page.locator("button[aria-label='Close']").first,
            # Clicking on the dialog itself sometimes works for dismissal
            lambda: self.page.locator("div[role='dialog']").first,
        ]
        for strat in strategies:
            try:
                el = await strat()
                if await el.count() > 0:
                    if await el.is_visible():
                        await el.click()
                        logger.info("Dismissed Duck.ai dialog")
                        await asyncio.sleep(2)  # wait for UI to settle
                        return
            except Exception:
                continue
        # As fallback, press Escape to close dialogs
        try:
            await self.page.keyboard.press("Escape")
            await asyncio.sleep(1)
        except Exception:
            pass

    async def send_message(self, message: str, timeout: int = 120000) -> str:
        """Send a message to Gemini and return the response."""
        try:
            if not self._chat_initialized:
                ready = await self._ensure_chat_page()
                if not ready:
                    return "Error: Failed to initialize Gemini chat interface"

            input_element = await self._find_element(
                self.INPUT_SELECTORS, timeout=20000
            )
            if not input_element:
                return "Error: Could not find message input field"

            # If input is disabled, try to dismiss overlays one more time
            if not await input_element.is_enabled():
                await self._handle_popups()
                await self._dismiss_duckai_dialog()
                await asyncio.sleep(1)
                if not await input_element.is_enabled():
                    # Reload page as last resort
                    await self.page.reload(wait_until="domcontentloaded")
                    await asyncio.sleep(3)
                    await self._handle_popups()
                    await self._dismiss_duckai_dialog()
                    await asyncio.sleep(2)
                    input_element = await self._find_element(self.INPUT_SELECTORS, timeout=10000)
                    if not input_element or not await input_element.is_enabled():
                        return "Error: Input field not enabled after retries"

            await input_element.fill(message)
            await asyncio.sleep(1)

            send_button = await self._find_element(
                self.SEND_BUTTON_SELECTORS, timeout=10000
            )
            if send_button:
                await send_button.click()
            else:
                await input_element.press("Enter")

            # Wait for response with longer timeout
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
            # Wait for network to be idle, but with a cap
            await self.page.wait_for_load_state("networkidle", timeout=timeout)
            await asyncio.sleep(3)

            # Try to find a response element
            response_element = await self._find_element(
                self.RESPONSE_SELECTORS, timeout=20000
            )
            if response_element:
                response_text = await response_element.inner_text()
                if response_text and response_text.strip():
                    return response_text.strip()

            # Fallback: evaluate to get any meaningful text from common containers
            response_text = await self.page.evaluate("""
                () => {
                    const candidates = document.querySelectorAll('gemini-response-viewer, response-content, div[role="presentation"], model-response, chat-turn, .response, .answer');
                    for (const candidate of candidates) {
                        const text = candidate.innerText || candidate.textContent;
                        if (text && text.length > 10) return text;
                    }
                    // As last resort, return the last large text block in the page
                    const allText = document.body.innerText;
                    if (allText && allText.length > 20) {
                        // Return last 2000 chars as a heuristic
                        return allText.slice(-2000);
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

            # Avoid networkidle timeout: use domcontentloaded
            try:
                await self.page.goto(
                    self.GEMINI_URL, wait_until="domcontentloaded", timeout=30000
                )
                await asyncio.sleep(2)
                self._chat_initialized = False
                return "Chat reset successfully (page refreshed)"
            except Exception as e:
                return f"Error resetting chat: {str(e)}"

        except Exception as e:
            logger.error(f"Error resetting chat: {e}")
            return f"Error resetting chat: {str(e)}"
