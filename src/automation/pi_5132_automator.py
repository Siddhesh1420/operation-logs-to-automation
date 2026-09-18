"""
Step 3 Automation Prototype: HR Payroll Change (5132_pi)
Target Host: Port 5132 | Target Element: pi-note | Submit Action: pi-ok

Executes deterministic direct payload injection, bypassing manual UI field focus,
clipboard transfers, and submit button latency.

NOTE ON SCOPE (prototype, not production):
- execute_transaction() simulates injection latency via time.sleep(); it does
  not make a real HTTP/DOM call against port 5132. This is acceptable per
  project scope ("a working prototype is sufficient, not production-ready").
- Payload content is a placeholder string, not real case data, because
  segments.jsonl only carries boundary/timing metadata (session_id, start,
  end, label), not per-case field content. Real field automation would
  require extending the data pipeline to capture that content -- out of
  scope for this prototype.

NOTE ON BASELINE (fixed 2026-09-17):
- Compares against human_in_portal_raw_sec (2.80s, the isolated click-to-
  submit action) rather than human_baseline_avg_sec (5.40s backdated mean,
  which includes ~2.60s of human reference-lookup/reading time this
  automation does not replace). Using the backdated mean overstated the
  speedup as ~360x; the corrected comparison is ~98% / ~187x on the
  portion of the task actually automated. See step2_analysis.md Section 5
  for the same correction applied to the written report.
- total_active_minutes_saved is now computed from each segment's REAL
  duration (parsed from segments.jsonl start/end), not count * constant
  average -- so this number is traceable to the validated segments.jsonl
  figure (11.62 min for 5132_pi) rather than an approximation.
"""
import argparse
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class HR5132PIAutomator:
    """Automated transaction runner for 5132_pi (Payroll / Salary Change Registration)."""

    def __init__(self, target_host: str = "http://127.0.0.1:5132"):
        self.target_host = target_host
        self.human_in_portal_raw_sec = 2.80
        self.simulated_injection_sec = 0.015

    def execute_transaction(self, case_id: str, note_text: str,
                             human_actual_sec: Optional[float] = None) -> Dict[str, Any]:
        """
        Simulates direct API / DOM payload submission to Port 5132.

        human_actual_sec: this specific case's real backdated segment
        duration (start->end from segments.jsonl), used only for the
        per-transaction report; the speedup/efficiency metrics below
        compare against the raw click-to-submit baseline, not this value,
        since that raw baseline is what the automation mechanically replaces.
        """
        t_start = time.perf_counter()

        payload = {
            "screen_id": "pi",
            "case_id": case_id,
            "field_automation_id": "pi-note",
            "content": note_text,
            "submit_action": "pi-ok",
            "timestamp_iso": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

        time.sleep(self.simulated_injection_sec)

        elapsed_sec = time.perf_counter() - t_start
        baseline = self.human_in_portal_raw_sec

        return {
            "status": "SUCCESS",
            "transaction_id": f"TX-{case_id}",
            "payload_submitted": payload,
            "metrics": {
                "automated_execution_sec": round(elapsed_sec, 4),
                "human_raw_click_baseline_sec": baseline,
                "human_actual_backdated_sec": human_actual_sec,
                "time_saved_vs_raw_click_sec": round(baseline - elapsed_sec, 4),
                "efficiency_gain_pct_vs_raw_click": round(
                    ((baseline - elapsed_sec) / baseline) * 100, 2
                ),
            },
        }

    def batch_process_records(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Executes batch automation using REAL per-segment durations from segments.jsonl."""
        pi_segments = [r for r in records if r.get("label") == "5132_pi"]

        results = []
        total_saved_vs_raw_sec = 0.0
        total_real_human_sec = 0.0  

        for idx, seg in enumerate(pi_segments, 1):
            case_id = f"PAY-2026-{idx:04d}"

            real_dur_sec = None
            if "start" in seg and "end" in seg:
                real_dur_sec = (parse_iso(seg["end"]) - parse_iso(seg["start"])).total_seconds()
                total_real_human_sec += real_dur_sec

            res = self.execute_transaction(
                case_id, f"Automated salary update for segment {idx}",
                human_actual_sec=real_dur_sec,
            )
            results.append(res)
            total_saved_vs_raw_sec += res["metrics"]["time_saved_vs_raw_click_sec"]

        total_records = len(results)
        total_auto_time_sec = sum(r["metrics"]["automated_execution_sec"] for r in results)

        return {
            "process_target": "5132_pi (Payroll / Salary Change Registration)",
            "total_records_processed": total_records,
            "total_active_minutes_actual_human_time": round(total_real_human_sec / 60, 4),
            "aggregate_automated_hours_consumed": round(total_auto_time_sec / 3600, 4),
            "projected_minutes_saved_vs_raw_click": round(total_saved_vs_raw_sec / 60, 2),
            "note_on_dwell_time": (
                "This figure excludes ~2.60s/case of human reference-lookup "
                "time, which this automation does not eliminate (see "
                "step2_analysis.md Section 5, Recommendation #1)."
            ),
            "average_speedup_factor_vs_raw_click": round(
                self.human_in_portal_raw_sec / self.simulated_injection_sec, 1
            ) if total_records > 0 else 0,
            "sample_execution_record": results[0] if results else {},
        }

    def batch_process_segments(self, segments_file: str = "segments.jsonl") -> Dict[str, Any]:
        """Reads segments.jsonl file and delegates to batch_process_records."""
        if not os.path.exists(segments_file):
            print(f"Error: Segment file '{segments_file}' not found.")
            return {}

        records = []
        with open(segments_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))

        return self.batch_process_records(records)


def main():
    parser = argparse.ArgumentParser(description="Automator Prototype for Process 5132_pi")
    parser.add_argument("--file", default="segments.jsonl", help="Path to segments file")
    parser.add_argument("--case", help="Single case ID for manual execution")
    parser.add_argument("--note", default="Standard payroll adjustment", help="Note text")

    args = parser.parse_args()
    automator = HR5132PIAutomator()

    if args.case:
        result = automator.execute_transaction(args.case, args.note)
        print(json.dumps(result, indent=2))
    else:
        summary = automator.batch_process_segments(args.file)
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()