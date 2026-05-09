import logging
import os
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from supabase import Client, create_client

load_dotenv()

logger = logging.getLogger(__name__)

_ZENDESK_BASE = "https://support.datatruck.io"
_ARTICLES_START = (
    f"{_ZENDESK_BASE}/api/v2/help_center/en-us/articles.json?per_page=100"
)
_EMBEDDING_MODEL = "text-embedding-3-small"
_TABLE = os.getenv("VECTOR_TABLE", "documents")


def _strip_html(html: str) -> str:
    return BeautifulSoup(html or "", "html.parser").get_text(separator="\n").strip()


def _fetch_all_articles() -> list[dict]:
    email = os.getenv("ZENDESK_EMAIL")
    token = os.getenv("ZENDESK_API_TOKEN")
    auth = (f"{email}/token", token) if email and token else None

    articles: list[dict] = []
    url: str | None = _ARTICLES_START

    while url:
        logger.info("GET %s", url)
        resp = requests.get(url, auth=auth, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        batch = payload.get("articles", [])
        articles.extend(batch)
        url = payload.get("next_page")
        logger.info("Fetched %d articles in batch (running total: %d)", len(batch), len(articles))

    logger.info("All pages fetched — total articles: %d", len(articles))
    return articles


def _embed(openai_client: OpenAI, text: str) -> list[float]:
    response = openai_client.embeddings.create(input=text, model=_EMBEDDING_MODEL)
    return response.data[0].embedding


def _upsert(supabase: Client, openai_client: OpenAI, article: dict) -> None:
    source_id = str(article["id"])
    title = (article.get("title") or "").strip()
    body = _strip_html(article.get("body") or "")
    content = f"TITLE: {title}\n\n{body}"

    logger.info("Embedding article %s — %s", source_id, title)
    embedding = _embed(openai_client, content)

    supabase.table(_TABLE).upsert(
        {
            "content": content,
            "embedding": embedding,
            "source_id": source_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="source_id",
    ).execute()

    logger.info("Upserted article %s — %s", source_id, title)


def sync_articles() -> None:
    logger.info("Starting Datatruck help-center sync")

    supabase: Client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )
    openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    articles = _fetch_all_articles()
    success = errors = 0

    for article in articles:
        try:
            _upsert(supabase, openai_client, article)
            success += 1
        except Exception:
            errors += 1
            logger.exception("Failed to upsert article id=%s", article.get("id"))

    logger.info("Sync finished — success: %d  errors: %d", success, errors)
