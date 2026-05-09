# Datatruck Help-Center Sync Service

Fetches all articles from the Datatruck Zendesk help center and upserts them
into the Supabase `documents` table with OpenAI embeddings.  
Runs immediately on start, then repeats every **2 hours**.

---

## 1 — Supabase schema setup

Run the following SQL once in the Supabase SQL editor before starting the service:

```sql
-- Track the Zendesk article ID so rows can be upserted without duplicates
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_id TEXT UNIQUE;

-- Record when each row was last synced
ALTER TABLE documents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

-- Embedding column for OpenAI text-embedding-3-small (1536 dimensions)
-- Skip this line if the column already exists with the correct dimension.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding vector(1536);
```

> **Note:** `text-embedding-3-small` produces **1536-dimensional** vectors.
> If your existing `embedding` column was created for a different model
> (e.g. `all-MiniLM-L6-v2` → 384 dims) you will need to drop and recreate it:
> ```sql
> ALTER TABLE documents DROP COLUMN embedding;
> ALTER TABLE documents ADD COLUMN embedding vector(1536);
> ```

---

## 2 — Environment variables

Add the following keys to the existing `.env` file:

```dotenv
OPENAI_API_KEY=sk-...

# Optional — only needed for private / authenticated help centers
ZENDESK_EMAIL=you@example.com
ZENDESK_API_TOKEN=your_zendesk_api_token
```

The existing keys (`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `VECTOR_TABLE`) are
reused automatically.

---

## 3 — Install dependencies

```bash
pip install -r requirements_sync.txt
```

---

## 4 — Run the sync service

```bash
python sync_runner.py
```

The service will:
1. Sync all articles immediately on startup.
2. Re-sync every 2 hours automatically.
3. Log every step to stdout; exceptions are caught so the loop never crashes.

---

## Files created

| File | Purpose |
|---|---|
| `services/sync_articles.py` | Core sync logic (fetch → embed → upsert) |
| `sync_runner.py` | Scheduler entry point |
| `requirements_sync.txt` | Python dependencies for the sync service |

Files **not touched**: `bot.py`, `config.py`, `handlers/`, `services/vector_search.py`
