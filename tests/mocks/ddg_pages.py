"""
Mock HTML structures for DuckDuckGo AI Chat pages.
Useful for testing selectors without hitting live site.
"""

HOME_PAGE = """
<!DOCTYPE html>
<html>
<head><title>DuckDuckGo AI Chat</title></head>
<body>
  <div id="chat-container">
    <textarea placeholder="Ask me anything..."></textarea>
    <button class="send-button">Send</button>
  </div>
  <div id="messages">
    <div class="message user">Hello</div>
    <div class="message assistant">Hi there! How can I help?</div>
  </div>
</body>
</html>
"""

WELCOME_MODAL = """
<!DOCTYPE html>
<html>
<head><title>Welcome</title></head>
<body>
  <div class="modal">
    <button class="primary">Get Started</button>
    <button class="secondary">I Agree</button>
  </div>
</body>
</html>
"""

ERROR_STATE = """
<!DOCTYPE html>
<html>
<head><title>Error</title></head>
<body>
  <div class="error">Something went wrong</div>
</body>
</html>
"""
