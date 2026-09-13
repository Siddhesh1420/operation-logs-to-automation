"""
Dataset A boundary detector -- validated on Day 2.

Dataset A has ZERO L3 (browser extension) events across all 63 sessions
(confirmed by direct check, not assumed). It DOES expose structured UI
identifiers through extensions.uia_v2.target.automation_id even on
ordinary L2 events, and some of these are formatted as
"{screen_prefix}-row-{case_id}" (e.g. "rt-row-RT-175009-002"). The first
timestamp each case_id appears is a strong, precise boundary signal.

This is a VALIDATION-ONLY tool. Dataset A is not the task deliverable
(Dataset B's segments.jsonl is) -- this module exists to demonstrate and
score the approach against ground truth, and to document what was tried
and rejected along the way.

Full-dataset results (63 sessions, tolerance=15s), see WORKLOG.md Day 2:
    automation_id-only : precision=0.97  recall=0.83  F1=0.899
    hybrid w/ fallback  : precision=0.45  recall=0.92  F1=0.607

automation_id-only was chosen over the hybrid despite lower recall,
because false positives (hybrid's weak point) corrupt Step 2's
frequency/duration analysis more than false negatives do (a missed
segment just undercounts an existing process; a false one invents one
that never happened).

Known gap: ~17% of gt cases (process codes LA, SUP, and one PI execution
in the session studied) are NOT covered by this signal at all -- those
processes spend their active time in Word/Excel/Notepad documents rather
than clicking rows in the three browser-portal systems, and never expose
this automation_id pattern. This is a documented limitation, not
silently patched over with a lower-confidence guess.

Rejected approaches (kept here as a record, not because they're used):
  - Idle-gap thresholds: rejected because switched_out->started pairs in
    gt.jsonl have ~2-3ms gaps; no meaningful dead time exists between
    real process boundaries in this dataset.
  - Dwell-time-based "utility app" suppression: rejected because
    measurement showed utility apps (e.g. m1_reference-Excel) can have
    LONGER median dwell than genuine "home" apps -- no clean threshold.
  - App-transition-graph connectivity ("hub" detection): rejected
    because home apps showed equal-or-higher distinct in/out-degree than
    utility apps in direct measurement.
  - Global shortest-shortcut-n-gram mining: rejected because mining the
    single most frequent n-gram across a whole session conflates
    different processes' distinct motifs and fires on every occurrence
    of a common short pattern, not just case-to-case seams. Measured
    result was WORSE than the plain baseline (F1 0.192 vs 0.247 at
    comparable settings).
"""
import json
import glob
import re
from datetime import datetime


CASE_ID_RE = re.compile(r'-([A-Z]{2,4}-\d{4,8}-\d{3,4})$')


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


def automation_id_case_boundaries(events):
    """
    Scan events for extensions.uia_v2.target.automation_id values matching
    "...-{CASE_ID}" (e.g. "rt-row-RT-175009-002") and return a dict of
    case_id -> first timestamp (as a datetime) that case_id was seen.

    This first-seen timestamp is the primary Step 1 boundary signal for
    Dataset A: it directly names the case being interacted with, rather
    than inferring a boundary from behavioral timing.
    """
    first_seen = {}
    for e in events:
        ext = e.get("extensions", {})
        uia = ext.get("uia_v2", {})
        target = uia.get("target", {})
        aid = target.get("automation_id")
        if not aid:
            continue
        m = CASE_ID_RE.search(aid)
        if not m:
            continue
        case_id = m.group(1)
        dt = parse(e["timestamp_iso"])
        if case_id not in first_seen or dt < first_seen[case_id]:
            first_seen[case_id] = dt
    return first_seen


def dedup_app_switches(events):
    """
    Filter app_switch events, dropping self-transitions where new_app and
    previous_app share the same (process_id, window_title) -- a confirmed
    recording/UIA-polling artifact (Day 1 finding), not a real switch.
    app_name alone is NOT a safe key: distinct windows/processes can share
    the same app_name (e.g. multiple Chrome windows).
    """
    out = []
    for e in events:
        if e.get("event_type") != "app_switch":
            continue
        na = e["payload"]["new_app"]
        pa = e["payload"]["previous_app"]
        is_dup = (na["process_id"], na["window_title"]) == (pa["process_id"], pa["window_title"])
        if not is_dup:
            out.append(e)
    return out


def load_gt_executions(session_dir):
    """Load Dataset A ground truth executions from gt_manifest.json."""
    with open(session_dir + "/gt_manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)
    execs = []
    for proc in manifest["processes"]:
        for ex in proc["executions"]:
            execs.append({
                "code": proc["code"],
                "case_id": ex["case_id"],
                "start_ts": parse(ex["start_ts"]),
            })
    return execs


def score(candidate_timestamps, gt_execs, tolerance_sec=15.0):
    """
    Greedy nearest-match scoring: each gt execution is matched to at most
    one candidate timestamp within tolerance_sec, each candidate used at
    most once. Returns (precision, recall, f1, matched_cand, total_cand,
    matched_gt, total_gt).
    """
    matched_gt, matched_cand = set(), set()
    for i, ex in enumerate(gt_execs):
        g = ex["start_ts"]
        best_j, best_diff = None, None
        for j, c in enumerate(candidate_timestamps):
            if j in matched_cand:
                continue
            diff = abs((c - g).total_seconds())
            if diff <= tolerance_sec and (best_diff is None or diff < best_diff):
                best_j, best_diff = j, diff
        if best_j is not None:
            matched_gt.add(i)
            matched_cand.add(best_j)

    total_cand = len(candidate_timestamps)
    total_gt = len(gt_execs)
    precision = len(matched_cand) / total_cand if total_cand else 0.0
    recall = len(matched_gt) / total_gt if total_gt else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1, len(matched_cand), total_cand, len(matched_gt), total_gt


def run_on_session(session_dir, tolerance_sec=15.0):
    """Convenience: run the detector + scorer on one Dataset A session."""
    events = load_session_events(session_dir)
    gt_execs = load_gt_executions(session_dir)
    first_seen = automation_id_case_boundaries(events)
    candidates = list(first_seen.values())
    return score(candidates, gt_execs, tolerance_sec=tolerance_sec)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python dataset_a_detector.py <path/to/dataset_a>")
        sys.exit(1)

    dataset_a_dir = sys.argv[1]
    session_dirs = sorted(glob.glob(dataset_a_dir + "/ses_*"))

    agg = {"mc": 0, "tc": 0, "mg": 0, "tg": 0}
    for session_dir in session_dirs:
        p, r, f1, mc, tc, mg, tg = run_on_session(session_dir)
        agg["mc"] += mc
        agg["tc"] += tc
        agg["mg"] += mg
        agg["tg"] += tg
        print(f"{session_dir}: precision={p:.2f} recall={r:.2f} f1={f1:.3f}")

    p = agg["mc"] / agg["tc"] if agg["tc"] else 0.0
    r = agg["mg"] / agg["tg"] if agg["tg"] else 0.0
    f1 = (2 * p * r / (p + r)) if (p + r) else 0.0
    print(f"\nAGGREGATE over {len(session_dirs)} sessions: "
          f"precision={p:.2f} recall={r:.2f} f1={f1:.3f}")
