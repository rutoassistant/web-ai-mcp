"""
Selector definitions and resilience helpers.
Centralize selectors for DuckDuckGo AI Chat to ease maintenance.
"""

# Input box selectors (attempt in order)
INPUT_SELECTORS = [
    'textarea[placeholder*="Ask"]',
    'textarea[placeholder*="ask"]',
    'textarea',
    '[role="textbox"]'
]

# Send button selectors (if needed)
SEND_SELECTORS = [
    'button[type="submit"]',
    'button.send-button',
    'button[aria-label="Send"]'
]

# Message containers
MESSAGE_SELECTORS = [
    'div[data-role="assistant"]',
    'div.message.assistant',
    'div[class*="msg--"]:not(.user)'
]

# Welcome modal buttons
WELCOME_BUTTONS = ["Get Started", "Start Chatting", "I Agree", "Got It"]

def is_response_complete(page) -> bool:
    """
    Heuristic to determine if the assistant has finished streaming.
    Could check for absence of a 'stop' button or presence of final message.
    For now, we rely on timeouts; this can be enhanced.
    """
    return True
