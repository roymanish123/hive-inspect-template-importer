"""Validate any supported export and write reviewable evidence without a database."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hive_importer.importer import ImportFailure, parse_export

parser = argparse.ArgumentParser()
parser.add_argument("file", type=Path)
parser.add_argument("--output", type=Path)
args = parser.parse_args()
try:
    result = parse_export(args.file.read_bytes(), args.file.name)
except (ImportFailure, OSError) as exc:
    print(json.dumps({"status": "blocked", "error": str(exc), "issues": getattr(exc, "issues", [])}, ensure_ascii=False, indent=2))
    raise SystemExit(1)
print(json.dumps(result["report"], ensure_ascii=False, indent=2))
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
