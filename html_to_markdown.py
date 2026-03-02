import trafilatura
from bs4 import BeautifulSoup
from typing import Optional
import re


class HTMLToMarkdownConverter:
    def __init__(self):
        # Tags to completely remove along with their content
        self.ignored_tags = {
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside",
            "noscript",
            "iframe",
            "object",
            "embed",
            "applet",
            "form",
            "button",
            "select",
            "textarea",
            "svg",
            "canvas",
            "video",
            "audio",
            "template",
            "dialog",
            "menu",
            "menuitem",
        }

        # Selectors for common unwanted elements (ads, social, cookies)
        self.unwanted_selectors = [
            '[class*="ad"]',
            '[id*="ad"]',
            '[class*="advertisement"]',
            '[class*="sponsored"]',
            '[class*="promoted"]',
            '[class*="cookie"]',
            '[id*="cookie"]',
            '[class*="gdpr"]',
            '[id*="gdpr"]',
            '[class*="consent"]',
            '[id*="consent"]',
            '[class*="privacy"]',
            '[class*="banner"]',
            '[class*="social"]',
            '[class*="share"]',
            '[class*="follow"]',
            '[class*="sidebar"]',
            '[id*="sidebar"]',
            '[class*="newsletter"]',
            '[id*="newsletter"]',
            '[class*="popup"]',
            '[id*="popup"]',
            '[class*="modal"]',
            '[id*="modal"]',
            '[class*="overlay"]',
            '[id*="overlay"]',
        ]

    def clean_html(self, html: str) -> str:
        """Clean HTML by removing unwanted tags and attributes."""
        soup = BeautifulSoup(html, "html.parser")

        # Remove ignored tags
        for tag in self.ignored_tags:
            for element in soup.find_all(tag):
                element.decompose()

        # Remove unwanted elements by CSS selectors
        for selector in self.unwanted_selectors:
            try:
                for element in soup.select(selector):
                    # Only remove if it doesn't look like main content (heuristic)
                    text_len = len(element.get_text(strip=True))
                    if text_len < 200 or len(element.find_all("a")) > text_len / 20:
                        element.decompose()
            except:
                pass

        # Remove unwanted attributes
        for element in soup.find_all():
            for attr in ["style", "class", "id", "onclick", "onload", "onerror"]:
                if element.has_attr(attr):
                    del element[attr]
            # Remove data attributes
            for attr in list(element.attrs.keys()):
                if attr.startswith("data-"):
                    del element[attr]

        return str(soup)

    def html_to_markdown(self, html: str) -> str:
        """Main method to convert HTML to Markdown using trafilatura."""
        cleaned_html = self.clean_html(html)

        # Use trafilatura for robust extraction and conversion
        extracted = trafilatura.extract(
            cleaned_html,
            include_comments=False,
            include_tables=True,
            output_format="markdown",
        )

        if not extracted:
            # Fallback to markdownify if trafilatura extraction fails
            from markdownify import markdownify as md

            markdown = md(cleaned_html, heading_style="ATX", bullets="-")
        else:
            markdown = extracted

        # Clean up excess whitespace
        markdown = re.sub(r"\n\s*\n\s*\n+", "\n\n", markdown)
        return markdown.strip()


# Example usage
if __name__ == "__main__":
    converter = HTMLToMarkdownConverter()

    sample_html = """
    <html>
        <body>
            <header><h1>Site Header</h1></header>
            <nav>Menu</nav>
            <main>
                <h1>Article Title</h1>
                <p>This is <strong>important</strong> content.</p>
                <div class="ad-container">Buy our product!</div>
            </main>
            <footer>Copyright 2026</footer>
        </body>
    </html>
    """

    print(converter.html_to_markdown(sample_html))
