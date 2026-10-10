#!/usr/bin/env python3
"""Record an unscored, exploratory closed-book run of the normal question fixture.

This calls a local Ollama model directly. It does not retrieve indexed notes, use
the Gov Assistant API, supply official links, or validate citations. Its answers
are not equivalent to the project's source-grounded pipeline. The output is a
raw observation record, not a factual or participant assessment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
CASES_PATH = HERE / "cases.json"
RUNS_PATH = HERE.parent / "evidence" / "test-runs"
DEFAULT_ENDPOINT = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "qwen3:4b-instruct"
SYSTEM_PROMPT = (
    "Answer the user's Australian tax or visa question in concise Australian "
    "English. You have no retrieved source notes, browsing, tools, or access to "
    "personal government records in this run. State uncertainty when current "
    "rules or individual circumstances matter. Do not invent live fees, "
    "processing times, application outcomes, or citations. Do not request "
    "personal identifiers."
)


def loopback_chat_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path != "/api/chat"
    ):
        raise argparse.ArgumentTypeError("Use only a local HTTP Ollama /api/chat endpoint")
    return value


def exchange(url: str, payload: dict | None, timeout: float) -> dict:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Accept": "application/json", **({"Content-Type": "application/json"} if body else {})},
        method="POST" if body is not None else "GET",
    )
    start = time.perf_counter()
    status = None
    raw = None
    error = None
    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.status
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8", errors="replace")
        error = f"HTTP {exc.code}"
    except (URLError, TimeoutError, OSError) as exc:
        error = f"{type(exc).__name__}: {exc}"
    parsed = None
    if raw is not None:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            error = error or "Response was not valid JSON"
    return {
        "transport": "ok" if status == 200 and isinstance(parsed, dict) else "error",
        "http_status": status,
        "latency_ms": round((time.perf_counter() - start) * 1000, 1),
        "response_raw": raw,
        "response_json": parsed,
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", type=loopback_chat_url, default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.model.strip() or args.timeout <= 0:
        parser.error("--model must be non-empty and --timeout must be positive")

    fixture_bytes = CASES_PATH.read_bytes()
    fixture = json.loads(fixture_bytes)
    if fixture.get("schema_version") != 1 or not isinstance(fixture.get("cases"), list):
        parser.error("Unsupported cases.json format")
    cases = [case for case in fixture["cases"] if case.get("scenario") == "normal"]
    if len(cases) != 29 or len({case["id"] for case in cases}) != len(cases):
        parser.error("Expected 29 uniquely identified normal fixture questions")

    origin = args.endpoint[: -len("/api/chat")]
    version = exchange(f"{origin}/api/version", None, args.timeout)
    tags = exchange(f"{origin}/api/tags", None, args.timeout)
    if version["transport"] != "ok" or tags["transport"] != "ok":
        parser.error("Local Ollama metadata endpoints are unavailable")
    models = tags["response_json"].get("models", [])
    model_record = next((item for item in models if item.get("name") == args.model), None)
    if model_record is None:
        parser.error(f"Local Ollama model is not installed: {args.model}")

    now = datetime.now(timezone.utc)
    output = args.output or RUNS_PATH / f"eval-closed-book-{now.strftime('%Y%m%dT%H%M%S%fZ')}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        parser.error(f"Output already exists: {output}")

    records = []
    for index, case in enumerate(cases, 1):
        # The exact question is sent as-is; topic and expected criteria stay in
        # the fixture record for traceability but are not model context.
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": case["question"]},
        ]
        payload = {"model": args.model, "stream": False, "options": {"temperature": 0}, "messages": messages}
        result = exchange(args.endpoint, payload, args.timeout)
        answer = None
        if isinstance(result["response_json"], dict):
            message = result["response_json"].get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                answer = message["content"]
        records.append({
            "case_id": case["id"],
            "question": case["question"],
            "fixture_topic_not_sent": case.get("topic"),
            "request": payload,
            **result,
            "answer_text": answer,
            "review": {"outcome": None, "reviewer": "", "source_page_checked_on": None},
        })
        print(f"{index:>2}/{len(cases)} {case['id']}: HTTP {result['http_status'] or '-'}; {result['latency_ms']} ms; {result['transport']}", flush=True)

    report = {
        "schema_version": 1,
        "kind": "exploratory_closed_book_local_llm",
        "created_at_utc": now.isoformat(),
        "method_note": (
            "Direct local-model baseline using the same 29 normal synthetic question wordings. "
            "No Gov Assistant retrieval, indexed notes, route selection, official links, citation validator, "
            "extractive fallback, or answer-quality scoring. This is not a controlled or equivalent "
            "comparison with the source-grounded system. No human factual or participant rating is claimed."
        ),
        "fixture_path": "tests/cases.json",
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "prompt_provenance": {
            "system_prompt": SYSTEM_PROMPT,
            "system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
            "user_prompt": "Exact case question text; no topic label or retrieved notes sent",
            "design": "Exploratory comparison prompt written for this runner; it is not the Gov Assistant API prompt",
        },
        "ollama_endpoint": args.endpoint,
        "ollama_version": version["response_json"].get("version"),
        "model": args.model,
        "model_digest": model_record.get("digest"),
        "model_details": model_record.get("details"),
        "temperature": 0,
        "selected_count": len(cases),
        "records": records,
    }
    # Exclusive creation prevents a later run from replacing evidence.
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"Saved {output}")
    print(f"Transport success: {sum(r['transport'] == 'ok' for r in records)}/{len(records)}; human-scored: 0")
    return 0 if all(record["transport"] == "ok" and record["answer_text"] for record in records) else 1


if __name__ == "__main__":
    sys.exit(main())
