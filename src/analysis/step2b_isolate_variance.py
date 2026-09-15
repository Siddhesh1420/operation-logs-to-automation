"""
Step 2b Variance Isolation: Compares Backdated CV vs Raw Click-to-Submit CV
"""
import json
import glob
import os
import sys
import statistics
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
    segments = [json.loads(line) for line in open(segments_path, encoding="utf-8") if line.strip()]
    by_session = defaultdict(list)
    for s in segments:
        by_session[s["session_id"]].append(s)

    raw_durations = defaultdict(list)
    backdated_durations = defaultdict(list)
    backdate_amounts = defaultdict(list)

    for sid, segs in by_session.items():
        session_path = os.path.join(dataset_b_dir, sid)
        if not os.path.exists(session_path):
            continue
        events = load_events(session_path)
        for s in segs:
            screen = s["label"].split("_", 1)[1]
            raw_note_ts = find_raw_note_click_before(events, s["end"], screen)
            bd_dur = (parse_ts(s["end"]) - parse_ts(s["start"])).total_seconds()
            backdated_durations[s["label"]].append(bd_dur)
            
            if raw_note_ts:
                raw_dur = (parse_ts(s["end"]) - parse_ts(raw_note_ts)).total_seconds()
                raw_durations[s["label"]].append(raw_dur)
                backdate_amounts[s["label"]].append((parse_ts(raw_note_ts) - parse_ts(s["start"])).total_seconds())

    print(f"{'Label':<10} | {'BackdatedCV':<12} | {'RawClickCV':<11} | {'AvgBackdate(s)':<15} | {'Matched':<8}")
    print("-" * 65)
    for label in sorted(backdated_durations, key=lambda l: -len(backdated_durations[l])):
        bd_durs = backdated_durations[label]
        raw_durs = raw_durations[label]
        b_amts = backdate_amounts[label]
        
        bd_cv = statistics.stdev(bd_durs) / statistics.mean(bd_durs) if len(bd_durs) > 1 else 0.0
        raw_cv = statistics.stdev(raw_durs) / statistics.mean(raw_durs) if len(raw_durs) > 1 else 0.0
        avg_bd = sum(b_amts) / len(b_amts) if b_amts else 0.0
        
        print(f"{label:<10} | {bd_cv:<12.3f} | {raw_cv:<11.3f} | {avg_bd:<15.2f} | {len(raw_durs)}/{len(bd_durs)}")

if __name__ == "__main__":
    db_dir = sys.argv[1] if len(sys.argv) > 1 else "data/dataset_b"
    seg_path = sys.argv[2] if len(sys.argv) > 2 else "segments.jsonl"
    main(db_dir, seg_path)