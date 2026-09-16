import csv
import json
from pathlib import Path
import time
from typing import Any, Dict, List


def parse_incoming_file(
    file_path: str, retries: int = 10, delay: float = 0.2
) -> List[Dict[str, Any]]:
  path = Path(file_path)
  records = []

  for attempt in range(retries):
    try:
      # Wait if the file is still 0 bytes (Windows copy buffer lag)
      if path.stat().st_size == 0:
        time.sleep(delay)
        continue

      if path.suffix == ".jsonl":
        with open(path, "r", encoding="utf-8") as f:
          for line in f:
            if line.strip():
              records.append(json.loads(line))

      elif path.suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
          data = json.load(f)
          records = data if isinstance(data, list) else [data]

      elif path.suffix in [".csv", ".tsv"]:
        delimiter = "\t" if path.suffix == ".tsv" else ","
        with open(path, "r", encoding="utf-8-sig") as f:
          reader = csv.DictReader(f, delimiter=delimiter)
          records = list(reader)

      elif path.suffix in [".xlsx", ".xls"]:
        import pandas as pd

        df = pd.read_excel(path)
        records = df.to_dict(orient="records")

      if records:
        return records

    except (PermissionError, OSError):
      time.sleep(delay)

  return records