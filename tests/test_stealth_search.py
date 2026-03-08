"""
Tests for StealthSearchTools and models in src/tools/stealth_search.py
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import unquote

from src.tools.stealth_search import (
    StealthSearchTools,
    SearchResult,
    AISummary,
    SearchResponse,
    ExtractedContent,
    stealth_search,
    stealth_extract,
    stealth_scrape,
)


def create_mock_page():
    """Create a mock Playwright page object."""
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.evaluate = AsyncMock()
    page.content = AsyncMock()
    return page


class TestSearchResultModel:
    """Test cases for SearchResult Pydantic model."""

    def test_search_result_creation(self):
        """Test SearchResult creation with required fields."""
        result = SearchResult(
            title="Test Title",
            url="https://example.com",
            snippet="Test snippet",
            position=1,
        )

        assert result.title == "Test Title"
        assert result.url == "https://example.com"
        assert result.snippet == "Test snippet"
        assert result.position == 1

    def test_search_result_defaults(self):
        """Test SearchResult default values."""
        result = SearchResult(
            title="Test", url="https://example.com", snippet="Snippet"
        )

        assert result.position == 0


class TestAISummaryModel:
    """Test cases for AISummary Pydantic model."""

    def test_ai_summary_creation(self):
        """Test AISummary creation."""
        summary = AISummary(
            text="AI generated summary",
            sources=[{"title": "Source 1", "url": "https://example.com"}],
        )

        assert summary.text == "AI generated summary"
        assert len(summary.sources) == 1

    def test_ai_summary_empty_sources(self):
        """Test AISummary with empty sources."""
        summary = AISummary(text="Summary only")

        assert summary.text == "Summary only"
        assert summary.sources == []


class TestSearchResponseModel:
    """Test cases for SearchResponse Pydantic model."""

    def test_search_response_creation(self):
        """Test SearchResponse creation."""
        results = [
            SearchResult(
                title="Result 1", url="https://a.com", snippet="Snippet 1", position=1
            ),
            SearchResult(
                title="Result 2", url="https://b.com", snippet="Snippet 2", position=2
            ),
        ]

        response = SearchResponse(
            query="test query", results=results, page=1, has_next_page=False
        )

        assert response.query == "test query"
        assert len(response.results) == 2
        assert response.page == 1
        assert response.has_next_page is False

    def test_search_response_with_ai_summary(self):
        """Test SearchResponse with AI summary."""
        ai_summary = AISummary(text="AI Summary", sources=[])

        response = SearchResponse(query="test", results=[], ai_summary=ai_summary)

        assert response.ai_summary is not None
        assert response.ai_summary.text == "AI Summary"


class TestExtractedContentModel:
    """Test cases for ExtractedContent Pydantic model."""

    def test_extracted_content_creation(self):
        """Test ExtractedContent creation."""
        content = ExtractedContent(
            title="Page Title",
            url="https://example.com",
            content="Extracted content text",
            word_count=5,
        )

        assert content.title == "Page Title"
        assert content.url == "https://example.com"
        assert content.content == "Extracted content text"
        assert content.word_count == 5

    def test_extracted_content_with_summary(self):
        """Test ExtractedContent with optional summary."""
        content = ExtractedContent(
            title="Title",
            url="https://example.com",
            content="Long content here " * 50,
            summary="Short summary",
            word_count=100,
        )

        assert content.summary == "Short summary"


class TestStealthSearchTools:
    """Test cases for StealthSearchTools class."""

    def test_init(self):
        """Test initialization of StealthSearchTools."""
        page = create_mock_page()
        tools = StealthSearchTools(page)

        assert tools.page is page
        assert tools.BRAVE_SEARCH_URL == "https://search.brave.com/search"
        assert tools.MAX_PAGE == 100
        assert tools.MAX_COUNT == 100

    @pytest.mark.asyncio
    async def test_search_empty_query(self):
        """Test search with empty query raises error."""
        page = create_mock_page()
        tools = StealthSearchTools(page)

        with pytest.raises(ValueError, match="Query cannot be empty"):
            await tools.search("")

    @pytest.mark.asyncio
    async def test_search_whitespace_query(self):
        """Test search with whitespace-only query raises error."""
        page = create_mock_page()
        tools = StealthSearchTools(page)

        with pytest.raises(ValueError, match="Query cannot be empty"):
            await tools.search("   ")

    @pytest.mark.asyncio
    async def test_search_invalid_page(self):
        """Test search with invalid page number raises error."""
        page = create_mock_page()
        tools = StealthSearchTools(page)

        with pytest.raises(ValueError, match="Page must be between"):
            await tools.search("test", page=0)

        with pytest.raises(ValueError, match="Page must be between"):
            await tools.search("test", page=101)

    @pytest.mark.asyncio
    async def test_search_invalid_count(self):
        """Test search with invalid count raises error."""
        page = create_mock_page()
        tools = StealthSearchTools(page)

        with pytest.raises(ValueError, match="Count must be between"):
            await tools.search("test", count=0)

        with pytest.raises(ValueError, match="Count must be between"):
            await tools.search("test", count=101)

    @pytest.mark.asyncio
    async def test_search_success(self):
        """Test successful search returns results."""
        page = create_mock_page()
        page.goto = AsyncMock()
        page.wait_for_selector = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.evaluate = AsyncMock(
            return_value={
                "results": [
                    {
                        "title": "Result 1",
                        "url": "https://example.com",
                        "snippet": "Snippet 1",
                        "position": 1,
                    },
                    {
                        "title": "Result 2",
                        "url": "https://test.com",
                        "snippet": "Snippet 2",
                        "position": 2,
                    },
                ],
                "aiSummary": None,
            }
        )

        tools = StealthSearchTools(page)
        response = await tools.search("test query", count=10)

        assert response.query == "test query"
        assert len(response.results) == 2
        assert response.results[0].title == "Result 1"

    @pytest.mark.asyncio
    async def test_search_with_pagination(self):
        """Test search with pagination parameters."""
        page = create_mock_page()
        page.goto = AsyncMock()
        page.wait_for_selector = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.evaluate = AsyncMock(return_value={"results": [], "aiSummary": None})

        tools = StealthSearchTools(page)
        response = await tools.search("test", page=2, count=5)

        assert response.page == 2

    @pytest.mark.asyncio
    async def test_search_with_ai_summary(self):
        """Test search extracts AI summary."""
        page = create_mock_page()
        page.goto = AsyncMock()
        page.wait_for_selector = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.evaluate = AsyncMock(
            return_value={
                "results": [],
                "aiSummary": {
                    "text": "AI Summary Text",
                    "sources": [{"title": "Source", "url": "https://source.com"}],
                },
            }
        )

        tools = StealthSearchTools(page)
        response = await tools.search("test")

        assert response.ai_summary is not None
        assert response.ai_summary.text == "AI Summary Text"

    @pytest.mark.asyncio
    async def test_search_no_results(self):
        """Test search with no results."""
        page = create_mock_page()
        page.goto = AsyncMock()
        page.wait_for_selector = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.evaluate = AsyncMock(return_value={"results": [], "aiSummary": None})

        tools = StealthSearchTools(page)
        response = await tools.search("no results query")

        assert len(response.results) == 0
        assert response.ai_summary is None


class TestStealthSearchToolsExtract:
    """Test extraction methods of StealthSearchTools."""

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Test needs proper trafilatura mocking - complex async/sync interaction"
    )
    async def test_extract_success(self):
        """Test successful content extraction."""
        pass

    @pytest.mark.asyncio
    async def test_extract_with_max_length(self):
        """Test extraction respects max_length."""
        page = create_mock_page()
        page.goto = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.evaluate = AsyncMock(return_value="A" * 10000)

        tools = StealthSearchTools(page)

        with patch("src.tools.stealth_search.TRAFILATURA_AVAILABLE", False):
            content = await tools.extract("https://example.com", max_length=100)

        assert len(content.content) <= 103  # 100 + "..."

    @pytest.mark.asyncio
    async def test_extract_with_trafilatura(self):
        """Test extraction uses trafilatura when available."""
        page = create_mock_page()
        page.goto = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.content = AsyncMock(
            return_value="<html><body><article>Test</article></body></html>"
        )

        tools = StealthSearchTools(page)

        mock_result = '{"title": "Test Page", "text": "Extracted with trafilatura"}'

        with patch("src.tools.stealth_search.TRAFILATURA_AVAILABLE", True):
            with patch("src.tools.stealth_search.trafilatura") as mock_trafilatura:
                mock_trafilatura.extract = MagicMock(return_value=mock_result)
                content = await tools.extract("https://example.com")

                assert content.title == "Test Page"


class TestStealthSearchToolsScrape:
    """Test scrape_page method of StealthSearchTools."""

    @pytest.mark.asyncio
    async def test_scrape_page_success(self):
        """Test successful page scraping."""
        page = create_mock_page()
        page.goto = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.content = AsyncMock(
            return_value="<html><body><h1>Title</h1><p>Content</p></body></html>"
        )

        tools = StealthSearchTools(page)

        with patch("src.tools.stealth_search.MARKDOWNIFY_AVAILABLE", False):
            result = await tools.scrape_page("https://example.com")

        assert "Title" in result or "Content" in result

    @pytest.mark.asyncio
    async def test_scrape_page_with_markdownify(self):
        """Test page scraping with markdownify."""
        page = create_mock_page()
        page.goto = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.content = AsyncMock(return_value="<html><body><h1>Test</h1></body></html>")

        tools = StealthSearchTools(page)

        with patch("src.tools.stealth_search.MARKDOWNIFY_AVAILABLE", True):
            with patch("src.tools.stealth_search.md") as mock_md:
                mock_md.return_value = "# Test\n"
                result = await tools.scrape_page("https://example.com")

                mock_md.assert_called_once()


class TestStealthSearchToolsHelpers:
    """Test helper methods of StealthSearchTools."""

    @pytest.mark.asyncio
    async def test_get_page_title(self):
        """Test _get_page_title method."""
        page = create_mock_page()
        page.evaluate = AsyncMock(return_value="Test Page Title")

        tools = StealthSearchTools(page)
        title = await tools._get_page_title()

        assert title == "Test Page Title"

    def test_clean_content(self):
        """Test _clean_content method."""
        page = create_mock_page()
        tools = StealthSearchTools(page)

        dirty_text = "Text with   whitespace  \n\n\n\nand newlines"
        cleaned = tools._clean_content(dirty_text)

        assert "  " not in cleaned
        assert "\n\n\n\n" not in cleaned

    def test_clean_content_removes_social_prompts(self):
        """Test _clean_content removes social sharing prompts."""
        page = create_mock_page()
        tools = StealthSearchTools(page)

        text = "Article content here Share this on Facebook Follow us on Twitter"
        cleaned = tools._clean_content(text)

        assert "Share this" not in cleaned
        assert "Follow us" not in cleaned

    def test_generate_summary(self):
        """Test _generate_summary method."""
        page = create_mock_page()
        tools = StealthSearchTools(page)

        text = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence."
        summary = tools._generate_summary(text, sentences=3)

        assert "First sentence" in summary
        assert "Second sentence" in summary
        assert "Third sentence" in summary
        assert "Fourth sentence" not in summary


class TestConvenienceFunctions:
    """Test convenience functions."""

    @pytest.mark.asyncio
    async def test_stealth_search_function(self):
        """Test stealth_search convenience function."""
        page = create_mock_page()
        page.goto = AsyncMock()
        page.wait_for_selector = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.evaluate = AsyncMock(return_value={"results": [], "aiSummary": None})

        result = await stealth_search(page, "test query")

        assert isinstance(result, SearchResponse)
        assert result.query == "test query"

    @pytest.mark.asyncio
    async def test_stealth_extract_function(self):
        """Test stealth_extract convenience function."""
        page = create_mock_page()
        page.goto = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.evaluate = AsyncMock(return_value="Content")

        result = await stealth_extract(page, "https://example.com")

        assert isinstance(result, ExtractedContent)

    @pytest.mark.asyncio
    async def test_stealth_scrape_function(self):
        """Test stealth_scrape convenience function."""
        page = create_mock_page()
        page.goto = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.content = AsyncMock(return_value="<html>Content</html>")

        result = await stealth_scrape(page, "https://example.com")

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_stealth_search_with_session(self):
        """Test stealth_search with session_id uses manager."""
        page = create_mock_page()

        mock_manager = MagicMock()
        mock_browser_instance = MagicMock()
        mock_browser_instance.page = page
        mock_manager.get_or_create_browser = AsyncMock(
            return_value=mock_browser_instance
        )

        mock_manager.get_or_create_browser = AsyncMock(
            return_value=mock_browser_instance
        )

        with patch("src.tools.stealth_search.StealthSearchTools") as mock_tools_class:
            mock_tools_instance = MagicMock()
            mock_tools_class.return_value = mock_tools_instance
            mock_tools_instance.search = AsyncMock(
                return_value=SearchResponse(
                    query="test", results=[], page=1, has_next_page=False
                )
            )

            await stealth_search(
                page, "test", session_id="session1", manager=mock_manager
            )

            mock_manager.get_or_create_browser.assert_called_once_with("session1")
