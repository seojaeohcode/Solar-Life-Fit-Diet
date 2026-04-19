# Upstage Document Parse

Verified on: 2026-04-19

## What it does
Layout-aware extraction of text AND structure (headings, paragraphs, tables, lists, figures, charts) from PDFs and document images, returning a hierarchical `elements[]` array plus rolled-up `content.html` / `content.markdown` / `content.text` fields that the agent can navigate or pipe directly into downstream steps. OCR is applied automatically for scanned sources, so Parse is the single entry point whenever you need document body with structure — not just raw characters.

## When to choose this over related capabilities
Use Parse when you need the document body with structure (e.g., reconstruct a PDF as Markdown, extract a table while preserving its cell layout, feed structured chunks into a RAG pipeline).

- **Chat (Solar LLM)** → text generation and reasoning; has no document-perception capability.
- **Document OCR** → raw text + word-level bounding boxes from scans or handwriting; no heading/table/paragraph structure. Choose OCR when you only need positional character output and layout does not matter.
- **Information Extract (Universal)** → schema-driven named-field extraction (e.g., pull `invoice_total`, `vendor_name`); returns only the fields you specify. If you need the full document body first, pipe Parse → Information Extract.
- **Document Classification** → buckets a document into a predefined category (invoice / contract / receipt); returns a label, not content.
- **Embeddings** → vectorizes text for semantic search or similarity; requires text input, not documents.

Concrete decision rule: "Use Parse when you need the document body with structure. For raw text from a phone photo, use OCR. To pull specific named fields, pipe Parse → Information Extract."

## Constraints checklist
- Max file size: 50 MB
- Max pages: 100 pages per request
- Max pixels per page: 200,000,000 pixels at 150 DPI
- Max tokens (input/output): N/A — file-based upload; no token limit applies
- Rate limits: Sync 1 RPS, Async 2 RPS (per model alias); see console quota page for account-level limits
- Language / locale support: Alphanumeric scripts, Hangul, Hanja supported; Hanzi/Kanji in beta — confirm current status against docs
- Other hard limits: `base64_encoding` crops are returned per element type requested; async timeout not specified in docs

## Supported formats
- Input: PDF, JPEG, PNG, BMP, TIFF, HEIC, DOCX, PPTX, XLSX, HWP, HWPX
- Output (`content` and per-element `content`): `html`, `markdown`, `text` — controlled by which fields are populated in the response (all three are always present; unused ones are empty strings). The `output_formats` parameter is not documented for this endpoint — request the format you need by consuming the corresponding field in the response.

## Authentication
Set the environment variable `UPSTAGE_API_KEY` to your Upstage API key. Pass it as a Bearer token:

```
Authorization: Bearer $UPSTAGE_API_KEY
```

Example (shell):
```bash
export UPSTAGE_API_KEY="up-..."
```

## API format
**Endpoint**: `POST https://api.upstage.ai/v1/document-digitization`

This endpoint is shared with Document OCR — the `model` form field selects which capability runs.

**Request**:
```bash
# multipart/form-data — send the document as a file part
```

**Response**:
```json
{
  "api": "2.0",
  "content": {
    "html": "<h1 id='0'>INVOICE</h1><p id='1'>...</p>",
    "markdown": "# INVOICE\n\n...",
    "text": "INVOICE\n..."
  },
  "elements": [
    {
      "id": 0,
      "page": 1,
      "category": "heading1",
      "content": {
        "html": "<h1 id='0'>INVOICE</h1>",
        "markdown": "# INVOICE",
        "text": "INVOICE"
      },
      "coordinates": [
        {"x": 0.06, "y": 0.05},
        {"x": 0.24, "y": 0.05},
        {"x": 0.24, "y": 0.10},
        {"x": 0.06, "y": 0.10}
      ]
    }
  ],
  "model": "document-parse-260128",
  "usage": {"pages": 1}
}
```

Coordinates are normalized to `[0, 1]` relative to page dimensions (top-left origin). Known `category` values include: `heading1`, `paragraph`, `list`, `table`, `figure`, `chart` — full taxonomy unverified; confirm against "Understanding output" docs page.

**Curl example**:
```bash
curl -X POST https://api.upstage.ai/v1/document-digitization \
  -H "Authorization: Bearer $UPSTAGE_API_KEY" \
  -F "document=@invoice.pdf" \
  -F "model=document-parse" \
  -F "ocr=force"
```

## Parameters
| Name | Required | Default | Description |
|---|---|---|---|
| `document` | yes | — | The document file (multipart file part). Accepts PDF, JPEG, PNG, BMP, TIFF, HEIC, DOCX, PPTX, XLSX, HWP, HWPX. |
| `model` | yes | — | Model alias. Use `document-parse` (points to `document-parse-260128`, 1 RPS sync / 2 RPS async) or `document-parse-nightly` for the latest nightly build. |
| `ocr` | no | auto | Set to `"force"` to run OCR even on digital-born (text-layer) PDFs. Omit or leave blank to let the model decide. |
| `base64_encoding` | no | — | JSON-style list of element category strings (e.g., `"['table']"`, `"['figure','chart']"`) for which the response should include a base64-encoded image crop of each matched element. |

## Caveats and gotchas

**When the source is a scanned image or a PDF without a text layer**, pass `ocr='force'` so the model runs full OCR rather than attempting to lift the (absent) text layer directly:
```bash
curl -X POST https://api.upstage.ai/v1/document-digitization \
  -H "Authorization: Bearer $UPSTAGE_API_KEY" \
  -F "document=@scanned_contract.pdf" \
  -F "model=document-parse" \
  -F "ocr=force"
```

**When extracting tables**, consume `content.html` or `content.markdown` — the `content.text` field flattens all cells into a single string and loses column/row boundaries entirely.

**When you need image crops of figures or tables** (e.g., to feed into a vision model), set `base64_encoding` to include the element type(s) you need:
```python
data={
    "model": "document-parse",
    "base64_encoding": "['table', 'figure']",
}
```
Each matched element in `elements[]` will then carry a `base64_encoding` field with the PNG crop.

**When building a RAG pipeline**, use `content.html` as the canonical representation, chunk by iterating `elements[]` (each element has its own `content` and `coordinates`), then embed each chunk with `embedding-passage` (see `upstage-embeddings.md`). Chunking at the element level preserves semantic boundaries better than fixed-token splitting.

**When the document exceeds sync throughput (1 RPS)**, use the Async API which allows 2 RPS — endpoint path not fully verified in available docs; confirm against the "Handling large documents" page in the Upstage console.

**Python drop-in example**:
```python
import os, requests

def parse_document(file_path: str, force_ocr: bool = False) -> dict:
    with open(file_path, "rb") as f:
        form_data = {"model": "document-parse"}
        if force_ocr:
            form_data["ocr"] = "force"
        resp = requests.post(
            "https://api.upstage.ai/v1/document-digitization",
            headers={"Authorization": f"Bearer {os.environ['UPSTAGE_API_KEY']}"},
            files={"document": f},
            data=form_data,
        )
    resp.raise_for_status()
    return resp.json()

# Access structured output
result = parse_document("report.pdf", force_ocr=True)
full_html   = result["content"]["html"]       # full document as HTML
full_md     = result["content"]["markdown"]   # full document as Markdown
elements    = result["elements"]              # list of structural elements with coordinates
pages_billed = result["usage"]["pages"]
```
