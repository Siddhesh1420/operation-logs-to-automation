"""
Step 2 Operational Analysis: Volume, Duration, and Variance Metrics
"""
import json
import sys
import statistics
from collections import defaultdict
from datetime import datetime

def parse_ts(ts_str):
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

def main(segments_path="segments.jsonl"):
    segments = []
    with open(segments_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                segments.append(json.loads(line))

    stats = defaultdict(list)
    sessions_by_label = defaultdict(set)

    for s in segments:
        lbl = s["label"]
        t0 = parse_ts(s["start"])
        t1 = parse_ts(s["end"])
        dur = (t1 - t0).total_seconds()
        stats[lbl].append(dur)
        sessions_by_label[lbl].add(s["session_id"])

    print(f"{'Label':<10} | {'Vol':<5} | {'TotMin':<7} | {'Mean(s)':<7} | {'Med(s)':<7} | {'Std(s)':<7} | {'CV':<7} | {'P90(s)':<7} | {'Sess':<5}")
    print("-" * 85)

    for lbl, durs in sorted(stats.items(), key=lambda x: sum(x[1]), reverse=True):
        cnt = len(durs)
        tot_min = sum(durs) / 60.0
        mean_sec = statistics.mean(durs)
        med_sec = statistics.median(durs)
        std_sec = statistics.stdev(durs) if cnt > 1 else 0.0
        cv = std_sec / mean_sec if mean_sec > 0 else 0.0
        
        sorted_durs = sorted(durs)
        p90_idx = int(0.90 * cnt) - 1
        p90_sec = sorted_durs[max(0, p90_idx)]
        sess_cnt = len(sessions_by_label[lbl])

        print(f"{lbl:<10} | {cnt:<5} | {tot_min:<7.2f} | {mean_sec:<7.2f} | {med_sec:<7.2f} | {std_sec:<7.2f} | {cv:<7.3f} | {p90_sec:<7.2f} | {sess_cnt:<5}")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "segments.jsonl"
    main(path)