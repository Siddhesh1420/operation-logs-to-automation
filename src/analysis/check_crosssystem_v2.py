"""
Corrected cross-system contamination check: separates "other PORTAL system"
(the real concern -- Finance/Logistics foreground during an HR segment's
back-dated window) from "non-portal document" (Word/Excel/Notepad -- already
validated in Day 4 as legitimate reference-lookup time) and true unknown
(no window title resolved yet).

Run: python check_crosssystem_v2.py data/dataset_b segments.jsonl 5132_pi
"""
import json, glob, os, sys
from collections import defaultdict
from datetime import datetime

SYSTEM_TITLE_TO_PORT = {
    "HR人事給与システム": "5132",
    "財務会計システム": "5133",
    "受発注在庫管理システム": "5134",
}

def parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))

def load_segments(path, label_filter):
    by_session = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            s = json.loads(line)
            if s["label"] == label_filter:
                by_session[s["session_id"]].append(s)
    for sid in by_session:
        by_session[sid].sort(key=lambda s: s["start"])
    return by_session

def load_events(session_dir):
    files = sorted(glob.glob(os.path.join(session_dir, "chunk_*/events.jsonl")))
    events = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            events.extend(json.loads(l) for l in fh if l.strip())
    events.sort(key=lambda e: e["timestamp_iso"])
    return events

def find_raw_note_click(events, segment_end_ts, screen):
    candidates = [e for e in events if e["timestamp_iso"] <= segment_end_ts]
    for e in reversed(candidates):
        et = e.get("event_type")
        if et == "browser_click":
            elem = e.get("payload", {}).get("element") or {}
            attrs = elem.get("attributes") or {}
            eid = attrs.get("id") or elem.get("id") or ""
            if eid == f"{screen}-note":
                return e["timestamp_iso"]
        elif et == "mouse_click":
            ext = e.get("extensions", {})
            uia = ext.get("uia_v2", {})
            aid = uia.get("target", {}).get("automation_id") or ""
            if aid == f"{screen}-note":
                return e["timestamp_iso"]
    return None

def classify_title(title, own_port):
    """Returns 'own', 'other_portal', or 'non_portal' -- always resolves to
    SOMETHING (no more silent None -> 'unknown' collapse)."""
    if not title:
        return None  # genuinely no data yet
    for sys_name, port in SYSTEM_TITLE_TO_PORT.items():
        if sys_name in title:
            return "own" if port == own_port else "other_portal"
    return "non_portal"  # Word, Excel, Notepad, or anything else non-matching

def main(dataset_b_dir, segments_path, target_label):
    own_port = target_label.split("_")[0]
    screen = target_label.split("_", 1)[1]
    by_session = load_segments(segments_path, target_label)

    totals = defaultdict(float)
    per_segment_rows = []

    for sid, segs in by_session.items():
        events = load_events(os.path.join(dataset_b_dir, sid))
        for s in segs:
            raw_note_ts = find_raw_note_click(events, s["end"], screen)
            if not raw_note_ts:
                continue
            window_start, window_end = s["start"], raw_note_ts
            window_sec = (parse(window_end) - parse(window_start)).total_seconds()
            if window_sec <= 0:
                continue

            in_window = sorted(
                [e for e in events if window_start <= e["timestamp_iso"] <= window_end],
                key=lambda e: e["timestamp_iso"]
            )

            bucket_sec = defaultdict(float)
            prev_ts = window_start
            prev_class = None

            for e in in_window:
                ctx = e.get("context") or {}
                aa = ctx.get("active_app") or {}
                title = aa.get("window_title", "")
                cls = classify_title(title, own_port)

                seg_dur = (parse(e["timestamp_iso"]) - parse(prev_ts)).total_seconds()
                bucket_sec[prev_class or "unknown_no_data"] += seg_dur

                prev_ts = e["timestamp_iso"]
                if cls:
                    prev_class = cls

            tail_dur = (parse(window_end) - parse(prev_ts)).total_seconds()
            bucket_sec[prev_class or "unknown_no_data"] += tail_dur

            for k, v in bucket_sec.items():
                totals[k] += v

            if len(per_segment_rows) < 15:
                per_segment_rows.append((sid, window_sec, dict(bucket_sec)))

    total_all = sum(totals.values())
    print(f"=== Corrected contamination check for {target_label} ===")
    print(f"Total back-dated review-window time analyzed: {total_all:.1f}s ({total_all/60:.2f} min)\n")
    for k in ["own", "other_portal", "non_portal", "unknown_no_data"]:
        v = totals.get(k, 0.0)
        pct = 100 * v / total_all if total_all else 0
        print(f"  {k:<18}: {v:.1f}s ({pct:.1f}%)")

    print(f"\n=== Sample segments (first 15) ===")
    for sid, w, buckets in per_segment_rows:
        print(f"  {sid} | window={w:.2f}s | {buckets}")

if __name__ == "__main__":
    dataset_b_dir = sys.argv[1] if len(sys.argv) > 1 else "data/dataset_b"
    segments_path = sys.argv[2] if len(sys.argv) > 2 else "segments.jsonl"
    label = sys.argv[3] if len(sys.argv) > 3 else "5132_pi"
    main(dataset_b_dir, segments_path, label)