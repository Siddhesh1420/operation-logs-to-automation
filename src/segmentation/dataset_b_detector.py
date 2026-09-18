"""
Dataset B boundary detector.

See WORKLOG.md Day 2 (cont'd) and Day 3 for the full investigation this
is based on. Summary of the design:

Dataset B is the actual Step 1 deliverable (segments.jsonl at repo root).
Dataset A's automation_id-case-ID approach does NOT transfer here -- B's
automation_ids are generic per-screen field labels (pi-note, la-note,
etc.) with no case identity embedded (confirmed by direct inspection).

Two-path design, based on whether a session has L3 (browser_click) data:

PATH 1 -- IMPLEMENTED. 14/15 sessions have L3 data.
    Uses browser_click events' payload.element.attributes.id:
    - id == "{screen}-note"       -> anchors the CLOSE side of case
                                     identification; see start-time
                                     back-dating below
    - id == "btn-{screen}-ok"     -> closes the open segment for that
                                     screen and emits it.

PATH 2 -- IMPLEMENTED. 1/15 sessions has zero L3 data
    (ses_20260701-192455-NEELA9BAF).
    automation_id still exposes "{screen}-note" via UIA even without the
    browser extension. The submit action is detected via physical mouse_click
    coordinates at the submit button location (x: 590-670, y: 1845-1885),
    with host port mapped from active L2 window titles.

Validation is by spot-checking a sample of emitted segments against 
context.extracted_text and/or screenshots for plausibility.
"""
import json
import glob
import os
from datetime import datetime, timedelta


SYSTEM_TITLE_TO_PORT = {
    "HR人事給与システム": "5132",
    "財務会計システム": "5133",
    "受発注在庫管理システム": "5134"
}

PORTAL_ACTIVITY_TYPES = {
    "browser_click", "mouse_click", "mouse_scroll", "screenshot_smart",
    "browser_navigation",
}


def _continuous_portal_run_start(events, before_ts, not_before_ts,
                                  max_intra_gap_sec=3.0):
    """
    Validated in capture_recoverable_time.py: recovers ~9.6 min of start-time
    back-dating that the app_switch-only rule missed, by walking backward
    through an unbroken chain of same-screen portal activity (no app_switch)
    when no app_switch is found in the normal lookback window.
    """
    before_dt = parse(before_ts)
    not_before_dt = parse(not_before_ts) if not_before_ts else None

    candidates = [e for e in events if e["timestamp_iso"] < before_ts]
    candidates.sort(key=lambda e: e["timestamp_iso"])

    chain_end_dt = before_dt
    earliest_in_chain = None

    for e in reversed(candidates):
        ts = e["timestamp_iso"]
        dt = parse(ts)

        if not_before_dt and dt <= not_before_dt:
            break
        if e.get("event_type") == "app_switch":
            break
        if e.get("event_type") not in PORTAL_ACTIVITY_TYPES:
            break

        gap = (chain_end_dt - dt).total_seconds()
        if gap > max_intra_gap_sec:
            break

        earliest_in_chain = ts
        chain_end_dt = dt

    return earliest_in_chain


def resolve_segment_start(events, note_ts, claimed_app_switches,
                           backdate_lookback_sec, last_segment_end):
    """
    Priority: (1) nearest preceding app_switch, (2) continuous portal-activity
    chain if no app_switch found, (3) raw note-click timestamp as last resort.
    """
    backdated = _nearest_preceding_app_switch(
        events, note_ts, claimed_app_switches,
        lookback_sec=backdate_lookback_sec,
        not_before_ts=last_segment_end,
    )
    if backdated:
        claimed_app_switches.add(backdated)
        return backdated

    portal_chain_start = _continuous_portal_run_start(
        events, note_ts, not_before_ts=last_segment_end,
    )
    if portal_chain_start:
        return portal_chain_start

    return note_ts


def parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def load_session_events(session_dir):
    """Load and time-sort all events.jsonl files across a session's chunks."""
    files = sorted(glob.glob(session_dir + "/chunk_*/events.jsonl"))
    events = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            events.extend(json.loads(line) for line in fh if line.strip())
    events.sort(key=lambda e: e["timestamp_iso"])
    return events


def session_has_l3_data(events):
    """Return True if this session has any L3 (browser extension) events."""
    return any(e.get("layer") == "L3" for e in events)


def browser_click_element_id(event):
    """
    Extract the element id from a browser_click event's payload, if any.
    This is payload.element.(attributes.id or id).
    """
    if event.get("event_type") != "browser_click":
        return None
    elem = event.get("payload", {}).get("element") or {}
    attrs = elem.get("attributes") or {}
    return attrs.get("id") or elem.get("id")


def active_tab_host(event):
    """
    Extract host:port from context.active_browser_tab.url, if present.
    Returns port alone if available (e.g. '5132').
    """
    ctx = event.get("context") or {}
    tab = ctx.get("active_browser_tab")
    if not tab or not tab.get("url"):
        return None
    url = tab["url"]
    if "//" not in url:
        return None
    host = url.split("//", 1)[1].split("/", 1)[0]
    return host.split(":")[-1] if ":" in host else host


def resolve_port_from_window_title(event):
    """Fallback to resolve port from L2 active_app window_title when L3 tab URL is missing."""
    ctx = event.get("context") or {}
    active_app = ctx.get("active_app") or {}
    title = active_app.get("window_title", "")
    for sys_name, port in SYSTEM_TITLE_TO_PORT.items():
        if sys_name in title:
            return port
    return None


def resolve_host_or_port(event):
    """Attempts L3 tab URL resolution first, falling back to L2 window title mapping."""
    return active_tab_host(event) or resolve_port_from_window_title(event)


def _nearest_preceding_app_switch(events, before_ts, claimed_timestamps, lookback_sec=30, not_before_ts=None):
    """
    Return the timestamp (str) of the app_switch event closest to (but
    before) before_ts, within lookback_sec, EXCLUDING any timestamp
    already present in claimed_timestamps, and never earlier than
    not_before_ts if given.
    """
    before_dt = parse(before_ts)
    lookback_floor = before_dt - timedelta(seconds=lookback_sec)
    not_before_dt = parse(not_before_ts) if not_before_ts else None
    lower_bound = max(lookback_floor, not_before_dt) if not_before_dt else lookback_floor

    best_ts = None
    best_dt = None
    for e in events:
        if e["event_type"] != "app_switch":
            continue
        ts = e["timestamp_iso"]
        if ts in claimed_timestamps:
            continue
        dt = parse(ts)
        if dt >= before_dt:
            break
        if dt < lower_bound:
            continue
        if best_dt is None or dt > best_dt:
            best_dt = dt
            best_ts = ts
    return best_ts


def path1_click_id_segments(events, session_id, backdate_lookback_sec=30):
    """
    Path 1: Walk browser_click events in order and pair {screen}-note (open) with
    btn-{screen}-ok (close) clicks, per screen, to emit segments.
    """
    open_segments = {}  
    last_segment_end = None
    claimed_app_switches = set()
    segments = []
    warnings = []

    for e in events:
        eid = browser_click_element_id(e)
        if not eid:
            continue
        ts = e["timestamp_iso"]

        if eid.endswith("-note"):
            screen = eid[: -len("-note")]
            if screen in open_segments:
                warnings.append(
                    f"{ts}: reopening '{screen}' while a segment was already "
                    f"open (started {open_segments[screen][0]}) -- discarding the "
                    f"earlier open, keeping this one"
                )
            open_segments[screen] = (ts, resolve_host_or_port(e))

        elif eid.startswith("btn-") and eid.endswith("-ok"):
            screen = eid[len("btn-"):-len("-ok")]
            if screen in open_segments:
                note_click_ts, note_host = open_segments.pop(screen)
                start_ts = resolve_segment_start(
                    events, note_click_ts, claimed_app_switches,
                    backdate_lookback_sec, last_segment_end,
                )
                
                label = f"{note_host}_{screen}" if note_host else screen
                segments.append({
                    "session_id": session_id,
                    "start": start_ts,
                    "end": ts,
                    "label": label,
                })
                last_segment_end = ts
            else:
                warnings.append(
                    f"{ts}: btn-{screen}-ok with nothing open for '{screen}' "
                    f"-- treated as a stray/duplicate submit, ignored"
                )

    if open_segments:
        warnings.append(
            f"session ended with {len(open_segments)} segment(s) still open "
            f"and never closed: {list(open_segments.keys())}"
        )

    return segments, warnings


def path2_coordinate_cluster_segments(events, session_id, backdate_lookback_sec=30):
    """
    Path 2: Coordinate-clustering fallback for sessions lacking L3 browser extension data.
    Uses UIA automation_id ending in '-note' to catch open state and physical mouse_click
    coordinates for submit button to catch close state.
    """
    segments = []
    warnings = []
    last_segment_end = None
    claimed_app_switches = set()

    i = 0
    n = len(events)
    while i < n:
        e = events[i]
        ext = e.get("extensions", {})
        uia = ext.get("uia_v2", {})
        aid = uia.get("target", {}).get("automation_id") or ""

        if e.get("event_type") == "mouse_click" and aid.endswith("-note"):
            screen = aid[:-len("-note")]
            note_click_event = e
            note_ts = e["timestamp_iso"]
            note_host = resolve_host_or_port(note_click_event)

            submit_event = None
            for j in range(i + 1, n):
                ev_next = events[j]
                if ev_next.get("event_type") == "mouse_click":
                    payload = ev_next.get("payload") or {}
                    coords = payload.get("coordinates") or payload.get("click_coordinates") or payload.get("position") or {}
                    x = coords.get("x", 0)
                    y = coords.get("y", 0)

                    # Submit button cluster target: x in [590, 670], y in [1845, 1885]
                    
                    if 590 <= x <= 670 and 1845 <= y <= 1885:
                        submit_event = ev_next
                        i = j
                        break

            if submit_event:
                start_ts = resolve_segment_start(
                events, note_ts, claimed_app_switches,
                backdate_lookback_sec, last_segment_end,
                )

                end_ts = submit_event["timestamp_iso"]
                label = f"{note_host}_{screen}" if note_host else screen

                segments.append({
                    "session_id": session_id,
                    "start": start_ts,
                    "end": end_ts,
                    "label": label
                })
                last_segment_end = end_ts
            else:
                warnings.append(f"{note_ts}: note field opened for '{screen}' but no submit click was found")

        i += 1

    return segments, warnings


def segment_session(session_dir):
    """Top-level entry point: dispatches to path1 or path2 depending on L3 data availability."""
    session_id = os.path.basename(session_dir.rstrip("/\\"))
    events = load_session_events(session_dir)
    if session_has_l3_data(events):
        return path1_click_id_segments(events, session_id)
    else:
        return path2_coordinate_cluster_segments(events, session_id)


def run_on_dataset_b(dataset_b_dir, out_path="segments.jsonl", skip_no_l3=False):
    """Run detector across every session in dataset_b_dir and write out_path."""
    session_dirs = sorted(glob.glob(os.path.join(dataset_b_dir, "ses_*")))
    all_segments = []
    total_warnings = 0

    with open(out_path, "w", encoding="utf-8") as out:
        for session_dir in session_dirs:
            session_id = os.path.basename(session_dir.rstrip("/\\"))
            events = load_session_events(session_dir)

            if not session_has_l3_data(events) and skip_no_l3:
                print(f"{session_id}: no L3 data, SKIPPED")
                continue

            segments, warnings = segment_session(session_dir)
            for seg in segments:
                out.write(json.dumps(seg, ensure_ascii=False) + "\n")
            all_segments.extend(segments)
            total_warnings += len(warnings)

            print(f"{session_id}: {len(segments)} segments, {len(warnings)} warnings")
            for w in warnings:
                print(f"    {w}")

    print(f"\nTotal: {len(all_segments)} segments written to {out_path}")
    print(f"Total warnings across all sessions: {total_warnings}")
    return all_segments


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python dataset_b_detector.py <path/to/dataset_b> [out.jsonl]")
        sys.exit(1)

    dataset_b_dir = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "segments.jsonl"
    run_on_dataset_b(dataset_b_dir, out_path)