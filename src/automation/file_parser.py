"""
Multi-format ingestion layer for the Step 3 automation prototype.

Normalises .jsonl / .json / .csv / .tsv / .xlsx inputs into a common
list-of-dicts form so that file_watcher.py and pi_5132_automator.py can
consume any of them without format-specific branching.

VERIFICATION STATUS (see WORKLOG.md Day 6 and reports/final_report.md
Section 2): full end-to-end correctness -- real durations flowing through
to accurate aggregate output -- has only been confirmed for .jsonl,
against the validated segments.jsonl. The other formats were exercised
with small synthetic files that confirmed structural parsing and label
filtering, but not duration arithmetic. Treat them as functionally
plausible, not load-tested.

The retry loop exists because a file copied into the watch directory on
Windows can be observed by the watcher before the write handle is
released, yielding a zero-byte stat or a partial read.
"""
import csv
import json
import time
from pathlib import Path
from typing import Any, Dict, List

SUPPORTED_SUFFIXES = {".jsonl", ".json", ".csv", ".tsv", ".xlsx", ".xls"}

# Fields the automator reads off each record. Timestamp fields are
# normalised to ISO-8601 strings on ingestion (see _normalise_record).
TIMESTAMP_FIELDS = ("start", "end")


def _normalise_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Coerce timestamp fields to ISO-8601 strings.

    Excel cannot store timezone-aware datetimes, so a file round-tripped
    through Excel comes back with native datetime cells and the UTC "Z"
    marker stripped. pandas then hands us datetime/Timestamp objects where
    the automator expects strings, and parsing raises ValueError.

    Durations are computed as (end - start), so both values losing the
    same timezone marker leaves the arithmetic correct; only the absolute
    UTC anchor is lost, which this pipeline does not depend on.
    """
    for field in TIMESTAMP_FIELDS:
        value = record.get(field)
        if value is None or isinstance(value, str):
            continue
        # datetime, date and pandas.Timestamp all expose isoformat().
        isoformat = getattr(value, "isoformat", None)
        if callable(isoformat):
            record[field] = isoformat()
        else:
            record[field] = str(value)
    return record


def parse_incoming_file(
    file_path: str, retries: int = 10, delay: float = 0.2
) -> List[Dict[str, Any]]:
    """
    Read file_path and return its rows as a list of dicts.

    Returns an empty list if the file could not be read after `retries`
    attempts, or if its extension is unsupported. Failures are reported
    on stdout rather than raised, so that a single bad drop cannot take
    down a long-running watcher process.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix not in SUPPORTED_SUFFIXES:
        print(f"[PARSER] Unsupported file type '{suffix}' -- skipping {path.name}. "
              f"Supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}")
        return []

    last_error = None

    for _attempt in range(retries):
        # Reset per attempt. Without this, a partial read followed by a
        # retry re-appends the rows already collected, silently inflating
        # the record count (confirmed: a .jsonl with one malformed line
        # returned 9 records instead of 4).
        records: List[Dict[str, Any]] = []

        try:
            # A zero-byte stat means the writer has not flushed yet.
            if path.stat().st_size == 0:
                time.sleep(delay)
                continue

            # utf-8-sig transparently strips the Windows UTF-8 BOM.
            if suffix == ".jsonl":
                with open(path, "r", encoding="utf-8-sig") as f:
                    for line in f:
                        if line.strip():
                            records.append(json.loads(line))

            elif suffix == ".json":
                with open(path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                records = data if isinstance(data, list) else [data]

            elif suffix in (".csv", ".tsv"):
                delimiter = "\t" if suffix == ".tsv" else ","
                with open(path, "r", encoding="utf-8-sig", newline="") as f:
                    records = list(csv.DictReader(f, delimiter=delimiter))

            elif suffix in (".xlsx", ".xls"):
                try:
                    import pandas as pd
                except ImportError:
                    print("[PARSER] pandas is required for Excel input but is not "
                          "installed. Run: pip install -r requirements.txt")
                    return []
                records = pd.read_excel(path).to_dict(orient="records")

            if records:
                return [_normalise_record(r) for r in records
                        if isinstance(r, dict)]

            # Parsed cleanly but empty: a genuinely empty file, not a
            # mid-write race. Retrying would not change the result.
            print(f"[PARSER] {path.name} contained no records.")
            return []

        except (PermissionError, OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            # Expected during a mid-write race -- back off and retry.
            last_error = exc
            time.sleep(delay)

        except Exception as exc:  # deliberately broad: surface real defects
            # Anything else is a real defect. Surface it rather than
            # letting the watcher report a silent zero.
            print(f"[PARSER] Unexpected {type(exc).__name__} reading "
                  f"{path.name}: {exc}")
            return []

    reason = type(last_error).__name__ if last_error else "file stayed empty"
    print(f"[PARSER] Gave up on {path.name} after {retries} attempts. Last issue: {reason}")
    return []
