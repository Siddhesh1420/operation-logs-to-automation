"""
Dataset B boundary detector -- DESIGN SPEC ONLY, not yet implemented.
See WORKLOG.md Day 2 (cont'd) for the full investigation this is based on.

Dataset B is the actual Step 1 deliverable (segments.jsonl at repo root).
Unlike Dataset A, most Dataset B sessions have real L3 (browser
extension) data, and Dataset A's automation_id-case-ID approach does NOT
transfer here -- B's automation_ids are generic per-screen field labels
(pi-note, la-note, rt-note, si-note, ob-note) with no case identity
embedded, confirmed by direct inspection.

Two-path design, based on whether a session has L3 (browser_click) data:

PATH 1 -- primary, 14/15 sessions checked so far have L3 data:
    Use browser_click events' payload.element.attributes.id (NOT
    automation_id -- a different field, populated by the browser
    extension layer specifically).
    - id == "{screen}-note"       -> start of a case on that screen
    - id == "btn-{screen}-ok"     -> end/submit of that case
    Validated on TWO separate sessions with near-1:1 and then an EXACT
    1:1 note:ok click ratio across all five screens (pi/la/rt/si/ob) in
    the second session. This is the strongest, most direct signal found
    across either dataset this week.

    Open question (not yet checked): whether all 14 L3-having sessions
    expose all five screen types, or only a subset per session (the
    first session checked only showed 4 of 5: pi/la/rt/si, no ob).

PATH 2 -- fallback, 1/15 sessions confirmed to have ZERO L3 events
    (ses_20260701-192455-NEELA9BAF, the only one found so far; there may
    be no others, but this was only confirmed by checking L3 counts
    across all 15 sessions, not assumed):
    automation_id STILL exposes "{screen}-note" via UIA even without the
    browser extension (UIA operates independently of the extension), but
    the submit/OK button has no captured automation_id in this session.
    Traced manually: the submit action is a mouse_click at a consistent,
    repeatable (x, y) screen coordinate shortly after each note-field
    click + clipboard paste. Proposed rule: cluster mouse_click
    coordinates; a click landing within a small tolerance of the same
    (x, y) region as another click already seen for that screen is
    treated as that screen's submit action, functionally equivalent to
    Path 1's btn-{screen}-ok id-based match.
    STATUS: conceptually validated on one motif, by hand. NOT yet
    implemented as code. Coordinate tolerance not yet chosen/tested.

Because Dataset B has no ground truth, this detector cannot be scored the
way dataset_a_detector.py is. Validation will be by spot-checking a
sample of emitted segments against context.extracted_text and/or
screenshots for plausibility, per the task's own FAQ ("we will score
your submission after you submit it").
"""
import json
import glob


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
    NOTE: this is payload.element.(attributes.id or id) -- a different
    field from extensions.uia_v2.target.automation_id used in Dataset A.
    """
    if event.get("event_type") != "browser_click":
        return None
    elem = event.get("payload", {}).get("element") or {}
    attrs = elem.get("attributes") or {}
    return attrs.get("id") or elem.get("id")


def path1_click_id_segments(events):
    """
    NOT YET IMPLEMENTED.

    Intended behavior: walk browser_click events in order; for each
    "{screen}-note" click, open a candidate segment on that screen; close
    it at the next "btn-{screen}-ok" click for the same screen. Emit
    (screen, start_ts, end_ts) tuples.

    Needs decisions before implementation:
    - What to do if a "{screen}-note" click repeats before its matching
      "btn-{screen}-ok" (multiple note edits within one case, expected
      per the observed 1:1 pairing being note-events == ok-events, not
      necessarily 1 note-click per case)
    - Whether segments from different screens can interleave (operator
      switches screens mid-case) and how that should be represented
    """
    raise NotImplementedError("Day 3 task -- see module docstring for design")


def path2_coordinate_cluster_segments(events, coord_tolerance_px=15):
    """
    NOT YET IMPLEMENTED.

    Intended behavior: for a no-L3 session, cluster mouse_click
    coordinates seen shortly after "{screen}-note" automation_id clicks;
    treat repeated clicks within coord_tolerance_px of each other as the
    same logical "submit" action, closing a segment the same way
    path1 does with btn-{screen}-ok.

    coord_tolerance_px is a guess, not yet validated against real
    variance in click position (button rendering may shift slightly
    frame to frame; needs checking against real data before trusting the
    default).
    """
    raise NotImplementedError("Day 3 task -- see module docstring for design")


def segment_session(session_dir):
    """
    Top-level entry point (NOT YET FUNCTIONAL): dispatches to path1 or
    path2 depending on whether the session has L3 data.
    """
    events = load_session_events(session_dir)
    if session_has_l3_data(events):
        return path1_click_id_segments(events)
    else:
        return path2_coordinate_cluster_segments(events)


if __name__ == "__main__":
    import sys
    print("Design spec only -- see module docstring. Not yet runnable.")
    print("Next step: implement path1_click_id_segments and validate against")
    print("a sample of Dataset B sessions by spot-checking extracted_text.")
