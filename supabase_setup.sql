-- Enable the pgvector extension
create extension if not exists vector;

-- Knowledge base table
-- 384 dimensions matches all-MiniLM-L6-v2 (sentence-transformers default)
create table if not exists documents (
    id        bigserial primary key,
    content   text    not null,
    metadata  jsonb   default '{}',
    embedding vector(384)
);

-- Similarity search function called by VectorSearchService
create or replace function match_documents(
    query_embedding  vector(384),
    match_threshold  float,
    match_count      int
)
returns table (
    id          bigint,
    content     text,
    metadata    jsonb,
    similarity  float
)
language sql stable
as $$
    select
        id,
        content,
        metadata,
        1 - (embedding <=> query_embedding) as similarity
    from documents
    where 1 - (embedding <=> query_embedding) > match_threshold
    order by embedding <=> query_embedding
    limit match_count;
$$;

-- Index for fast ANN search
create index if not exists documents_embedding_idx
    on documents using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);
