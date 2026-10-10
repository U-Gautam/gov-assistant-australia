#!/usr/bin/env python3
"""Record unscored, reproducible responses from the local Gov Assistant API.

Run from any directory. Only loopback API addresses are accepted so that the
synthetic privacy test cannot accidentally be sent to a hosted service.
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
RUNS_PATH = HERE / "runs"


def local_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise argparse.ArgumentTypeError("The evaluator only sends questions to a local HTTP API")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise argparse.ArgumentTypeError("Provide only the local API origin, for example http://127.0.0.1:8000")
    return value.rstrip("/")


def request_json(url: str, payload: dict | None, timeout: float) -> dict:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
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
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    parsed = None
    if raw is not None:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            if error is None:
                error = "Response was not valid JSON"
    transport = "ok" if status == 200 and isinstance(parsed, dict) else "error"
    return {
        "transport": transport,
        "http_status": status,
        "latency_ms": elapsed_ms,
        "response_raw": raw,
        "response_json": parsed,
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", type=local_url, default="http://127.0.0.1:8000")
    parser.add_argument("--scenario", choices=("normal", "model_offline"), default="normal")
    parser.add_argument("--id", action="append", dest="case_ids", help="Run one case ID; repeat for several")
    parser.add_argument("--output", type=Path, help="New JSON output path; existing files are never overwritten")
    parser.add_argument("--timeout", type=float, default=45.0, help="Timeout per API call in seconds")
    parser.add_argument("--environment-label", default="not recorded", help="Human-entered device or build label")
    parser.add_argument("--model-label", default="not recorded", help="Human-entered local model name or 'none'")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    fixture_bytes = CASES_PATH.read_bytes()
    fixture = json.loads(fixture_bytes)
    if fixture.get("schema_version") != 1 or not isinstance(fixture.get("cases"), list):
        parser.error("Unsupported cases.json format")
    cases = [case for case in fixture["cases"] if case["scenario"] == args.scenario]
    if args.case_ids:
        unknown = sorted(set(args.case_ids) - {case["id"] for case in cases})
        if unknown:
            parser.error(f"Unknown IDs for {args.scenario}: {', '.join(unknown)}")
        cases = [case for case in cases if case["id"] in set(args.case_ids)]
    if not cases:
        parser.error("No cases selected")

    health = request_json(f"{args.base_url}/api/health", None, args.timeout)
    if args.scenario == "model_offline":
        info = health.get("response_json")
        if health["transport"] != "ok" or not isinstance(info, dict) or not info.get("ollama_model"):
            parser.error("For model_offline, start the API with OLLAMA_MODEL set and Ollama unreachable; /api/health must report a non-empty ollama_model")

    now = datetime.now(timezone.utc)
    output = args.output or RUNS_PATH / f"eval-{args.scenario}-{now.strftime('%Y%m%dT%H%M%S%fZ')}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        parser.error(f"Output already exists: {output}")

    records = []
    for index, case in enumerate(cases, 1):
        payload = {"question": case["question"], "topic": case["topic"]}
        result = request_json(f"{args.base_url}/api/chat", payload, args.timeout)
        records.append({
            "case": case,
            "request": payload,
            **result,
            "review": {
                "outcome": None,
                "criterion_notes": "",
                "source_page_checked_on": None,
                "reviewer": "",
                "reviewed_at": None,
            },
        })
        print(f"{index:>2}/{len(cases)} {case['id']}: HTTP {result['http_status'] or '-'}; {result['latency_ms']} ms; {result['transport']}")

    report = {
        "schema_version": 1,
        "created_at_utc": now.isoformat(),
        "base_url": args.base_url,
        "scenario": args.scenario,
        "environment_label": args.environment_label,
        "model_label": args.model_label,
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "api_health": health,
        "selected_count": len(cases),
        "records": records,
        "note": "These are raw observations only. No answer has been scored or source-checked by this runner.",
    }
    # Exclusive creation prevents a later run from replacing evidence.
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"Saved {output}")
    print(f"Transport success: {sum(record['transport'] == 'ok' for record in records)}/{len(records)}; human-scored: 0")
    return 0 if all(record["transport"] == "ok" for record in records) else 1


if __name__ == "__main__":
    sys.exit(main())
