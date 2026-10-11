# Australian government information assistant

This repository contains the locally run application and its test code. The interface uses HTML, CSS and JavaScript. A Python FastAPI service routes questions, searches short source notes with SQLite FTS5 and can ask a locally running, pretrained Qwen3 4B model through Ollama to summarise the retrieved notes. The model was not fine-tuned for this project. The API checks generated citations, dates and route details, and can return a labelled source extract when generation is unavailable or rejected.

The assistant covers selected Australian tax and visa information. It is an academic information tool, **not an official government service or a source of personal advice**. The bundled notes are indexed project material; an active note does not imply that a government agency or named reviewer has approved its wording. Check linked official pages for current rules before using or demonstrating an answer.

## Start the application

Use Python 3.10 or later from this directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/>. API documentation is at <http://127.0.0.1:8000/docs>. On first start, the application creates an ignored SQLite database and imports the 54 bundled notes. The app still works without a local model: supported questions return source extracts.

For optional local generation, [install Ollama](https://ollama.com/download), run `ollama pull qwen3:4b-instruct` and start Ollama. The default model connection is the loopback URL `http://127.0.0.1:11434/api/chat`. `OLLAMA_MODEL` selects an installed model; set it to an empty value to use extracts only. `OLLAMA_URL` can set another HTTP loopback `/api/chat` endpoint. The backend rejects remote model endpoints. No model weights or runtime database are stored in this repository.

The browser keeps chat history and optional helpfulness choices in that browser's local storage; the SQLite database stores public source notes, not conversations. `GET /api/sources` lists indexed notes and `GET /api/health` shows the active count and model setting.

## Check the code

Run the backend unit and API checks:

```sh
.venv/bin/python -m unittest discover -s backend/tests -v
```

With the local server running, record unscored responses to the synthetic questions:

```sh
.venv/bin/python tests/run_eval.py --scenario normal --environment-label local --model-label qwen3:4b-instruct
```

The runner writes raw results to ignored `tests/runs/`. It does **not** judge factual correctness. `tests/run_closed_book.py` separately calls a local Ollama model without retrieval as an exploratory baseline; it writes to ignored `evidence/test-runs/` and likewise does not score answers. Neither run should be described as a participant study or an independent source review.

### Report test evidence and independent review

[`tests/final-30-case-results-2026-10-10.csv`](tests/final-30-case-results-2026-10-10.csv) records the responses, retrieval details, response times and **provisional desk ratings** for the frozen 10 October evaluation: 29 normal synthetic questions and one model-outage case. Those ratings were AI-assisted and were **not** an independent human assessment. This CSV documents the evaluated 22-note build; the 10 October follow-up seeded 26 notes and the current website seeds 54 notes, so its answers may differ. The `raw_run_file` column points to run files held separately and is retained for provenance.

[`tests/two-rater-review-blank-2026-10-10.csv`](tests/two-rater-review-blank-2026-10-10.csv) contains the same 30 cases with blank reviewer A/B columns. The [review guide](tests/two-rater-review-guide.md) explains how two people can assess answers independently before using `tests/calc_interrater_kappa.py`. No human ratings or agreement statistic are claimed here.

Optional browser checks use Playwright:

```sh
npm install
npx playwright install chromium
npm run test:browser
```

The browser script opens a fresh context, checks core flows and saves its captures to ignored `evidence/`. Set `PLAYWRIGHT_BROWSER_PATH` to a local Chromium-compatible executable if you prefer to use an installed browser.
Set `GOV_ASSISTANT_URL` to another loopback origin if the local server uses a port other than 8000.

## Update source notes

`backend/seed_sources.json` contains short paraphrased notes and official links. New or revised material can be staged and inspected before indexing:

```sh
.venv/bin/python -m backend.sources_cli stage path/to/new_notes.json
.venv/bin/python -m backend.sources_cli list --status pending
.venv/bin/python -m backend.sources_cli approve 7 --source-checked
```

The last flag is an operator confirmation, not an automated source check. When an existing URL and section changes, stage and approve a revised note to supersede the old one. Tax and visa material changes over time; recheck the page and record a review date before indexing a change.

The original academic report, student details, screenshots, raw run files and local database are intentionally outside this code repository.
