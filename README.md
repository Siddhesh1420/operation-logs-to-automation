# Operation Logs -> Automation Proposal

Intern selection task submission. See original task brief and data schema
in `docs/` (copy the provided README.md / DATA_SCHEMA.md there if you want
them versioned alongside this work — not included here since they were
provided separately).

## Layout

```
data/                   Datasets (gitignored — see data/README.md)
scratch/                 Throwaway exploration scripts, one-off checks
src/
  segmentation/          Step 1: event stream -> segments.jsonl
  analysis/               Step 2: segments -> automation candidate ranking
  automation/             Step 3: the actual prototype tool
reports/
  step2_analysis.md       Automation candidate analysis + priority ranking
  final_report.md          The four required report sections
segments.jsonl            Step 1 deliverable for Dataset B (generated)
WORKLOG.md                 Daily log: what we did, why, what failed
```

## Status

Day 1 complete — raw data exploration and manual gt-tracing on one
Dataset A session. See WORKLOG.md for findings. No segmentation code
written yet.
