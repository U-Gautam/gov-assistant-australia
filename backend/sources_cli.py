"""Stage and approve source notes without exposing a public editing endpoint.

Run from the project root, for example:
  python -m backend.sources_cli stage backend/new_notes.json
  python -m backend.sources_cli list --status pending
  python -m backend.sources_cli approve 7 --source-checked
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .storage import approve_note, connect, list_notes, stage_note


DEFAULT_DB = Path(__file__).resolve().parent / "data" / "knowledge.sqlite"


def main() -> None:
    parser = argparse.ArgumentParser(description="Review and index official-source notes")
    parser.add_argument("--db", default=os.getenv("GOV_ASSISTANT_DB_PATH", str(DEFAULT_DB)), help="SQLite knowledge database")
    subcommands = parser.add_subparsers(dest="command", required=True)
    stage = subcommands.add_parser("stage", help="Import JSON notes as pending, not searchable")
    stage.add_argument("file", type=Path)
    listing = subcommands.add_parser("list", help="List note metadata")
    listing.add_argument("--status", choices=["pending", "approved", "superseded"])
    approve = subcommands.add_parser("approve", help="Make a reviewed pending note searchable")
    approve.add_argument("id", type=int)
    approve.add_argument("--source-checked", action="store_true", help="Confirm that the URL and paraphrase were compared with the current official page")
    args = parser.parse_args()
    db = connect(args.db)
    if args.command == "stage":
        records = json.loads(args.file.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise SystemExit("The JSON file must contain a list of source notes.")
        for record in records:
            note_id, status = stage_note(db, record)
            print(f"{note_id}: {status} — {record['title']}")
        print("Pending notes are not included in answers. Check each official page before approving.")
    elif args.command == "list":
        for note in list_notes(db, args.status):
            print(f"{note['id']:>3}  {note['status']:<10}  {note['reviewed_on']}  {note['title']} — {note['section']}\n     {note['url']}")
    elif args.command == "approve":
        if not args.source_checked:
            raise SystemExit("Read the current official page, compare the staged note, then rerun with --source-checked.")
        approve_note(db, args.id)
        print(f"Approved and indexed source note {args.id}.")


if __name__ == "__main__":
    main()
