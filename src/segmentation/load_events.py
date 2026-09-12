"""
Basic loaders for events.jsonl / gt.jsonl, generalized from the ad-hoc
scripts used during Day 1 exploration.

Not yet wired into a segmentation pipeline — just the shared I/O layer
so later scripts don't re-write this each time.
"""
import json
import glob
import os


def load_session_events(session_dir):
    """
    Load all events.jsonl files for a session, across all its chunks,
    in chronological order. Returns a list of dicts.

    session_dir: path to a ses_* directory (contains one or more chunk_*
    subdirectories).
    """
    files = sorted(glob.glob(os.path.join(session_dir, "chunk_*", "events.jsonl")))
    events = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
    events.sort(key=lambda e: e["timestamp_iso"])
    return events


def load_gt(session_dir):
    """
    Load gt.jsonl for a Dataset A session. Returns list of dicts,
    in file order (already chronological per DATA_SCHEMA.md).
    """
    gt_path = os.path.join(session_dir, "gt.jsonl")
    with open(gt_path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def dedup_app_switches(events):
    """
    Filter app_switch events, dropping self-transitions where the
    (process_id, window_title) of new_app matches previous_app exactly.

    See WORKLOG.md Day 1, finding #3: raw app_switch events contain many
    duplicate/self-transition entries that are a recording artifact, not
    real window changes. app_name alone is NOT a safe dedup key (distinct
    windows/processes can share the same app_name) — must use process_id
    + window_title.

    Returns the full event list with duplicate app_switch events removed;
    non-app_switch events are untouched.
    """
    out = []
    for e in events:
        if e.get("event_type") != "app_switch":
            out.append(e)
            continue
        na = e["payload"]["new_app"]
        pa = e["payload"]["previous_app"]
        is_dup = (na["process_id"], na["window_title"]) == (pa["process_id"], pa["window_title"])
        if not is_dup:
            out.append(e)
    return out


def gt_process_transitions(gt_events):
    """
    Filter gt.jsonl entries down to process-level transition events only
    (process_started / process_switched_out / process_suspended /
    process_resumed / session_ended) — the events used in Day 1 to trace
    session structure.
    """
    keep = {
        "process_started",
        "process_switched_out",
        "process_suspended",
        "process_resumed",
        "session_ended",
    }
    return [e for e in gt_events if e.get("event") in keep]
