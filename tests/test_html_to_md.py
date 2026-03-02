import pytest
from html_to_markdown import HTMLToMarkdownConverter


class TestHTMLToMarkdownConverter:
    def setup_method(self):
        self.converter = HTMLToMarkdownConverter()

    def test_basic_conversion(self):
        html = """
        <h1>Test Heading</h1>
        <p>This is a <strong>sample</strong> paragraph with <a href="https://example.com">a link</a>.</p>
        """
        # markdownify might add extra whitespace or different link formatting
        result = self.converter.html_to_markdown(html)
        assert "# Test Heading" in result
        assert "This is a **sample** paragraph" in result
        assert "[a link](https://example.com)" in result

    def test_list_conversion(self):
        html = """
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
        </ul>
        """
        result = self.converter.html_to_markdown(html)
        assert "- Item 1" in result
        assert "- Item 2" in result

    def test_ignored_tags_removal(self):
        html = """
        <div>
            <script>console.log('This should be removed');</script>
            <style>body { color: red; }</style>
            <nav>Navigation: <a href="/home">Home</a></nav>
            <p>Main content</p>
            <footer>Copyright info</footer>
        </div>
        """
        result = self.converter.html_to_markdown(html)
        assert "Main content" in result
        assert "console.log" not in result
        assert "Navigation" not in result
        assert "Copyright info" not in result

    def test_unwanted_selectors_removal(self):
        html = """
        <div>
            <div class="ad-banner">Big Sale!</div>
            <div id="cookie-notice">Accept cookies?</div>
            <p>Real Article Content</p>
        </div>
        """
        result = self.converter.html_to_markdown(html)
        assert "Real Article Content" in result
        assert "Big Sale!" not in result
        assert "Accept cookies?" not in result

    def test_complex_html_logic(self):
        html = """
        <html>
            <head><title>Page</title></head>
            <body>
                <header><h1>Site</h1></header>
                <nav>Links</nav>
                <article>
                    <h2>Title</h2>
                    <p>Text.</p>
                </article>
                <aside>Sidebar</aside>
                <footer>End</footer>
            </body>
        </html>
        """
        result = self.converter.html_to_markdown(html)
        assert "Title" in result
        assert "Text." in result
        assert "Site" not in result
        assert "Links" not in result
        assert "Sidebar" not in result
        assert "End" not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
