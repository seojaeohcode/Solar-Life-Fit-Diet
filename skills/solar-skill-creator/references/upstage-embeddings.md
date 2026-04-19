# Upstage Embeddings

Verified on: 2026-04-19

## What it does

Converts text strings into fixed-length 4096-dimensional float vectors that encode semantic meaning, enabling similarity comparisons, nearest-neighbor search, clustering, and retrieval-augmented generation (RAG). Outputs are L2-normalized (magnitude 1), so dot product equals cosine similarity. Returns one embedding vector per input string.

## When to choose this over related capabilities

- **Chat (Solar LLM)** → generates text responses; choose Embeddings when you need to measure similarity or build a retrieval index, not when you need a generated answer.
- **Document Parse** → extracts structured layout + text from PDFs and scanned images; use Document Parse first, then embed the extracted chunks with this API downstream.
- **Document OCR** → extracts raw text and word bounding boxes from document images; embed the OCR'd text downstream with this API.
- **Information Extract (Universal)** → pulls named fields from a document against a JSON schema (invoice totals, contract clauses); choose that when the fields are fixed and known up front — use Embeddings when you need open-ended similarity or the label set is dynamic.
- **Document Classification** → buckets a document into predefined labels; Embeddings + nearest-neighbor is a DIY alternative when labels are not fixed in advance or you need per-chunk granularity.

Use Embeddings to power RAG retrieval, deduplication, semantic search, and similarity-based recommendation. Canonical pipeline: parse the document with Document Parse, chunk by section, embed each chunk with `embedding-passage`, store vectors with metadata, then at query time embed the user's question with `embedding-query` and retrieve the nearest chunks before passing them to Chat (Solar LLM).

## Constraints checklist

- Max file size / pages / DPI: N/A — text-based API
- Max tokens (input): ≤ 204,800 tokens total per request; recommended ≤ 512 tokens per individual string for best retrieval quality
- Max batch size: 100 strings per request
- Rate limits / quota: 100 requests/min (RPM), 300,000 tokens/min (TPM) per model alias
- Language / locale support: English, Korean, Japanese (Korean and English are primary emphasis)
- Embedding dimensions: fixed at 4096 — not selectable
- Query-vs-passage: **two separate model aliases** — `embedding-query` for user queries, `embedding-passage` for corpus documents — both share the same vector space but are trained asymmetrically

## Supported formats

- Input: a single UTF-8 string or a JSON array of up to 100 UTF-8 strings
- Output: array of float32 vectors, each of length 4096, L2-normalized (magnitude 1); one vector per input string

## Authentication

Set the environment variable `UPSTAGE_API_KEY` and pass it as a Bearer token:

```bash
Authorization: Bearer $UPSTAGE_API_KEY
```

The API is OpenAI-SDK-compatible; set `base_url="https://api.upstage.ai/v1"`.

## API format

**Endpoint**: `POST https://api.upstage.ai/v1/embeddings`

**Request**:
```json
{
  "model": "embedding-passage",
  "input": "Upstage builds state-of-the-art language models for enterprise use."
}
```

Batch variant (array input):
```json
{
  "model": "embedding-passage",
  "input": [
    "First document chunk.",
    "Second document chunk.",
    "Third document chunk."
  ]
}
```

**Response**:
```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "index": 0,
      "embedding": [0.01850688, -0.0066606696, "...4096 floats total..."]
    }
  ],
  "model": "embedding-passage",
  "usage": {
    "prompt_tokens": 12,
    "total_tokens": 12
  }
}
```

**Curl example** — embed a single passage:
```bash
curl -X POST https://api.upstage.ai/v1/embeddings \
  -H "Authorization: Bearer $UPSTAGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "embedding-passage",
    "input": "Solar is a powerful language model built by Upstage."
  }'
```

**Curl example** — embed a user query:
```bash
curl -X POST https://api.upstage.ai/v1/embeddings \
  -H "Authorization: Bearer $UPSTAGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "embedding-query",
    "input": "What language models does Upstage offer?"
  }'
```

**Python example** — build an index then query it:
```python
import os
import numpy as np
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["UPSTAGE_API_KEY"],
    base_url="https://api.upstage.ai/v1",
)

# Index time: embed documents with the PASSAGE alias
documents = [
    "Solar Pro 3 is Upstage's flagship 102B MoE model.",
    "Upstage Document Parse extracts text with layout awareness.",
    "Solar Embedding supports English, Korean, and Japanese.",
]
passage_resp = client.embeddings.create(model="embedding-passage", input=documents)
doc_vectors = np.array([item.embedding for item in passage_resp.data])

# Query time: embed the user's question with the QUERY alias
query = "Which languages does the embedding model support?"
query_resp = client.embeddings.create(model="embedding-query", input=query)
query_vector = np.array(query_resp.data[0].embedding)

# Dot product == cosine similarity because vectors are L2-normalized
scores = doc_vectors @ query_vector
best_idx = int(np.argmax(scores))
print(f"Best match: {documents[best_idx]}")
```

## Parameters

| Name | Required | Default | Description |
|---|---|---|---|
| `model` | yes | — | `embedding-query` (alias for `solar-embedding-1-large-query`) for user search strings; `embedding-passage` (alias for `solar-embedding-1-large-passage`) for corpus documents |
| `input` | yes | — | A single string or an array of up to 100 strings to embed |

No other parameters are documented. Similarity metric: dot product on the normalized output vectors equals cosine similarity; Euclidean distance is also valid.

## Caveats and gotchas

**Query alias vs. passage alias — the highest-leverage gotcha.** Upstage exposes two model aliases that share the same 4096-dimensional vector space but are trained asymmetrically for their respective roles:

| Scenario | Model alias to use | Full model name |
|---|---|---|
| Embedding document chunks into the index | `embedding-passage` | `solar-embedding-1-large-passage` |
| Embedding the user's search query at retrieval time | `embedding-query` | `solar-embedding-1-large-query` |

Mixing the aliases (e.g., indexing with `embedding-query`, querying with `embedding-passage`) produces numerically valid vectors but silently degrades recall — the asymmetric training means the models are calibrated to work as a matched pair, not interchangeably. Example correct workflow:

```python
# BUILD the index — always passage alias
passage_vec = client.embeddings.create(
    model="embedding-passage",
    input="The Solar API base URL is https://api.upstage.ai/v1",
).data[0].embedding

# SEARCH the index — always query alias
query_vec = client.embeddings.create(
    model="embedding-query",
    input="What is the Solar API base URL?",
).data[0].embedding
```

**Token budget per request.** Total tokens across all strings in a single request must be ≤ 204,800, with up to 100 strings per call. Individual strings exceeding their natural token length may be truncated. For best retrieval quality, keep individual chunks ≤ 512 tokens; split on paragraph or section boundaries before embedding.

**Batching for throughput.** Send multiple strings in a single `input` array rather than looping with one call per string — reduces latency and round-trip overhead. For large document sets, split into batches of ≤ 100 strings yourself:

```python
def embed_in_batches(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    all_vectors = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(model="embedding-passage", input=batch)
        all_vectors.extend([item.embedding for item in resp.data])
    return all_vectors
```

**LangChain / LlamaIndex integration note.** When using `langchain-upstage` or `llama-index-embeddings-upstage`, pass `solar-embedding-1-large` as the model string (without alias suffix) — those libraries route to the correct alias internally via `embed_query()` vs. `embed_documents()`. When calling the REST API directly, always specify the full alias (`embedding-query` or `embedding-passage`).

**Dot product shortcut.** Because output vectors are L2-normalized, `np.dot(q, p)` is numerically equivalent to cosine similarity — no need to normalize manually before computing scores.
