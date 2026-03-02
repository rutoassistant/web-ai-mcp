"""Browser automation components."""

from src.browser.manager import BrowserManager
from src.browser.stealth import StealthConfig, XvfbManager, detect_display, setup_xvfb_env
from src.browser.captcha import CaptchaSolver, MouseController, solve_captcha

__all__ = [
    "BrowserManager",
    "CaptchaSolver",
    "MouseController",
    "StealthConfig",
    "XvfbManager",
    "detect_display",
    "setup_xvfb_env",
    "solve_captcha",
]
