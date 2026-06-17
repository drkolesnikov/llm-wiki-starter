"""
Tests for tools/source-ingest/web/crawler.py — issue #29.

No real network is used.  A fixture link graph is embedded and served via an
injected fetcher callable.
"""

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CRAWLER_PATH = ROOT / "tools" / "source-ingest" / "web" / "crawler.py"


def load_crawler_module():
    spec = importlib.util.spec_from_file_location("crawler", CRAWLER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


crawler_mod = load_crawler_module()
CrawlSpec = crawler_mod.CrawlSpec
crawl = crawler_mod.crawl


# ---------------------------------------------------------------------------
# Fixture link graph
#
#   allowed host: example.com  (allowed path prefix: /docs/)
#   disallowed host: other.com
#   disallowed path on allowed host: /private/secret
#
#   Graph (depth → URLs):
#     0  https://example.com/docs/
#            links to:
#              https://example.com/docs/page1  (depth 1)
#              https://example.com/docs/page2  (depth 1)
#              https://other.com/docs/page     (depth 1, wrong host)
#              https://example.com/private/secret  (depth 1, wrong path)
#     1  https://example.com/docs/page1
#            links to:
#              https://example.com/docs/deep   (depth 2)
#     1  https://example.com/docs/page2
#            links to nothing extra
#     2  https://example.com/docs/deep
#            links to nothing
# ---------------------------------------------------------------------------

GRAPH: dict[str, str] = {
    "https://example.com/docs/": (
        '<html><body>'
        '<a href="/docs/page1">page1</a>'
        '<a href="/docs/page2">page2</a>'
        '<a href="https://other.com/docs/page">other</a>'
        '<a href="/private/secret">secret</a>'
        '</body></html>'
    ),
    "https://example.com/docs/page1": (
        '<html><body>'
        '<a href="/docs/deep">deep</a>'
        '</body></html>'
    ),
    "https://example.com/docs/page2": "<html><body><p>nothing</p></body></html>",
    "https://example.com/docs/deep": "<html><body><p>leaf</p></body></html>",
    "https://other.com/docs/page": "<html><body><p>other</p></body></html>",
    "https://example.com/private/secret": "<html><body><p>secret</p></body></html>",
}


class FetchTracker:
    """Counts how many times each URL was requested."""

    def __init__(self):
        self.call_count: dict[str, int] = {}

    def fetch(self, url: str) -> str:
        self.call_count[url] = self.call_count.get(url, 0) + 1
        if url not in GRAPH:
            raise KeyError(f"Fixture has no entry for {url!r}")
        return GRAPH[url]


def make_spec(**overrides) -> CrawlSpec:
    defaults = dict(
        seed_urls=["https://example.com/docs/"],
        allowed_hosts=["example.com"],
        path_prefixes=["/docs/"],
        max_depth=3,
        max_pages=100,
    )
    defaults.update(overrides)
    return CrawlSpec(**defaults)


class TestAllowedHostEnforcement(unittest.TestCase):
    def test_only_allowed_host_urls_are_fetched(self):
        tracker = FetchTracker()
        result = crawl(make_spec(), tracker.fetch)

        fetched_hosts = {__import__("urllib.parse", fromlist=["urlparse"]).urlparse(p.url).netloc
                        for p in result.fetched}
        self.assertNotIn("other.com", fetched_hosts,
                         "other.com must never be fetched")

    def test_disallowed_host_url_appears_in_skipped(self):
        tracker = FetchTracker()
        result = crawl(make_spec(), tracker.fetch)

        skipped_urls = {url for url, _ in result.skipped}
        self.assertIn("https://other.com/docs/page", skipped_urls)

    def test_disallowed_host_skip_reason(self):
        tracker = FetchTracker()
        result = crawl(make_spec(), tracker.fetch)

        reason_map = {url: reason for url, reason in result.skipped}
        self.assertEqual("host_not_allowed",
                         reason_map.get("https://other.com/docs/page"))


class TestPathPrefixEnforcement(unittest.TestCase):
    def test_only_allowed_path_urls_are_fetched(self):
        tracker = FetchTracker()
        result = crawl(make_spec(), tracker.fetch)

        for page in result.fetched:
            path = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(page.url).path
            self.assertTrue(
                path.startswith("/docs/"),
                f"{page.url!r} has path {path!r} which is not under /docs/",
            )

    def test_disallowed_path_url_appears_in_skipped(self):
        tracker = FetchTracker()
        result = crawl(make_spec(), tracker.fetch)

        skipped_urls = {url for url, _ in result.skipped}
        self.assertIn("https://example.com/private/secret", skipped_urls)

    def test_disallowed_path_skip_reason(self):
        tracker = FetchTracker()
        result = crawl(make_spec(), tracker.fetch)

        reason_map = {url: reason for url, reason in result.skipped}
        self.assertEqual("path_not_allowed",
                         reason_map.get("https://example.com/private/secret"))


class TestDepthEnforcement(unittest.TestCase):
    def test_depth_never_exceeds_max_depth(self):
        max_depth = 1
        tracker = FetchTracker()
        result = crawl(make_spec(max_depth=max_depth), tracker.fetch)

        for page in result.fetched:
            self.assertLessEqual(
                page.depth, max_depth,
                f"Page {page.url!r} fetched at depth {page.depth} > {max_depth}",
            )

    def test_depth_limited_crawl_skips_deep_urls(self):
        """With max_depth=1 the /docs/deep page must NOT be fetched."""
        tracker = FetchTracker()
        result = crawl(make_spec(max_depth=1), tracker.fetch)

        fetched_urls = {p.url for p in result.fetched}
        self.assertNotIn("https://example.com/docs/deep", fetched_urls)

    def test_deep_url_is_reachable_at_sufficient_depth(self):
        """With max_depth=2 the /docs/deep page IS reachable."""
        tracker = FetchTracker()
        result = crawl(make_spec(max_depth=2), tracker.fetch)

        fetched_urls = {p.url for p in result.fetched}
        self.assertIn("https://example.com/docs/deep", fetched_urls)


class TestPageBudget(unittest.TestCase):
    def test_crawl_halts_at_max_pages(self):
        max_pages = 2
        tracker = FetchTracker()
        result = crawl(make_spec(max_pages=max_pages), tracker.fetch)

        self.assertLessEqual(len(result.fetched), max_pages)

    def test_stopped_reason_is_page_budget(self):
        tracker = FetchTracker()
        result = crawl(make_spec(max_pages=2), tracker.fetch)

        self.assertEqual("page_budget", result.stopped_reason)

    def test_no_stopped_reason_when_budget_not_exhausted(self):
        tracker = FetchTracker()
        result = crawl(make_spec(max_pages=100), tracker.fetch)

        self.assertIsNone(result.stopped_reason)


class TestVisitedSet(unittest.TestCase):
    def test_no_url_is_fetched_twice(self):
        tracker = FetchTracker()
        crawl(make_spec(), tracker.fetch)

        for url, count in tracker.call_count.items():
            self.assertEqual(1, count, f"{url!r} was fetched {count} times")

    def test_seed_already_linked_from_graph_not_re_fetched(self):
        """If a page links back to the seed the seed is not fetched again."""
        graph_with_cycle = {
            **GRAPH,
            # page1 now also links back to the seed
            "https://example.com/docs/page1": (
                '<a href="/docs/">back</a>'
                '<a href="/docs/deep">deep</a>'
            ),
        }
        tracker = FetchTracker()

        def cyclic_fetch(url: str) -> str:
            tracker.call_count[url] = tracker.call_count.get(url, 0) + 1
            return graph_with_cycle[url]

        crawl(make_spec(), cyclic_fetch)
        self.assertEqual(1, tracker.call_count.get("https://example.com/docs/", 0))


class TestOffConstraintUrlsNeverFetched(unittest.TestCase):
    def test_skipped_urls_are_never_fetched(self):
        tracker = FetchTracker()
        result = crawl(make_spec(), tracker.fetch)

        skipped_urls = {url for url, _ in result.skipped}
        for url in skipped_urls:
            self.assertNotIn(url, tracker.call_count,
                             f"Skipped URL {url!r} must not have been fetched")


if __name__ == "__main__":
    unittest.main()
