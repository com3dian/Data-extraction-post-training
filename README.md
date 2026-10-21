# Species Interaction Data Extraction

This project extracts Jantzen-standard ecological species interactions from research
papers. One paper can produce zero, one, or many interaction records. Each interaction is
validated with Pydantic and saved as one row in a CSV table.

## Environment setup with uv

The project requires Python 3.12 or newer and uses `uv` for dependency and environment
management.

```bash
uv sync
cp .env.example .env
```

`uv sync` creates `.venv`, installs the application and development dependencies, and uses
the committed `uv.lock` for reproducibility. Run commands with `uv run`; activating the
environment is optional.

Never commit `.env` or API keys.

## Download the Jantzen papers

The source inventory already contains `Paper ID`, DOI, publisher link, and full citation
columns. The downloader uses these to find publicly available PDFs through
[OpenAlex](https://help.openalex.org/api/get-single-entities/),
[Unpaywall](https://data.unpaywall.org/products/api),
[Semantic Scholar](https://api.semanticscholar.org/api-docs/), and
[Crossref](https://www.crossref.org/documentation/retrieve-metadata/rest-api/), followed by
the URL stored in the source CSV and the DOI resolver. If an institutional repository
redirects to a public Figshare article, it checks the article identity and tries its direct
PDF file URL. For papers with a verified author or repository PDF that is missing from
metadata services, add a row to `data/ready/jantzen_pdf_urls.csv` with `Paper ID`, matching
`Reference DOI`, and `PDF URL`. The checked URL is tried first. The file includes paper 17.

OpenAlex works without an account. Set a real contact email in `.env` to also use Unpaywall:

```dotenv
UNPAYWALL_EMAIL=your_email@example.org
# Optional; improves Semantic Scholar rate limits for a large batch.
SEMANTIC_SCHOLAR_API_KEY=
```

Preview the batch without making network requests:

```bash
uv run download-papers --dry-run
```

Try five papers first, then run the full list:

```bash
uv run download-papers --limit 5
uv run download-papers
```

To retry one paper after adding a verified URL:

```bash
uv run download-papers --paper-id 17
```

The equivalent standalone script is:

```bash
uv run python scripts/download_papers.py --limit 5
```

PDFs are saved under `data/papers/jantzen/`. After each paper, the downloader atomically
updates `outputs/paper_downloads/download_status.csv` and
`outputs/paper_downloads/not_downloaded.csv`. It checks the PDF file signature and rejects
HTML login/error pages even if the server labels them as a PDF. Existing valid PDFs are
skipped on rerun; pass `--overwrite` only when you want to fetch them again.

The downloader only uses links made available by the source table and scholarly metadata
services; it does not bypass publisher access controls. Papers that need institutional or
manual access remain in `not_downloaded.csv` with the attempted URLs and errors.
If you obtain one through a browser or library account, save it as
`data/papers/jantzen/paper_<Paper ID>.pdf` (for example, `paper_14.pdf`). On the next run,
the downloader checks the file, marks it as already downloaded, and removes it from
`not_downloaded.csv`.

For an interactive run, open
[`notebooks/02-download-jantzen-papers.ipynb`](notebooks/02-download-jantzen-papers.ipynb).
Its default `LIMIT = 5` provides a small trial; change it to `None` for all selected papers.

## Providers and models

The CLI supports two OpenAI-compatible providers.

### CLI Proxy

CLI Proxy is used to access OpenAI models. Configure:

```dotenv
LLM_PROVIDER=cliproxy
LLM_MODEL=gpt6luna
CLIPROXY_API_KEY=...
CLIPROXY_API_BASE=https://cliproxy.sub2api-best.com/v1
```

Built-in aliases:

- `gpt6luna` -> `gpt-6-luna`
- `gpt56luna` -> `gpt-5.6-luna`

### SURF Willma

Configure:

```dotenv
LLM_PROVIDER=surf
LLM_MODEL=oss120b
SURF_API_KEY=...
SURF_API_BASE=https://willma.surf.nl/api/v0
```

Built-in aliases:

- `oss120b` -> `openai/gpt-oss-120b`
- `qwen35b` -> `Qwen/Qwen3.6-35B-A3B-FP8`
- `gemma4` -> `RedHatAI/gemma-4-31B-it-NVFP4`

You can pass a full provider model ID instead of an alias. SURF requests include the
required `X-API-KEY` header. Provider availability can change; a listed alias does not prove
that the remote model is currently loaded.

## Extract MinerU output

PDF parsing is deliberately not implemented in this repository. Process the downloaded
PDFs with MinerU on the server, copy the resulting Markdown or plain-text files back, and
give those files (or their directory) to the extraction command.

First inspect the selected files without making an API request:

```bash
uv run extract-papers data/mineru --recursive --dry-run
```

Run with CLI Proxy:

```bash
uv run extract-papers data/mineru \
  --recursive \
  --provider cliproxy \
  --model gpt6luna \
  --output-dir outputs/cliproxy-gpt6luna
```

Run with SURF:

```bash
uv run extract-papers data/mineru \
  --recursive \
  --provider surf \
  --model oss120b \
  --output-dir outputs/surf-oss120b
```

Strict JSON Schema output is used by default. This follows OpenAI's
[Structured Outputs guidance](https://developers.openai.com/api/docs/guides/structured-outputs):
the Pydantic model is sent as the response schema and the returned object is validated
locally. If an OpenAI-compatible provider does not implement strict JSON Schema, use
`--response-mode json_object`; local Pydantic validation still applies.

The complete paper text is sent in one request. The pipeline never silently truncates a
paper. Use `--max-paper-chars N` to fail explicitly when a paper exceeds a limit selected
for a provider/model context window.

## Output layout

Each run directory contains:

```text
outputs/<run>/
├── config.json              # Non-secret provider and run settings
├── records.csv              # Combined table; one row per interaction
├── run_status.csv           # One status row per paper
├── by_paper/
│   └── <paper-id>.csv       # Per-paper table checkpoint
└── raw/
    └── <paper-id>.json      # Validated structured result
```

Per-paper JSON and CSV files are written atomically. Re-running the same command skips
completed papers and rebuilds `records.csv` from the checkpoints. Use `--overwrite` to
extract them again. Failed papers remain visible in `run_status.csv` and do not erase
successful outputs.

The combined table includes paper provenance plus the fields extracted from paper content:

- evidence type;
- source taxon, directional interaction type, and target taxon;
- target part and interaction-specific occurrence period;
- study locality, reported coordinates, and observation years;
- paper-supported remarks.

Taxonomic acceptance, GBIF IDs, ontology IRIs, DOI bookkeeping, and internal paper IDs are
deliberately left for later enrichment rather than inferred by the LLM.

## Development

```bash
uv run pytest
uv run ruff check .
```
