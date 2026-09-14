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
                                      screen and emits it. Verified
                                      (Day 3 spot-check) that nothing
                                      meaningful happens in the 6s after
                                      this click other than the next
                                      case's own app_switch beginning --
                                      this timestamp is a clean, correct
                                      segment end as-is, no adjustment
                                      needed.

    START-TIME BACK-DATING (Day 3 fix): the raw "{screen}-note" click
    timestamp UNDERSTATES the true start of a case. Spot-checking
    multiple segments against context.extracted_text showed a consistent
    pattern: several seconds before the note-click (4s to ~14.5s across
    5 examples checked, in 3 different sessions), an app_switch event
    occurs whose surrounding extracted_text reveals the actual case
    content the person is about to act on (e.g. an invoice number and
    amount). The gap between that app_switch and the note-click is the
    person's review/reading time for that case -- real work time that
    the raw click-to-click window was silently excluding.

    Rule: a segment's start is the timestamp of the NEAREST app_switch
    event preceding the note-click, within a capped lookback window
    (default 30s). If no app_switch is found in that window, the
    note-click timestamp itself is used as a fallback (better to slightly
    understate a rare case than to reach arbitrarily far into unrelated
    prior activity).

    CLAIMED-TIMESTAMP FIX (Day 3, second pass): back-dating naively let
    two different segments share the SAME app_switch as their "nearest
    preceding" one, producing two segments with identical start times.
    Root cause, confirmed by inspection: sometimes two cases are
    reviewed back-to-back after a single app_switch (e.g. the person
    scrolls to the next row within the same already-open view, rather
    than switching apps again) -- so there genuinely isn't a fresh
    app_switch for the second case. Each app_switch can now back-date at
    most ONE segment: once used, it is added to a per-session "claimed"
    set and skipped by subsequent lookups. A segment whose nearest
    app_switch is already claimed falls through to the next-nearest
    unclaimed one within the lookback window, or to the raw note-click
    timestamp if none remain -- which honestly reflects that no distinct
    review moment could be detected for that case, rather than
    fabricating one.

    Screen coverage varies per session (2 to 5 of the 5 known screens:
    pi, la, rt, si, ob) -- this is expected, not a bug: sessions simply
    don't all touch every screen type.

PATH 2 -- NOT YET IMPLEMENTED. 1/15 sessions has zero L3 data
    (ses_20260701-192455-NEELA9BAF, confirmed by direct check across all
    15 sessions, not assumed to be the only one in the full Dataset B).
    automation_id still exposes "{screen}-note" via UIA even without the
    browser extension, but the submit/OK action has no captured
    automation_id there. Traced manually: the submit action is a
    mouse_click at a consistent, repeatable screen coordinate shortly
    after each note-field click + clipboard paste. Not yet implemented
    as code -- coordinate tolerance not yet chosen/tested. The same
    start-time back-dating principle (look for the preceding app_switch)
    likely applies here too, but has not yet been checked against this
    session specifically.

Because Dataset B has no ground truth, this detector cannot be scored
the way dataset_a_detector.py is. Validation is by spot-checking a
sample of emitted segments against context.extracted_text and/or
screenshots for plausibility.
"""
import json
import glob
import os
from datetime import datetime, timedelta


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
    This is payload.element.(attributes.id or id) -- a different field
    from extensions.uia_v2.target.automation_id used in Dataset A.
    """
    if event.get("event_type") != "browser_click":
        return None
    elem = event.get("payload", {}).get("element") or {}
    attrs = elem.get("attributes") or {}
    return attrs.get("id") or elem.get("id")

# Extract host/port from active_browser_tab URL safely
def _extract_host_port(event):
    ctx = event.get("context") or {}
    tab = ctx.get("active_browser_tab") or {}
    url = tab.get("url") or ""
    if "//" in url:
        # e.g., "127.0.0.1:5132"
        return url.split("//", 1)[1].split("/", 1)[0]
    return "unknown_host"


def _nearest_preceding_app_switch(events, before_ts, claimed_timestamps, lookback_sec=30, not_before_ts=None):
    """
    Return the timestamp (str) of the app_switch event closest to (but
    before) before_ts, within lookback_sec, EXCLUDING any timestamp
    already present in claimed_timestamps, and never earlier than
    not_before_ts if given. Returns None if none found.

    not_before_ts (str or None): the previous segment's own end time on
    this screen. A case can never legitimately start reviewing before
    the prior case (on the same screen) has finished -- confirmed by the
    Day 3 interleaving check (0 anomalies, strictly sequential across
    14/15 sessions). This is a hard logical bound, not a tuned parameter.
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


def path1_click_id_segments(events, session_id, backdate_lookback_sec=30,):
    """
    Walk browser_click events in order and pair {screen}-note (open) with
    btn-{screen}-ok (close) clicks, per screen, to emit segments.

    The emitted "start" is back-dated to the nearest preceding, not
    already claimed, app_switch (within backdate_lookback_sec) rather
    than the raw note-click timestamp -- see module docstring,
    "START-TIME BACK-DATING" and "CLAIMED-TIMESTAMP FIX", for the
    evidence behind this.

    Returns (segments, warnings). Each segment is a dict matching the
    segments.jsonl schema: {"session_id", "start", "end", "label"}.

    Rules (see module docstring for the evidence behind each):
    - A "{screen}-note" click opens a segment for that screen. If one is
      already open for that screen (should not happen per Day 3 checks,
      but handled defensively), the earlier one is discarded rather than
      silently overwritten, and a warning is recorded.
    - A "btn-{screen}-ok" click closes and emits the open segment for
      that screen, using its back-dated start and the click's own
      timestamp as end. If nothing is open for that screen, the click is
      treated as a stray/duplicate submit and ignored (Day 3 finding:
      confirmed this happens at least once, immediately following a
      valid pair, not at a session boundary -- i.e. a real double-click,
      not a truncation artifact).
    - Each app_switch can back-date at most one segment; once used it is
      excluded from consideration for all later segments in the session.
    """
    open_segments = {}  # screen -> raw note-click timestamp (str)
    last_segment_end=None
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
                    f"open (started {open_segments[screen]}) -- discarding the "
                    f"earlier open, keeping this one"
                )
            open_segments[screen] = ts

        elif eid.startswith("btn-") and eid.endswith("-ok"):
            screen = eid[len("btn-"):-len("-ok")]
            if screen in open_segments:
                note_click_ts = open_segments.pop(screen)
                backdated_start = _nearest_preceding_app_switch(
                    events, note_click_ts, claimed_app_switches,
                    lookback_sec=backdate_lookback_sec,
                    not_before_ts=last_segment_end
                )           
                if backdated_start:
                    claimed_app_switches.add(backdated_start)
                    start_ts = backdated_start
                else:
                    start_ts = note_click_ts
                segments.append({
                    "session_id": session_id,
                    "start": start_ts,
                    "end": ts,
                    "label": screen,
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


def path2_coordinate_cluster_segments(events, session_id, coord_tolerance_px=15):
    """
    NOT YET IMPLEMENTED. See module docstring, PATH 2.
    """
    raise NotImplementedError(
        "path2 (no-L3 fallback) is not yet implemented -- "
        "see WORKLOG.md Day 2 (cont'd) for the design notes"
    )


def segment_session(session_dir):
    """
    Top-level entry point: dispatches to path1 or path2 depending on
    whether the session has L3 data. Returns (segments, warnings).
    """
    session_id = os.path.basename(session_dir.rstrip("/\\"))
    events = load_session_events(session_dir)
    if session_has_l3_data(events):
        return path1_click_id_segments(events, session_id)
    else:
        return path2_coordinate_cluster_segments(events, session_id)


def run_on_dataset_b(dataset_b_dir, out_path="segments.jsonl", skip_no_l3=True):
    """
    Run the detector across every session under dataset_b_dir and write
    results to out_path in segments.jsonl format (one JSON object per
    line: session_id, start, end, label).

    skip_no_l3: if True (default, since path2 isn't implemented yet),
    sessions without L3 data are skipped with a printed notice rather
    than raising NotImplementedError and aborting the whole run.
    """
    session_dirs = sorted(glob.glob(os.path.join(dataset_b_dir, "ses_*")))
    all_segments = []
    total_warnings = 0

    with open(out_path, "w", encoding="utf-8") as out:
        for session_dir in session_dirs:
            session_id = os.path.basename(session_dir.rstrip("/\\"))
            events = load_session_events(session_dir)

            if not session_has_l3_data(events):
                if skip_no_l3:
                    print(f"{session_id}: no L3 data, path2 not implemented -- SKIPPED")
                    continue
                else:
                    raise NotImplementedError(f"{session_id} needs path2")

            segments, warnings = path1_click_id_segments(events, session_id)
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
