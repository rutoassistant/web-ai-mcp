"""Stealth Search and content extraction tools."""

import logging
from typing import List, Optional
from urllib.parse import quote

from pydantic import BaseModel
from patchright.async_api import Page

try:
    from markdownify import markdownify as md

    MARKDOWNIFY_AVAILABLE = True
except ImportError:
    md = None
    MARKDOWNIFY_AVAILABLE = False

trafilatura = None
TRAFILATURA_AVAILABLE = False

try:
    import trafilatura as _trafilatura

    trafilatura = _trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    pass

logger = logging.getLogger(__name__)


class SearchResult(BaseModel):
    """Model for search result data."""

    title: str
    url: str
    snippet: str
    position: int


class AISummary(BaseModel):
    """AI-generated summary from Brave Search."""

    text: str
    sources: List[dict] = []  # List of {title, url}


class SearchResponse(BaseModel):
    """Complete search response with optional AI summary."""

    ai_summary: Optional[AISummary] = None
    results: List[SearchResult]
    query: str
    page: int = 1
    has_next_page: bool = False


class ExtractedContent(BaseModel):
    """Model for extracted content data."""

    title: str
    url: str
    content: str
    summary: Optional[str] = None
    word_count: int


class StealthSearchTools:
    """Tools for Stealth Search and content extraction."""

    BRAVE_SEARCH_URL = "https://search.brave.com/search"
    MAX_PAGE = 100
    MAX_COUNT = 100

    def __init__(self, page: Page):
        self.page = page

    async def search(self, query: str, count: int = 10, page: int = 1) -> SearchResponse:
        """Search Brave Search and return structured results.

        Args:
            query: Search query string
            count: Number of results to return (default: 10)
            page: Page number for pagination (default: 1)

        Returns:
            SearchResponse object containing results and optional AI summary
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        if page < 1 or page > self.MAX_PAGE:
            raise ValueError(f"Page must be between 1 and {self.MAX_PAGE}")

        if count < 1 or count > self.MAX_COUNT:
            raise ValueError(f"Count must be between 1 and {self.MAX_COUNT}")

        logger.info(f"Searching Brave for: {query} (count={count}, page={page})")

        # Navigate to Brave search with query
        encoded_query = quote(query)
        search_url = f"{self.BRAVE_SEARCH_URL}?q={encoded_query}"

        # Add page parameter for pagination (Brave uses 0-based indexing internally)
        if page > 1:
            search_url += f"&page={page}"

        # Use domcontentloaded for faster navigation, then wait for results
        await self.page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

        # Wait for page to be more stable
        await self.page.wait_for_timeout(3000)

        # Wait for search results to load with increased timeout
        # Brave Search is a SPA, so we need to wait for JavaScript rendering
        try:
            # Primary: Wait for any link with external URL
            await self.page.wait_for_selector(
                "a[href^='https://www.'], a[href^='https://en.'], a[href^='http']", timeout=20000
            )
            logger.info("Found external links on page")

            # Optional: Wait for AI summary to appear (it can be slow)
            logger.info("Waiting for AI Summary...")
            try:
                # Brave's AI answer uses multiple possible selectors
                # Updated 2026-02: Brave uses .answer class and data attributes
                ai_selectors = [
                    ".answer",  # Main AI answer container
                    '[data-component="Summarizer"]',
                    ".summarizer",
                    "#answer-box",
                    '[class*="answer"]',
                    '[class*="ai-response"]',
                    ".snippet",
                ]
                selector_list = ", ".join(ai_selectors)
                await self.page.wait_for_selector(
                    selector_list,
                    timeout=15000,
                )
                logger.info("AI Summary element detected on page")

                # Wait for the AI text to actually populate (not just the container)
                # The element appears before text is generated
                for i in range(10):
                    await self.page.wait_for_timeout(500)
                    # Check if any AI element has meaningful text
                    has_text = await self.page.evaluate("""
                        () => {
                            const selectors = ['.answer', '[class*="answer"]', '.summarizer'];
                            for (const sel of selectors) {
                                const el = document.querySelector(sel);
                                if (el && el.textContent.trim().length > 50) {
                                    return true;
                                }
                            }
                            return false;
                        }
                    """)
                    if has_text:
                        logger.info(f"AI Summary text populated after {(i + 1) * 500}ms")
                        break
                else:
                    logger.info("AI Summary element found but text not populated after 5s")

            except Exception as e:
                logger.info(f"AI Summary not found or timed out: {e}")
        except Exception as e:
            logger.warning(f"Could not find expected search result selectors: {e}")

        # Debug: Check what's actually in the page for AI summary
        ai_debug = await self.page.evaluate("""
            () => {
                const debug = {};
                
                // Check the chatllm-answer-list structure specifically
                const answerEl = document.querySelector('.chatllm-answer-list, [class*="chatllm-answer"], [class*="answer"]');
                if (answerEl) {
                    debug.parentClass = answerEl.className;
                    debug.parentText = answerEl.textContent.trim().substring(0, 300);
                    debug.childrenCount = answerEl.children.length;
                    
                    // Check each child
                    debug.children = [];
                    for (const child of answerEl.children) {
                        debug.children.push({
                            tag: child.tagName,
                            class: child.className,
                            text: child.textContent.trim().substring(0, 200)
                        });
                    }
                    
                    // Also check for any bold/strong elements that might contain the subject
                    const strongs = answerEl.querySelectorAll('strong, b, .bold');
                    debug.strongTexts = Array.from(strongs).map(s => s.textContent.trim());
                }
                
                return debug;
            }
        """)

        if ai_debug:
            logger.info(f"AI Debug info: {ai_debug}")

        # Extract search results and AI summary using JavaScript
        data = await self.page.evaluate(
            f"""
            () => {{
                const results = [];
                const seenUrls = new Set();
                let aiSummary = null;

                // --- AI Summary Extraction ---
                // Updated 2026-02-10: Brave uses .chatllm-answer-list class for AI responses
                const aiSummarySelectors = [
                    '.chatllm-answer-list',  // Brave's current AI answer class
                    '[class*="chatllm-answer"]',
                    '[class*="answer"]',  // Any class containing "answer"
                    '.answer',
                    '[data-component="Summarizer"]',
                    '.summarizer-container',
                    '.summarizer',
                    '#answer-box',
                    '.summary',
                    '#summary',
                    '[class*="ai-answer"]',
                    '[class*="ai-response"]'
                ];

                for (const sel of aiSummarySelectors) {{
                    const el = document.querySelector(sel);
                    if (el) {{
                        console.log('AI Summary found with selector:', sel, 'class:', el.className);
                        
                        // Debug: Log the full element text and child structure
                        const fullText = el.textContent.trim();
                        console.log('Full element text (first 200 chars):', fullText.substring(0, 200));
                        
                        // Get text directly from the element itself (not looking for children)
                        // Brave's chatllm-answer-list has the text directly
                        const clone = el.cloneNode(true);
                        
                        // Remove only citation/reference elements, not content
                        clone.querySelectorAll('sup.citation, .cite-link, [data-cite]').forEach(e => e.remove());
                        
                        const text = clone.textContent.trim().replace(/\\s+/g, ' ');
                        console.log('Extracted text length:', text.length, 'preview:', text.substring(0, 150));
                        
                        // Extract citations from the original element (look in parent too)
                        const citationContainer = el.closest('[class*="answer"]') || el;
                        const sources = Array.from(citationContainer.querySelectorAll('a[href]')).map(a => ({{
                            title: a.textContent.trim() || a.hostname,
                            url: a.href
                        }})).filter(s => s.url.startsWith('http') && !s.url.includes('search.brave.com') && !s.url.includes('imgs.search.brave.com') && s.title.length > 1);

                        // Deduplicate sources
                        const uniqueSources = [];
                        const seenSourceUrls = new Set();
                        for (const s of sources) {{
                            if (!seenSourceUrls.has(s.url)) {{
                                seenSourceUrls.add(s.url);
                                uniqueSources.push(s);
                            }}
                        }}

                        if (text.length > 20) {{
                            aiSummary = {{ text, sources: uniqueSources }};
                            console.log('Extracted AI Summary text length:', text.length);
                            break;
                        }}
                    }}
                }}

                // --- Web Results Extraction ---
                // Strategy 1: Try Brave Search specific selectors (newest structure)
                const braveSelectors = [
                    '#results .snippet:has(a.l1)',
                    '#results [data-component="Result"]',
                    '.snippet:has(a.l1)',
                    '#results .snippet',
                    '.snippet',
                    'div[data-loc="main"] > div > div',
                    'main article',
                    'article[data-loc]',
                    '.search-result',
                    '.result-item',
                    '[data-component="search-result"]'
                ];

                let resultElements = [];
                for (const sel of braveSelectors) {{
                    const elements = document.querySelectorAll(sel);
                    if (elements.length > 0) {{
                        resultElements = elements;
                        break;
                    }}
                }}

                // Strategy 2: If no structured results, find all external links
                if (resultElements.length === 0) {{
                    const allLinks = Array.from(document.querySelectorAll('a[href^="https://"]'));
                    const searchLinks = allLinks.filter(a => {{
                        const href = a.href;
                        const text = a.textContent.trim();
                        return href &&
                               text.length > 5 &&
                               !href.includes('search.brave.com') &&
                               !href.includes('brave.com/') &&
                               !href.includes('imgs.search.brave.com') &&
                               !a.closest('nav') &&
                               !a.closest('footer');
                    }});

                    const containers = new Map();
                    for (const link of searchLinks) {{
                        let parent = link.closest('article, section, div[class*="result"], div[class*=\"item\"], li');
                        if (!parent) parent = link.parentElement?.parentElement?.parentElement;
                        if (parent && !containers.has(parent)) containers.set(parent, link);
                    }}
                    resultElements = Array.from(containers.keys());
                }}

                // Extract results from elements
                for (let i = 0; i < Math.min(resultElements.length, {count}); i++) {{
                    const element = resultElements[i];
                    let title = '';
                    let url = '';
                    let snippet = '';

                    const titleLink = element.querySelector('a.l1') ||
                                     element.querySelector('a[href^="https://"]') ||
                                     element.querySelector('a[href^="http://"]') ||
                                     element.querySelector('a');
                    if (titleLink) {{
                        url = titleLink.href;
                        const titleEl = titleLink.querySelector('.title') || 
                                        element.querySelector('h2, h3, [class*="title"]');
                        title = titleEl ? titleEl.textContent.trim() : titleLink.textContent.trim();
                    }}

                    const snippetEl = element.querySelector('p, [class*="description"], [class*="snippet"], [data-loc="snippet"]');
                    if (snippetEl) snippet = snippetEl.textContent.trim();

                    if (title && url && !seenUrls.has(url) && url.startsWith('http')) {{
                        seenUrls.add(url);
                        results.push({{
                            title: title.substring(0, 200),
                            url: url,
                            snippet: snippet.substring(0, 500),
                            position: results.length + 1
                        }});
                    }}
                }}

                return {{ results, aiSummary }};
            }}
            """
        )

        results = data.get("results", [])
        ai_summary_data = data.get("aiSummary")

        # Debug logging for AI summary extraction
        if ai_summary_data:
            extracted_text = ai_summary_data.get("text", "")
            logger.info(
                f"AI Summary extracted - length: {len(extracted_text)}, preview: '{extracted_text[:100]}...'"
            )
        else:
            logger.info("AI Summary data was None or empty")

        # Convert to Pydantic models
        search_results = []
        for i, result in enumerate(results[:count]):
            search_results.append(
                SearchResult(
                    title=result.get("title", ""),
                    url=result.get("url", ""),
                    snippet=result.get("snippet", ""),
                    position=result.get("position", i + 1),
                )
            )

        ai_summary = None
        if ai_summary_data:
            ai_summary = AISummary(
                text=ai_summary_data.get("text", ""), sources=ai_summary_data.get("sources", [])
            )

        logger.info(f"Found {len(search_results)} search results")
        if ai_summary:
            logger.info(f"Extracted AI summary: {ai_summary.text[:100]}...")
        else:
            logger.info("No AI summary extracted (ai_summary_data was None or empty)")

        has_next_page = len(results) >= count
        return SearchResponse(
            query=query,
            results=search_results,
            ai_summary=ai_summary,
            page=page,
            has_next_page=has_next_page,
        )

    async def extract(self, url: str, max_length: int = 5000) -> ExtractedContent:
        """Extract clean content from a URL.

        Args:
            url: URL to extract content from
            max_length: Maximum content length (default: 5000)

        Returns:
            ExtractedContent object with clean text
        """
        logger.info(f"Extracting content from: {url}")

        # Navigate to the URL with better timeout handling
        await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await self.page.wait_for_timeout(2000)

        # Wait for content to load
        await self.page.wait_for_timeout(2000)

        # Try trafilatura first if available
        if TRAFILATURA_AVAILABLE and trafilatura is not None:
            try:
                html_content = await self.page.content()
                extracted = trafilatura.extract(
                    html_content,
                    include_comments=False,
                    include_tables=False,
                    no_fallback=False,
                    output_format="json",
                )

                if extracted:
                    import json

                    data = json.loads(extracted)
                    title = data.get("title", "")
                    text = data.get("text", "")

                    # Clean up the text
                    text = self._clean_content(text)

                    # Truncate if needed
                    if len(text) > max_length:
                        text = text[:max_length].rsplit(" ", 1)[0] + "..."

                    # Generate summary if content is long
                    summary = None
                    word_count = len(text.split())
                    if word_count > 100:
                        summary = self._generate_summary(text)

                    return ExtractedContent(
                        title=title or await self._get_page_title(),
                        url=url,
                        content=text,
                        summary=summary,
                        word_count=word_count,
                    )
            except Exception as e:
                logger.warning(f"Trafilatura extraction failed: {e}")

        # Fallback to JavaScript extraction
        return await self._extract_with_js(url, max_length)

    async def scrape_page(self, url: str, include_images: bool = False) -> str:
        """Deep page scraper that returns full content in Markdown.

        Args:
            url: URL to scrape
            include_images: Whether to include images in markdown

        Returns:
            Markdown formatted string of the page content
        """
        logger.info(f"Deep scraping (Markdown) from: {url}")

        # Navigate to the URL
        await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)

        # Give JS a bit more time to settle for SPA-like sites
        await self.page.wait_for_timeout(3000)

        # Get the HTML content
        html_content = await self.page.content()

        if MARKDOWNIFY_AVAILABLE:
            # Configure markdownify
            kwargs = {
                "heading_style": "ATX",
                "bullets": "-",
            }
            if not include_images:
                kwargs["strip"] = ["img"]

            markdown = md(html_content, **kwargs)

            # Basic cleanup: remove excess newlines
            import re

            markdown = re.sub(r"\n{3,}", "\n\n", markdown)
            return markdown.strip()
        else:
            # Fallback to basic text if markdownify is not available
            content = await self.page.evaluate("() => document.body.innerText")
            return f"# Content from {url}\n\n{content}"

    async def _extract_with_js(self, url: str, max_length: int) -> ExtractedContent:
        """Extract content using JavaScript as fallback with aggressive cleaning."""

        # Get page title
        title = await self._get_page_title()

        # Extract main content using heuristics with aggressive element removal
        content = await self.page.evaluate(
            """
            () => {
                // Create a clone of the body to manipulate without affecting the page
                const bodyClone = document.body.cloneNode(true);
                
                // Aggressively remove non-content elements by tag name
                const tagsToRemove = [
                    'script', 'style', 'nav', 'header', 'footer', 'aside',
                    'form', 'input', 'button', 'select', 'textarea',
                    'svg', 'canvas', 'video', 'audio', 'iframe', 'embed', 'object',
                    'noscript', 'template', 'dialog', 'menu', 'menuitem'
                ];
                
                tagsToRemove.forEach(tag => {
                    const elements = bodyClone.querySelectorAll(tag);
                    elements.forEach(el => el.remove());
                });
                
                // Remove elements by common class/ID patterns for ads and non-content
                const adSelectors = [
                    // Ads and sponsored content
                    '[class*="ad"]', '[id*="ad"]', '[class*="advertisement"]',
                    '[class*="sponsored"]', '[class*="promoted"]',
                    '[class*="partner"]', '[class*="affiliate"]',
                    
                    // Cookie banners and GDPR notices
                    '[class*="cookie"]', '[id*="cookie"]', 
                    '[class*="gdpr"]', '[id*="gdpr"]',
                    '[class*="consent"]', '[id*="consent"]',
                    '[class*="privacy"]', '[class*="banner"]',
                    
                    // Social media widgets
                    '[class*="social"]', '[class*="share"]', '[class*="follow"]',
                    '[id*="social"]', '[id*="share"]',
                    
                    // Sidebars and navigation
                    '[class*="sidebar"]', '[id*="sidebar"]',
                    '[class*="menu"]', '[class*="navigation"]', '[class*="nav"]',
                    '[class*="breadcrumb"]', '[id*="breadcrumb"]',
                    
                    // Comments and engagement
                    '[class*="comment"]', '[id*="comment"]',
                    '[class*="disqus"]', '[id*="disqus"]',
                    '[class*="reaction"]', '[class*="rating"]',
                    
                    // Related content widgets
                    '[class*="related"]', '[id*="related"]',
                    '[class*="recommended"]', '[class*="popular"]',
                    '[class*="trending"]', '[class*="more"]',
                    '[class*="read-more"]', '[class*="see-also"]',
                    
                    // Newsletter and subscription
                    '[class*="newsletter"]', '[id*="newsletter"]',
                    '[class*="subscribe"]', '[class*="subscription"]',
                    '[class*="signup"]', '[class*="sign-up"]',
                    
                    // Popups and modals
                    '[class*="popup"]', '[id*="popup"]',
                    '[class*="modal"]', '[id*="modal"]',
                    '[class*="overlay"]', '[id*="overlay"]',
                    '[class*="sticky"]', '[class*="fixed"]',
                    
                    // Author and metadata
                    '[class*="author"]', '[class*="byline"]',
                    '[class*="date"]', '[class*="timestamp"]',
                    '[class*="meta"]', '[class*="metadata"]',
                    
                    // Tags and categories
                    '[class*="tags"]', '[class*="categories"]',
                    '[class*="tag-cloud"]', '[class*="keywords"]'
                ];
                
                adSelectors.forEach(selector => {
                    try {
                        const elements = bodyClone.querySelectorAll(selector);
                        elements.forEach(el => {
                            // Don't remove if it might be main content
                            const text = el.textContent || '';
                            const isShort = text.length < 200;
                            const isLinkOnly = el.querySelectorAll('a').length > 0 && text.trim().split(/\\s+/).length < 10;
                            
                            if (isShort || isLinkOnly) {
                                el.remove();
                            }
                        });
                    } catch (e) {
                        // Ignore invalid selectors
                    }
                });
                
                // Remove elements with display:none or visibility:hidden
                const allElements = bodyClone.querySelectorAll('*');
                allElements.forEach(el => {
                    try {
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                            el.remove();
                        }
                    } catch (e) {
                        // Element might be removed already
                    }
                });
                
                // Try to find main content with priority order
                const contentSelectors = [
                    // High priority semantic tags
                    'article',
                    'main',
                    '[role="main"]',
                    
                    // Common content containers
                    '.content',
                    '#content',
                    '.main-content',
                    '#main-content',
                    '.post-content',
                    '.article-content',
                    '.entry-content',
                    '.page-content',
                    
                    // Blog/CMS specific
                    '.post-body',
                    '.entry-body',
                    '.article-body',
                    '[itemprop="articleBody"]',
                    
                    // News sites
                    '.story-body',
                    '.story-content',
                    '.news-content',
                    
                    // Generic fallbacks
                    '.body',
                    '#body',
                    '[class*="content"]',
                    '[id*="content"]'
                ];

                let mainContent = null;
                let bestContentLength = 0;
                
                // First pass: try to find by semantic tags
                for (const selector of contentSelectors) {
                    const el = bodyClone.querySelector(selector);
                    if (el) {
                        const textLength = (el.textContent || '').length;
                        // Prefer longer content if it's substantial
                        if (textLength > bestContentLength && textLength > 500) {
                            mainContent = el;
                            bestContentLength = textLength;
                        }
                    }
                }

                // Second pass: if no good semantic content found, use heuristic scoring
                if (!mainContent || bestContentLength < 500) {
                    const candidates = bodyClone.querySelectorAll('div, section');
                    let bestScore = 0;
                    
                    candidates.forEach(el => {
                        const text = el.textContent || '';
                        const textLength = text.length;
                        const paragraphs = el.querySelectorAll('p').length;
                        const links = el.querySelectorAll('a').length;
                        const linkDensity = links > 0 ? textLength / links : textLength;
                        
                        // Score based on: text length, paragraph count, and link density
                        // Higher score = more likely to be main content
                        const score = (textLength * 0.5) + (paragraphs * 100) + (linkDensity * 0.3);
                        
                        if (score > bestScore && textLength > 300) {
                            // Check it's not just a navigation container
                            const className = (el.className || '').toLowerCase();
                            const id = (el.id || '').toLowerCase();
                            const isNavRelated = /nav|menu|sidebar|header|footer|comment|related|meta/.test(className + ' ' + id);
                            
                            if (!isNavRelated || paragraphs > 3) {
                                bestScore = score;
                                mainContent = el;
                            }
                        }
                    });
                }

                // Final fallback to body if no main content found
                if (!mainContent) {
                    mainContent = bodyClone;
                }

                // Get text content and clean it up
                let text = mainContent.innerText || mainContent.textContent || '';
                
                // Remove very short lines (likely UI elements)
                const lines = text.split('\\n');
                const filteredLines = lines.filter(line => {
                    const trimmed = line.trim();
                    return trimmed.length > 10 || (trimmed.length > 0 && trimmed.includes('.'));
                });
                text = filteredLines.join('\\n');
                
                // Clean up whitespace
                text = text.replace(/\\s+/g, ' ').trim();
                
                // Remove standalone URLs
                text = text.replace(/https?:\\/\\/[^\\s]+/g, '');
                
                return text;
            }
            """
        )

        # Clean content with the improved cleaner
        content = self._clean_content(content)

        # Truncate if needed
        if len(content) > max_length:
            content = content[:max_length].rsplit(" ", 1)[0] + "..."

        word_count = len(content.split())

        # Generate summary if content is long
        summary = None
        if word_count > 100:
            summary = self._generate_summary(content)

        return ExtractedContent(
            title=title, url=url, content=content, summary=summary, word_count=word_count
        )

    async def _get_page_title(self) -> str:
        """Get the page title."""
        return await self.page.evaluate("document.title") or ""

    def _clean_content(self, text: str) -> str:
        """Clean up extracted content with aggressive boilerplate removal."""
        if not text:
            return ""

        import re

        # Remove excess whitespace and normalize
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)

        # Remove social sharing and engagement prompts
        social_patterns = [
            r"Share this\s*(article|post|page)?\s*(on\s+\w+)?",
            r"Share on\s+(Facebook|Twitter|LinkedIn|X|Instagram|Pinterest|Reddit)",
            r"Follow us\s*(on\s+\w+)?",
            r"Like us\s*(on\s+\w+)?",
            r"Connect with us",
            r"Join the conversation",
            r"Leave a comment",
            r"Add a comment",
            r"Post a comment",
            r"\d+\s*(likes?|shares?|comments?|reactions?)",
        ]

        for pattern in social_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # Remove navigation and action prompts
        action_patterns = [
            r"Read more\s*(about this)?",
            r"Click here\s*(to\s+\w+)?",
            r"Learn more\s*(about)?",
            r"Find out more",
            r"Discover more",
            r"See more",
            r"View more",
            r"Show more",
            r"Expand\s*(for more)?",
            r"Continue reading",
            r"Skip to\s*(content|main|navigation)?",
            r"Jump to\s*\w+",
            r"Back to\s*(top|main|home)?",
            r"Go back",
            r"Next\s*(page|article|post)?",
            r"Previous\s*(page|article|post)?",
        ]

        for pattern in action_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # Remove subscription prompts
        subscription_patterns = [
            r"Subscribe\s*(to\s+\w+)?\s*(now)?",
            r"Sign up\s*(for\s+\w+)?\s*(now)?",
            r"Join\s*(our)?\s*(newsletter|list|community)",
            r"Newsletter\s*(signup|sign-up|subscription)?",
            r"Get\s+\w+\s+delivered\s+to\s+your\s+inbox",
            r"Stay\s+(updated|informed|connected)",
            r"Never\s+miss\s+(a|an)\s+\w+",
        ]

        for pattern in subscription_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # Remove cookie and privacy notices
        cookie_patterns = [
            r"Cookie\s*(Policy|Notice|Settings|Consent|Banner)?",
            r"This\s+site\s+uses\s+cookies",
            r"We\s+use\s+cookies\s+(to\s+\w+)?",
            r"By\s+(using|continuing|clicking)\s+.*?(you\s+agree|accept|consent)",
            r"Accept\s*(all)?\s*cookies",
            r"Cookie\s*preferences",
            r"Privacy\s*(Policy|Notice|Settings)",
            r"Terms\s*(of\s*Service|and\s*Conditions|of\s*Use)?",
            r"GDPR\s*compliance",
            r"California\s*Consumer\s*Privacy",
            r"Do\s*Not\s*Sell\s*My\s*Information",
        ]

        for pattern in cookie_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # Remove common navigation text
        nav_patterns = [
            r"Home\s*»?\s*",
            r"Menu\s*" r"Navigation\s*",
            r"Site\s*Map",
            r"Sitemap",
            r"Search\s*(this\s*site)?",
            r"Quick\s*Links",
            r"Related\s*(Links|Pages|Articles|Posts)?",
            r"You\s*might\s*also\s*like",
            r"Recommended\s*(for\s*you)?",
            r"Popular\s*\w+",
            r"Trending\s*\w+",
            r"Most\s*(Read|Viewed|Popular)",
        ]

        for pattern in nav_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # Remove ad-related text
        ad_patterns = [
            r"Advertisement\s*",
            r"Ad\s*\d*\s*",
            r"Sponsored\s*(content|post|link)?",
            r"Promoted\s*(content|post)?",
            r"Partner\s*content",
            r"Paid\s*(content|partnership)?",
            r"Affiliate\s*(link|disclosure)?",
        ]

        for pattern in ad_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # Remove copyright and legal text
        legal_patterns = [
            r"©\s*\d{4}.*?(All\s+rights\s+reserved)?",
            r"Copyright\s*©?\s*\d{4}",
            r"All\s+rights\s+reserved",
            r"Trademark\s*(notice)?",
            r"Legal\s*(notice|disclaimer)",
            r"Disclaimer",
        ]

        for pattern in legal_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # Remove timestamps and dates that appear alone
        date_patterns = [
            r"\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
            r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
            r"\b\d{4}-\d{2}-\d{2}\b",
            r"\d+\s+(minutes?|hours?|days?|weeks?|months?|years?)\s+ago",
            r"Updated?\s*:?\s*.*\d{4}",
            r"Published?\s*:?\s*.*\d{4}",
        ]

        for pattern in date_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # Remove standalone short lines (likely navigation/UI elements)
        lines = text.split("\n")
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Keep lines that are substantive (more than 3 words or longer than 30 chars)
            if len(stripped.split()) > 3 or len(stripped) > 30:
                cleaned_lines.append(stripped)
            elif stripped and len(stripped) > 10:
                # Check if it looks like a sentence
                if stripped[0].isupper() and stripped[-1] in ".!?":
                    cleaned_lines.append(stripped)

        text = "\n".join(cleaned_lines)

        # Final cleanup
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)

        return text.strip()

    def _generate_summary(self, text: str, sentences: int = 3) -> str:
        """Generate a simple summary by extracting first N sentences."""
        import re

        # Split into sentences
        sentences_list = re.split(r"(?<=[.!?])\s+", text)

        # Take first N sentences
        summary_sentences = sentences_list[:sentences]

        return " ".join(summary_sentences)


# Convenience functions for direct usage
async def stealth_search(
    page: Page,
    query: str,
    count: int = 10,
    page_num: int = 1,
    session_id: Optional[str] = None,
    manager=None,
) -> SearchResponse:
    """Convenience function to search.

    Args:
        page: Playwright page object (used if no session_id provided)
        query: Search query
        count: Number of results
        page_num: Page number for pagination (default: 1)
        session_id: Optional sub-agent session ID to use isolated browser
        manager: Optional SubAgentBrowserManager instance (required if session_id provided)

    Returns:
        SearchResponse object containing results and optional AI summary
    """
    if session_id and manager:
        # Use sub-agent browser
        browser_instance = await manager.get_or_create_browser(session_id)
        page = browser_instance.page
    # If no session_id, use the provided page (existing behavior)
    tools = StealthSearchTools(page)
    return await tools.search(query, count, page=page_num)


async def stealth_extract(
    page: Page, url: str, max_length: int = 5000, session_id: Optional[str] = None, manager=None
) -> ExtractedContent:
    """Convenience function to extract content.

    Args:
        page: Playwright page object (used if no session_id provided)
        url: URL to extract from
        max_length: Maximum content length
        session_id: Optional sub-agent session ID to use isolated browser
        manager: Optional SubAgentBrowserManager instance (required if session_id provided)

    Returns:
        ExtractedContent object
    """
    if session_id and manager:
        # Use sub-agent browser
        browser_instance = await manager.get_or_create_browser(session_id)
        page = browser_instance.page
    # If no session_id, use the provided page (existing behavior)
    tools = StealthSearchTools(page)
    return await tools.extract(url, max_length)


async def stealth_scrape(
    page: Page,
    url: str,
    include_images: bool = False,
    session_id: Optional[str] = None,
    manager=None,
) -> str:
    """Convenience function for deep scraping.

    Args:
        page: Playwright page object
        url: URL to scrape
        include_images: Whether to include images
        session_id: Optional session ID
        manager: Optional manager

    Returns:
        Markdown string
    """
    if session_id and manager:
        browser_instance = await manager.get_or_create_browser(session_id)
        page = browser_instance.page
    tools = StealthSearchTools(page)
    return await tools.scrape_page(url, include_images)
