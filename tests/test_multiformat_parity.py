"""
Closes the Day 6 open question: does multi-format ingestion produce
identical results on REAL segment data, not just placeholder test files?

Day 6 verified .jsonl against the validated segments.jsonl but only
exercised .csv/.tsv/.json/.xlsx with 1-2 record synthetic files carrying
degenerate timestamps, which could not confirm duration arithmetic.

This writes the same real segments.jsonl content out to every supported
format and asserts that the automator's aggregate output is identical
across all of them.

Run from the repository root:
    python tests/test_multiformat_parity.py [segments.jsonl]
"""
import csv
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "automation"))

from file_parser import parse_incoming_file  # noqa: E402
from pi_5132_automator import HR5132PIAutomator  # noqa: E402

FIELDS = ["session_id", "start", "end", "label"]


def write_formats(segments, out_dir):
    """Write `segments` to every supported format. Returns {ext: path}."""
    paths = {}

    jsonl = out_dir / "parity.jsonl"
    with open(jsonl, "w", encoding="utf-8") as f:
        for s in segments:
            f.write(json.dumps(s) + "\n")
    paths["jsonl"] = jsonl

    js = out_dir / "parity.json"
    with open(js, "w", encoding="utf-8") as f:
        json.dump(segments, f)
    paths["json"] = js

    for ext, delim in (("csv", ","), ("tsv", "\t")):
        p = out_dir / f"parity.{ext}"
        with open(p, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter=delim)
            writer.writeheader()
            writer.writerows(segments)
        paths[ext] = p

    try:
        import pandas as pd
    except ImportError:
        print("[SKIP] pandas not installed -- .xlsx parity not checked.")
    else:
        p = out_dir / "parity.xlsx"
        pd.DataFrame(segments).to_excel(p, index=False)
        paths["xlsx"] = p

        # Hostile case: a file the client round-tripped through Excel.
        # Excel cannot store timezone-aware datetimes, so it rewrites the
        # ISO-8601 strings as native datetime cells and drops the UTC "Z".
        # pandas then returns Timestamp objects where the automator expects
        # strings. This used to raise ValueError; the parser now coerces
        # them back to ISO strings on ingestion.
        hostile = pd.DataFrame(segments)
        for field in ("start", "end"):
            hostile[field] = pd.to_datetime(hostile[field]).dt.tz_localize(None)
        # Reordered columns, plus an extra column the automator ignores.
        hostile["operator_note"] = "added by client"
        hostile = hostile[["label", "end", "operator_note", "start", "session_id"]]
        p = out_dir / "parity_excel_roundtrip.xlsx"
        hostile.to_excel(p, index=False)
        paths["xlsx-roundtrip"] = p

    return paths


def main(segments_path="segments.jsonl"):
    if not Path(segments_path).exists():
        print(f"FAIL: {segments_path} not found. Run from the repository root.")
        return 1

    segments = [json.loads(line) for line in open(segments_path, encoding="utf-8")
                if line.strip()]
    print(f"Source: {len(segments)} segments from {segments_path}")

    automator = HR5132PIAutomator()
    baseline = None
    failures = []

    with tempfile.TemporaryDirectory() as tmp:
        paths = write_formats(segments, Path(tmp))

        header = f"{'format':<8} {'records':>8} {'matched':>8} {'human_min':>11} {'saved_min':>10}  result"
        print("\n" + header)
        print("-" * len(header))

        for ext, path in paths.items():
            records = parse_incoming_file(str(path))
            summary = automator.batch_process_records(records)
            result = (
                len(records),
                summary["total_records_processed"],
                summary["total_active_minutes_actual_human_time"],
            )
            if baseline is None:
                baseline = result
            ok = result == baseline
            if not ok:
                failures.append(ext)
            print(f"{ext:<8} {result[0]:>8} {result[1]:>8} {result[2]:>11} "
                  f"{summary['projected_minutes_saved_vs_raw_click']:>10}  "
                  f"{'OK' if ok else 'MISMATCH'}")

    if failures:
        print(f"\nFAIL: {', '.join(failures)} disagreed with the .jsonl baseline.")
        return 1

    print(f"\nPASS: all {len(paths)} formats agree "
          f"({baseline[1]} matched 5132_pi segments, {baseline[2]} min).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "segments.jsonl"))
