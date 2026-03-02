"""
CAPTCHA solver for automated browser automation.
Supports Cloudflare Turnstile, hCaptcha, and reCAPTCHA with human-like interactions.
"""

import asyncio
import logging
import os
import random
import time
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Try to import pyautogui, handle gracefully if no display available
pyautogui = None
pyautogui_available = False


def _init_pyautogui():
    """Initialize pyautogui if display is available."""
    global pyautogui, pyautogui_available

    if pyautogui_available and pyautogui is not None:
        return True

    try:
        import pyautogui as _pyautogui

        # Test if display is available
        _pyautogui.position()
        pyautogui = _pyautogui
        pyautogui_available = True
        # Configure PyAutoGUI for safety
        pyautogui.FAILSAFE = True  # Move mouse to corner to abort
        pyautogui.PAUSE = 0.1  # Small pause between actions
        logger.info("PyAutoGUI initialized successfully")
        return True
    except Exception as e:
        logger.debug(f"PyAutoGUI not available (no display?): {e}")
        pyautogui = None
        pyautogui_available = False
        return False


# Try to initialize on module load, but don't fail if no display
_init_pyautogui()


class CaptchaSolver:
    """CAPTCHA detection and solving with human-like interactions."""

    # CAPTCHA detection selectors
    CAPTCHA_SELECTORS = {
        "cloudflare_turnstile": [
            'iframe[src*="challenges.cloudflare.com"]',
            ".cf-turnstile",
            "[data-cf-turnstile]",
            'input[name="cf-turnstile-response"]',
        ],
        "hcaptcha": [
            ".h-captcha",
            "[data-hcaptcha-widget-id]",
            'iframe[src*="hcaptcha.com"]',
        ],
        "recaptcha": [
            ".g-recaptcha",
            "[data-sitekey]",
            'iframe[src*="google.com/recaptcha"]',
            'iframe[src*="recaptcha.net"]',
        ],
        "slider": [
            'button:has-text("Drag the slider")',
            'button:has-text("slider")',
            '[role="button"]:has-text("Drag")',
            'input[type="range"]',
            '.slider-captcha',
            '[class*="slider"]',
        ],
    }

    # CAPTCHA challenge indicators
    CHALLENGE_INDICATORS = [
        "challenge",
        "captcha",
        "verification",
        "verify",
        "i'm not a robot",
        "are you human",
        "security check",
        "please verify",
        "cloudflare",
        "drag the slider",
        "confirm you're not a robot",
        "slide to verify",
    ]

    def __init__(self, templates_dir: Optional[str] = None):
        """Initialize CAPTCHA solver.

        Args:
            templates_dir: Directory containing CAPTCHA template images
        """
        self.templates_dir = (
            Path(templates_dir)
            if templates_dir
            else Path(__file__).parent.parent.parent / "templates"
        )
        self.templates: Dict[str, np.ndarray] = {}
        self._load_templates()

    def _load_templates(self):
        """Load CAPTCHA template images for template matching."""
        if not self.templates_dir.exists():
            logger.warning(f"Templates directory not found: {self.templates_dir}")
            return

        template_files = {
            "turnstile_checkbox": "turnstile_checkbox.png",
            "verify_button": "verify_button.png",
            "hcaptcha_checkbox": "hcaptcha_checkbox.png",
            "recaptcha_checkbox": "recaptcha_checkbox.png",
        }

        for name, filename in template_files.items():
            template_path = self.templates_dir / filename
            if template_path.exists():
                try:
                    template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
                    if template is not None:
                        self.templates[name] = template
                        logger.info(f"Loaded template: {name}")
                except Exception as e:
                    logger.error(f"Failed to load template {name}: {e}")
            else:
                logger.debug(f"Template not found: {template_path}")

    async def detect_captcha(self, page) -> Tuple[bool, Optional[str]]:
        """Detect if CAPTCHA is present on the page.

        Args:
            page: Playwright page object

        Returns:
            Tuple of (detected: bool, captcha_type: Optional[str])
        """
        # Check for CAPTCHA selectors
        for captcha_type, selectors in self.CAPTCHA_SELECTORS.items():
            for selector in selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        logger.info(f"Detected {captcha_type} CAPTCHA")
                        return True, captcha_type
                except Exception:
                    continue

        # Check page content for challenge indicators
        try:
            content = await page.content()
            content_lower = content.lower()

            # First check for domain-based detection
            domain_patterns = {
                "cloudflare_turnstile": ["challenges.cloudflare.com", "turnstile"],
                "hcaptcha": ["hcaptcha.com", "h-captcha", "hcaptcha"],
                "recaptcha": ["recaptcha.net", "google.com/recaptcha", "g-recaptcha"],
            }

            for captcha_type, patterns in domain_patterns.items():
                if any(pattern in content_lower for pattern in patterns):
                    logger.info(f"Detected {captcha_type} via domain/content analysis")
                    return True, captcha_type

            # Check for challenge indicators with CAPTCHA context
            for indicator in self.CHALLENGE_INDICATORS:
                if indicator in content_lower:
                    # Check if it's in a CAPTCHA context
                    for captcha_type in self.CAPTCHA_SELECTORS.keys():
                        # Check for variations: hcaptcha, h-captcha, h_captcha
                        type_variants = [
                            captcha_type.replace("_", ""),  # hcaptcha
                            captcha_type.replace("_", "-"),  # h-captcha
                            captcha_type,  # h_captcha
                        ]
                        if any(variant in content_lower for variant in type_variants):
                            logger.info(f"Detected {captcha_type} via content analysis")
                            return True, captcha_type
        except Exception as e:
            logger.debug(f"Error checking page content: {e}")

        return False, None

    async def solve(self, page, timeout: int = 30) -> Dict[str, Any]:
        """Attempt to solve CAPTCHA on the page.

        Args:
            page: Playwright page object
            timeout: Maximum time to wait for CAPTCHA solving

        Returns:
            Dictionary with solving results
        """
        start_time = time.time()
        result = {"success": False, "type": None, "method": None, "duration": 0}

        # Detect CAPTCHA type
        detected, captcha_type = await self.detect_captcha(page)
        if not detected:
            logger.info("No CAPTCHA detected")
            return {**result, "success": True, "message": "No CAPTCHA detected"}

        result["type"] = captcha_type
        logger.info(f"Attempting to solve {captcha_type} CAPTCHA")

        # Try to solve based on CAPTCHA type
        try:
            if captcha_type == "cloudflare_turnstile":
                success = await self._solve_turnstile(page, timeout)
            elif captcha_type == "hcaptcha":
                success = await self._solve_hcaptcha(page, timeout)
            elif captcha_type == "recaptcha":
                success = await self._solve_recaptcha(page, timeout)
            elif captcha_type == "slider":
                success = await self._solve_slider(page, timeout)
            else:
                success = await self._solve_generic(page, timeout)

            result["success"] = success
            result["duration"] = time.time() - start_time

            if success:
                logger.info(f"CAPTCHA solved successfully in {result['duration']:.2f}s")
            else:
                logger.warning("Failed to solve CAPTCHA")

        except Exception as e:
            logger.error(f"Error solving CAPTCHA: {e}")
            result["error"] = str(e)
            result["duration"] = time.time() - start_time

        return result

    async def _solve_turnstile(self, page, timeout: int) -> bool:
        """Solve Cloudflare Turnstile CAPTCHA.

        Args:
            page: Playwright page object
            timeout: Maximum wait time

        Returns:
            True if solved successfully
        """
        logger.info("Solving Cloudflare Turnstile CAPTCHA")

        # Find Turnstile iframe
        iframe_selector = 'iframe[src*="challenges.cloudflare.com"]'
        iframe = await page.query_selector(iframe_selector)

        if not iframe:
            logger.warning("Turnstile iframe not found")
            return False

        # Get iframe position
        try:
            box = await iframe.bounding_box()
            if not box:
                logger.warning("Could not get iframe bounding box")
                return False

            # Calculate click position (center of iframe, slightly randomized)
            click_x = box["x"] + box["width"] / 2 + random.randint(-10, 10)
            click_y = box["y"] + box["height"] / 2 + random.randint(-10, 10)

            # Perform human-like click
            await self._human_click(click_x, click_y)

            # Wait for verification
            await asyncio.sleep(2)

            # Check if CAPTCHA is still present
            remaining_time = timeout - 2
            while remaining_time > 0:
                detected, _ = await self.detect_captcha(page)
                if not detected:
                    logger.info("Turnstile CAPTCHA solved")
                    return True
                await asyncio.sleep(0.5)
                remaining_time -= 0.5

            logger.warning("Turnstile CAPTCHA still present after timeout")
            return False

        except Exception as e:
            logger.error(f"Error solving Turnstile: {e}")
            return False

    async def _solve_hcaptcha(self, page, timeout: int) -> bool:
        """Solve hCaptcha.

        Args:
            page: Playwright page object
            timeout: Maximum wait time

        Returns:
            True if solved successfully
        """
        logger.info("Solving hCaptcha (limited support - may require manual intervention)")

        # hCaptcha typically requires image selection which is complex to automate
        # For now, try template matching to click the initial checkbox
        iframe = await page.query_selector('iframe[src*="hcaptcha.com"]')
        if iframe:
            try:
                box = await iframe.bounding_box()
                if box:
                    # Try to find checkbox using template matching
                    success = await self._template_click(page, box, "hcaptcha_checkbox")
                    if success:
                        # Wait to see if it solves
                        await asyncio.sleep(5)
                        detected, _ = await self.detect_captcha(page)
                        return not detected
            except Exception as e:
                logger.error(f"Error solving hCaptcha: {e}")

        return False

    async def _solve_recaptcha(self, page, timeout: int) -> bool:
        """Solve reCAPTCHA v2.

        Args:
            page: Playwright page object
            timeout: Maximum wait time

        Returns:
            True if solved successfully
        """
        logger.info("Solving reCAPTCHA v2 (limited support)")

        # Try to find and click the checkbox
        checkbox_selector = ".rc-anchor-checkbox"
        try:
            checkbox = await page.query_selector(checkbox_selector)
            if checkbox:
                box = await checkbox.bounding_box()
                if box:
                    click_x = box["x"] + box["width"] / 2
                    click_y = box["y"] + box["height"] / 2
                    await self._human_click(click_x, click_y)

                    # Wait for verification
                    await asyncio.sleep(5)
                    detected, _ = await self.detect_captcha(page)
                    return not detected
        except Exception as e:
            logger.error(f"Error solving reCAPTCHA: {e}")

        return False

    async def _solve_slider(self, page, timeout: int) -> bool:
        """Solve slider CAPTCHA (e.g., Brave Search).

        Args:
            page: Playwright page object
            timeout: Maximum wait time

        Returns:
            True if solved successfully
        """
        logger.info("Solving slider CAPTCHA")

        # Try to find slider button/element
        slider_selectors = [
            'button:has-text("Drag the slider")',
            'button:has-text("slider")',
            '[role="button"]:has-text("Drag")',
            'input[type="range"]',
            '.slider-captcha button',
            '[class*="slider"] button',
        ]

        slider_element = None
        for selector in slider_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    slider_element = element
                    logger.info(f"Found slider element with selector: {selector}")
                    break
            except Exception:
                continue

        if not slider_element:
            logger.warning("Slider element not found")
            return False

        try:
            # Get slider bounding box
            box = await slider_element.bounding_box()
            if not box:
                logger.warning("Could not get slider bounding box")
                return False

            # Calculate drag positions
            start_x = box["x"] + box["width"] * 0.1  # Start slightly inside
            start_y = box["y"] + box["height"] / 2
            end_x = box["x"] + box["width"] * 0.9  # End slightly inside
            end_y = start_y

            logger.info(f"Slider drag from ({start_x}, {start_y}) to ({end_x}, {end_y})")

            # Perform human-like drag
            if pyautogui_available and pyautogui is not None:
                # Move to start position
                await self._human_click(start_x, start_y)
                await asyncio.sleep(0.2)

                # Perform drag operation
                pyautogui.mouseDown()
                await asyncio.sleep(0.1)

                # Generate human-like drag path
                path = self._generate_mouse_path(
                    (int(start_x), int(start_y)),
                    (int(end_x), int(end_y)),
                    steps=30
                )

                for point in path:
                    pyautogui.moveTo(point[0], point[1])
                    await asyncio.sleep(random.uniform(0.01, 0.03))

                pyautogui.mouseUp()
                logger.info("Slider drag completed")
            else:
                # Fallback: Use Playwright's drag simulation
                await slider_element.hover()
                await page.mouse.down()
                await page.mouse.move(end_x, end_y, steps=30)
                await page.mouse.up()
                logger.info("Slider drag completed via Playwright")

            # Wait for verification
            await asyncio.sleep(2)

            # Check if CAPTCHA is still present
            remaining_time = timeout - 3
            while remaining_time > 0:
                detected, _ = await self.detect_captcha(page)
                if not detected:
                    logger.info("Slider CAPTCHA solved")
                    return True
                await asyncio.sleep(0.5)
                remaining_time -= 0.5

            logger.warning("Slider CAPTCHA still present after timeout")
            return False

        except Exception as e:
            logger.error(f"Error solving slider CAPTCHA: {e}")
            return False

    async def _solve_generic(self, page, timeout: int) -> bool:
        """Generic CAPTCHA solving using template matching.

        Args:
            page: Playwright page object
            timeout: Maximum wait time

        Returns:
            True if solved successfully
        """
        logger.info("Attempting generic CAPTCHA solving")

        # Take screenshot and look for known templates
        screenshot_path = "/tmp/captcha_screenshot.png"
        await page.screenshot(path=screenshot_path)

        try:
            screenshot = cv2.imread(screenshot_path, cv2.IMREAD_GRAYSCALE)
            if screenshot is None:
                logger.warning("Could not load screenshot for template matching")
                return False

            # Try each template
            for template_name, template in self.templates.items():
                match_result = self._match_template(screenshot, template)
                if match_result:
                    x, y, confidence = match_result
                    logger.info(
                        f"Found template {template_name} at ({x}, {y}) with confidence {confidence:.2f}"
                    )

                    if confidence > 0.7:  # Good match threshold
                        await self._human_click(x, y)
                        await asyncio.sleep(3)

                        # Check if solved
                        detected, _ = await self.detect_captcha(page)
                        return not detected

        except Exception as e:
            logger.error(f"Error in generic solving: {e}")

        return False

    def _match_template(
        self, screenshot: np.ndarray, template: np.ndarray, threshold: float = 0.7
    ) -> Optional[Tuple[int, int, float]]:
        """Match template in screenshot using OpenCV.

        Args:
            screenshot: Screenshot as numpy array
            template: Template image to match
            threshold: Minimum match confidence

        Returns:
            Tuple of (x, y, confidence) or None if no match
        """
        try:
            # Check if images are constant (all same pixel value)
            # Constant images can produce false matches with 1.0 confidence
            screenshot_std = np.std(screenshot)
            template_std = np.std(template)

            if screenshot_std < 1e-6 or template_std < 1e-6:
                # One or both images are effectively constant
                logger.debug("Rejecting match: constant image detected")
                return None

            result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            if max_val >= threshold:
                # Get center of matched region
                h, w = template.shape[:2]
                center_x = max_loc[0] + w // 2
                center_y = max_loc[1] + h // 2
                return (center_x, center_y, max_val)

        except Exception as e:
            logger.debug(f"Template matching error: {e}")

        return None

    async def _template_click(self, page, iframe_box: Dict[str, float], template_name: str) -> bool:
        """Click using template matching within an iframe.

        Args:
            page: Playwright page object
            iframe_box: Bounding box of the iframe
            template_name: Name of template to match

        Returns:
            True if clicked successfully
        """
        if template_name not in self.templates:
            logger.warning(f"Template {template_name} not loaded")
            return False

        # Take screenshot of iframe region
        screenshot_path = "/tmp/iframe_screenshot.png"

        try:
            # Calculate iframe region
            clip = {
                "x": iframe_box["x"],
                "y": iframe_box["y"],
                "width": iframe_box["width"],
                "height": iframe_box["height"],
            }
            await page.screenshot(path=screenshot_path, clip=clip)

            screenshot = cv2.imread(screenshot_path, cv2.IMREAD_GRAYSCALE)
            if screenshot is None:
                return False

            template = self.templates[template_name]
            match = self._match_template(screenshot, template, threshold=0.6)

            if match:
                rel_x, rel_y, confidence = match
                # Convert to absolute coordinates
                abs_x = iframe_box["x"] + rel_x
                abs_y = iframe_box["y"] + rel_y

                logger.info(
                    f"Template click at ({abs_x}, {abs_y}) with confidence {confidence:.2f}"
                )
                await self._human_click(abs_x, abs_y)
                return True

        except Exception as e:
            logger.error(f"Error in template click: {e}")

        return False

    async def _human_click(self, x: float, y: float):
        """Perform human-like mouse click with natural movement.

        Args:
            x: Target X coordinate
            y: Target Y coordinate
        """
        if not pyautogui_available or pyautogui is None:
            logger.warning("PyAutoGUI not available, skipping mouse click")
            return

        current_x, current_y = pyautogui.position()
        target_x, target_y = int(x), int(y)

        # Generate human-like path
        path = self._generate_mouse_path((current_x, current_y), (target_x, target_y))

        # Move along path
        for point in path:
            pyautogui.moveTo(point[0], point[1], duration=random.uniform(0.001, 0.005))
            await asyncio.sleep(random.uniform(0.001, 0.01))

        # Small pause before click
        await asyncio.sleep(random.uniform(0.05, 0.15))

        # Click with slight randomization
        final_x = target_x + random.randint(-2, 2)
        final_y = target_y + random.randint(-2, 2)
        pyautogui.click(final_x, final_y)

        logger.debug(f"Human-like click at ({final_x}, {final_y})")

    def _generate_mouse_path(
        self, start: Tuple[int, int], end: Tuple[int, int], steps: int = 25
    ) -> List[Tuple[int, int]]:
        """Generate human-like mouse movement path using Bezier curves.

        Args:
            start: Starting coordinates
            end: Ending coordinates
            steps: Number of steps in the path

        Returns:
            List of (x, y) coordinates
        """
        start_x, start_y = start
        end_x, end_y = end

        # Create control points for Bezier curve
        # Add some randomness to make it look human
        mid_x = (start_x + end_x) / 2 + random.randint(-50, 50)
        mid_y = (start_y + end_y) / 2 + random.randint(-50, 50)

        path = []
        for i in range(steps):
            t = i / (steps - 1)

            # Quadratic Bezier curve
            x = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * mid_x + t**2 * end_x
            y = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * mid_y + t**2 * end_y

            # Add small random noise
            noise_x = random.randint(-3, 3) * (1 - t)  # Less noise near end
            noise_y = random.randint(-3, 3) * (1 - t)

            path.append((int(x + noise_x), int(y + noise_y)))

        return path

    async def wait_for_captcha_resolution(
        self, page, check_interval: float = 0.5, timeout: int = 30
    ) -> bool:
        """Wait for CAPTCHA to be resolved (either manually or automatically).

        Args:
            page: Playwright page object
            check_interval: How often to check (seconds)
            timeout: Maximum wait time

        Returns:
            True if CAPTCHA was resolved
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            detected, captcha_type = await self.detect_captcha(page)
            if not detected:
                logger.info("CAPTCHA resolved")
                return True
            await asyncio.sleep(check_interval)

        logger.warning(f"CAPTCHA still present after {timeout}s")
        return False


class MouseController:
    """Human-like mouse controller with PyAutoGUI."""

    def __init__(self):
        """Initialize mouse controller."""
        if pyautogui_available and pyautogui is not None:
            self.screen_width, self.screen_height = pyautogui.size()
        else:
            # Default screen size when pyautogui not available
            self.screen_width, self.screen_height = 1920, 1080
        logger.info(f"Screen size: {self.screen_width}x{self.screen_height}")

    async def move_to(self, x: int, y: int, duration: Optional[float] = None):
        """Move mouse to coordinates with human-like timing.

        Args:
            x: Target X coordinate
            y: Target Y coordinate
            duration: Movement duration (randomized if not specified)
        """
        if not pyautogui_available or pyautogui is None:
            logger.warning("PyAutoGUI not available, skipping mouse move")
            return

        if duration is None:
            # Calculate duration based on distance
            current_x, current_y = pyautogui.position()
            distance = ((x - current_x) ** 2 + (y - current_y) ** 2) ** 0.5
            duration = min(0.5, max(0.1, distance / 2000))  # 0.1-0.5s

        pyautogui.moveTo(x, y, duration=duration)
        await asyncio.sleep(random.uniform(0.01, 0.05))

    async def click(self, x: Optional[int] = None, y: Optional[int] = None):
        """Click at coordinates (or current position).

        Args:
            x: X coordinate (optional)
            y: Y coordinate (optional)
        """
        if not pyautogui_available or pyautogui is None:
            logger.warning("PyAutoGUI not available, skipping mouse click")
            return

        if x is not None and y is not None:
            await self.move_to(x, y)

        # Randomize click timing
        await asyncio.sleep(random.uniform(0.05, 0.15))
        pyautogui.click()
        await asyncio.sleep(random.uniform(0.01, 0.05))

    async def scroll(self, amount: int):
        """Scroll with human-like behavior.

        Args:
            amount: Scroll amount (positive = up, negative = down)
        """
        if not pyautogui_available or pyautogui is None:
            logger.warning("PyAutoGUI not available, skipping scroll")
            return

        # Break into smaller scrolls
        steps = abs(amount) // 50 + 1
        step_amount = amount // steps

        for _ in range(steps):
            pyautogui.scroll(step_amount)
            await asyncio.sleep(random.uniform(0.05, 0.15))

    async def drag_to(self, start_x: int, start_y: int, end_x: int, end_y: int):
        """Drag from start to end position.

        Args:
            start_x: Starting X coordinate
            start_y: Starting Y coordinate
            end_x: Ending X coordinate
            end_y: Ending Y coordinate
        """
        if not pyautogui_available or pyautogui is None:
            logger.warning("PyAutoGUI not available, skipping drag")
            return

        await self.move_to(start_x, start_y)
        pyautogui.mouseDown()  # type: ignore

        # Generate path for drag
        solver = CaptchaSolver()
        path = solver._generate_mouse_path((start_x, start_y), (end_x, end_y), steps=20)

        for point in path:
            pyautogui.moveTo(point[0], point[1])  # type: ignore
            await asyncio.sleep(random.uniform(0.01, 0.02))

        pyautogui.mouseUp()  # type: ignore


# Convenience function for simple CAPTCHA solving
async def solve_captcha(
    page, timeout: int = 30, templates_dir: Optional[str] = None
) -> Dict[str, Any]:
    """Convenience function to solve CAPTCHA on a page.

    Args:
        page: Playwright page object
        timeout: Maximum time to wait
        templates_dir: Directory containing templates

    Returns:
        Dictionary with solving results
    """
    solver = CaptchaSolver(templates_dir=templates_dir)
    return await solver.solve(page, timeout=timeout)
