import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI as _OpenAI
from supabase import Client, create_client

_openai_client = _OpenAI(api_key=os.environ["OPENAI_API_KEY"])

logger = logging.getLogger(__name__)

# Words that add no discriminative value — excluded from keyword extraction
_STOPWORDS = {
    # English function / question words
    "the", "is", "in", "on", "at", "to", "for", "of", "and", "or", "a", "an",
    "with", "this", "that", "are", "was", "were", "been", "have", "has", "had",
    "its", "from", "will", "would", "could", "should", "does", "did", "can",
    "how", "what", "when", "where", "why", "who", "which",
    # Uzbek/Russian common words
    "bu", "va", "yoki", "da", "ga", "ni", "men", "sen", "biz", "ham",
}

# How many keywords must hit the same document before we trust the match.
# Applied only when the query has 3 or more significant keywords.
_MIN_KEYWORD_HITS = 2


@dataclass
class SearchResult:
    content: str   # full document text (caller decides how to display)
    title: str     # extracted from the embedded "TITLE: ..." line (for logging)
    match_type: str  # exact_title | keyword_title | keyword_content | no_match


class SearchService:
    """
    Searches a Supabase table where every row's content column starts with:

        TITLE: <article title>

        <body text …>

    Search priority:
        A. Full query found in the embedded title  (exact_title)
        B. Multiple keywords found in the embedded title (keyword_title)
        C. Multiple keywords found anywhere in content (keyword_content)
    """

    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
        table: str = "documents",
        content_column: str = "content",
    ) -> None:
        self._supabase: Client = create_client(supabase_url, supabase_key)
        self._table = table
        self._col = content_column

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def search(self, query: str) -> Optional[SearchResult]:
        logger.info("Search started | query: %.100s", query)

        result = self._exact_title(query)
        if result and self._is_relevant(query, result.content):
            return result

        keywords = self._extract_keywords(query)

        result = self._keyword_title(keywords, query)
        if result and self._is_relevant(query, result.content):
            return result

        result = self._keyword_content(keywords, query)
        if result and self._is_relevant(query, result.content):
            return result

        logger.info("Match type: no_match | query: %.100s", query)
        return None

    def _is_relevant(self, query: str, content: str) -> bool:
        response = _openai_client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=5,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f'User asked: "{query}"\n\n'
                        f"Found article:\n{content[:500]}\n\n"
                        "Does this article directly answer the user's question? Reply only \"yes\" or \"no\"."
                    ),
                }
            ],
        )
        answer = response.choices[0].message.content.strip().lower()
        return answer.startswith("yes")

    # ------------------------------------------------------------------ #
    # Search steps                                                         #
    # ------------------------------------------------------------------ #

    def _exact_title(self, query: str) -> Optional[SearchResult]:
        """
        Search for the full query string inside the embedded TITLE line.

        PostgREST filter sent:  content=ilike.TITLE: *<query>*

        Anchoring without a leading * means the string must START with
        'TITLE: ' — which all documents in this format do — so this is
        effectively a title-only substring match.
        """
        clean = query.strip().rstrip("?!. ")
        pattern = f"TITLE: *{clean}*"
        try:
            rows = self._ilike(pattern, limit=1)
            if rows:
                content = rows[0][self._col]
                title = self._parse_title(content)
                logger.info("Match type: exact_title | title: %s", title)
                return SearchResult(content=content, title=title, match_type="exact_title")
        except Exception as exc:
            logger.error(
                "Exact title search failed | filter: %s=ilike.%s | error: %s",
                self._col, pattern, exc,
            )
        return None

    def _keyword_title(self, keywords: list[str], query: str) -> Optional[SearchResult]:
        """
        Score documents by how many keywords appear on the TITLE line.

        PostgREST filter per keyword:  content=ilike.TITLE: *<keyword>*

        Same anchor trick: no leading * forces 'TITLE: ' to be at the start,
        so only the title section is matched against each keyword.
        """
        hits: dict[str, tuple[dict, int]] = {}

        for kw in keywords:
            pattern = f"TITLE: *{kw}*"
            try:
                for row in self._ilike(pattern):
                    key = self._parse_title(row[self._col])
                    prev, count = hits.get(key, (row, 0))
                    hits[key] = (prev, count + 1)
            except Exception as exc:
                logger.error(
                    "Keyword title search failed | keyword: %r | filter: %s=ilike.%s | error: %s",
                    kw, self._col, pattern, exc,
                )

        return self._best_hit(hits, keywords, "keyword_title")

    def _keyword_content(self, keywords: list[str], query: str) -> Optional[SearchResult]:
        """
        Score documents by how many keywords appear anywhere in the content.

        PostgREST filter per keyword:  content=ilike.*<keyword>*
        """
        hits: dict[str, tuple[dict, int]] = {}

        for kw in keywords:
            pattern = f"*{kw}*"
            try:
                for row in self._ilike(pattern):
                    key = self._parse_title(row[self._col])
                    prev, count = hits.get(key, (row, 0))
                    hits[key] = (prev, count + 1)
            except Exception as exc:
                logger.error(
                    "Keyword content search failed | keyword: %r | filter: %s=ilike.%s | error: %s",
                    kw, self._col, pattern, exc,
                )

        return self._best_hit(hits, keywords, "keyword_content")

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _ilike(self, pattern: str, limit: int = 5) -> list[dict]:
        logger.debug("PostgREST filter | %s=ilike.%s", self._col, pattern)
        result = (
            self._supabase
            .table(self._table)
            .select(self._col)
            .ilike(self._col, pattern)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def _best_hit(
        self,
        hits: dict[str, tuple[dict, int]],
        keywords: list[str],
        match_type: str,
    ) -> Optional[SearchResult]:
        if not hits:
            return None

        best_row, best_count = max(hits.values(), key=lambda x: x[1])
        min_required = _MIN_KEYWORD_HITS if len(keywords) >= 3 else 1

        if best_count < min_required:
            logger.info(
                "Confidence too low | match_type: %s | keywords matched: %d/%d (need %d)",
                match_type, best_count, len(keywords), min_required,
            )
            return None

        content = best_row[self._col]
        title = self._parse_title(content)
        logger.info(
            "Match type: %s | title: %s | keywords matched: %d/%d",
            match_type, title, best_count, len(keywords),
        )
        return SearchResult(content=content, title=title, match_type=match_type)

    @staticmethod
    def _parse_title(content: str) -> str:
        """Extract title from the first line: 'TITLE: Some Title' → 'Some Title'."""
        m = re.match(r"TITLE:\s*(.+)", content.strip(), re.IGNORECASE)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        words = re.findall(r"\w+", text.lower())
        filtered = [w for w in words if len(w) > 3 and w not in _STOPWORDS]
        return filtered if filtered else [w for w in words if len(w) > 2]
