"""
Step 2c: Slow-Tail Root Cause Check
For each of the three suspect labels, isolates whether p90+ transactions are
slow because of pre-click human dwell (reading time) or inflated raw click-to-submit
time (possible UI branching / secondary validation).

Usage:
    python step2c_slow_tail_check.py data/dataset_b segments.jsonl
"""
import json
import glob
import os
import sys
from collections import defaultdict
from datetime import datetime


def parse_ts(ts_str):
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))


def load_events(session_dir):
    files = sorted(glob.glob(os.path.join(session_dir, "chunk_*/events.jsonl")))
    events = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            events.extend(json.loads(l) for l in fh if l.strip())
    events.sort(key=lambda e: e["timestamp_iso"])
    return events


def find_raw_note_click_before(events, segment_end_ts, label_screen):
    candidates = [e for e in events if e["timestamp_iso"] <= segment_end_ts]
    for e in reversed(candidates):
        et = e.get("event_type")
        if et == "browser_click":
            elem = e.get("payload", {}).get("element") or {}
            attrs = elem.get("attributes") or {}
            eid = attrs.get("id") or elem.get("id") or ""
            if eid == f"{label_screen}-note":
                return e["timestamp_iso"]
        elif et == "mouse_click":
            ext = e.get("extensions", {})
            uia = ext.get("uia_v2", {})
            aid = uia.get("target", {}).get("automation_id") or ""
            if aid == f"{label_screen}-note":
                return e["timestamp_iso"]
    return None


def main(dataset_b_dir="data/dataset_b", segments_path="segments.jsonl"):
    TARGET_LABELS = {"5133_pi", "5132_ob", "5133_rt"}

    segments = [json.loads(l) for l in open(segments_path, encoding="utf-8") if l.strip()]
    by_session = defaultdict(list)
    for s in segments:
        by_session[s["session_id"]].append(s)

    # group target segments by label
    by_label = defaultdict(list)
    for s in segments:
        if s["label"] in TARGET_LABELS:
            by_label[s["label"]].append(s)

    # cache loaded events per session so we don't reload repeatedly
    events_cache = {}

    for label, segs in by_label.items():
        durs = sorted((parse_ts(s["end"]) - parse_ts(s["start"])).total_seconds() for s in segs)
        n = len(durs)
        p90 = durs[int(n * 0.9)]
        slow_segs = [s for s in segs
                     if (parse_ts(s["end"]) - parse_ts(s["start"])).total_seconds() >= p90]

        print(f"\n{label} — p90={p90:.1f}s, slow tail n={len(slow_segs)}")
        print(f"  {'session':<35} {'total':>7} {'dwell':>7} {'raw_click':>10}")

        screen = label.split("_", 1)[1]
        for s in sorted(slow_segs, key=lambda s: -(parse_ts(s["end"]) - parse_ts(s["start"])).total_seconds()):
            sid = s["session_id"]
            total_dur = (parse_ts(s["end"]) - parse_ts(s["start"])).total_seconds()

            if sid not in events_cache:
                session_path = os.path.join(dataset_b_dir, sid)
                events_cache[sid] = load_events(session_path) if os.path.exists(session_path) else []
            events = events_cache[sid]

            raw_click_ts = find_raw_note_click_before(events, s["end"], screen)
            if raw_click_ts:
                dwell = (parse_ts(raw_click_ts) - parse_ts(s["start"])).total_seconds()
                raw_click_dur = (parse_ts(s["end"]) - parse_ts(raw_click_ts)).total_seconds()
                print(f"  {sid:<35} {total_dur:7.1f} {dwell:7.1f} {raw_click_dur:10.1f}")
            else:
                print(f"  {sid:<35} {total_dur:7.1f} {'N/A':>7} {'N/A':>10}  (no click match)")


if __name__ == "__main__":
    db_dir = sys.argv[1] if len(sys.argv) > 1 else "data/dataset_b"
    seg_path = sys.argv[2] if len(sys.argv) > 2 else "segments.jsonl"
    main(db_dir, seg_path)