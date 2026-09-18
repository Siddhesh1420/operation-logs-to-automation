## Student Information
- Name: Siddhesh Bansal
- University: Indian Institute of Technology Bhilai
- Department- Computer Science and Engineering
- Branch- Data Science and Artificial Intelligence 
- Email address- siddheshb@iitbhilai.ac.in




# Operation Logs → Automation Proposal

FDE intern selection task. Recovers units of work from raw PC operation
logs, analyses what work is being done, and delivers an automation
prototype for the highest-impact process.

## Deliverables

| Deliverable | Location |
|---|---|
| Step 1 output (Dataset B segmentation) | `segments.jsonl` |
| Step 2 analysis + prioritised candidates | `reports/step2_analysis.md` |
| Step 3 prototype | `src/automation/` |
| Final report (4 required sections) | `reports/final_report.md` |
| Daily work log | `WORKLOG.md` |

`segments.jsonl` contains **681 segments across all 15 Dataset B sessions**,
covering 12 host-qualified processes, with zero overlapping segments and
56.36 minutes of active portal execution time.

## Results summary

**Step 1.** Dataset A and Dataset B required separate segmenters, because the
signal that works on one does not exist in the other:

- **Dataset A** has zero L3 (browser extension) events across all 63 sessions,
  but exposes case identity inside UIA `automation_id` values
  (`rt-row-RT-175009-002`). Detector scores **F1 = 0.899** (precision 0.97,
  recall 0.83) at ±15s tolerance across all 63 sessions.
- **Dataset B** is the reverse: 14 of 15 sessions carry L3 `browser_click`
  events, but its `automation_id` values are generic screen labels with no
  case identity. Boundaries come from a DOM state machine
  (`{screen}-note` opens a case, `btn-{screen}-ok` closes it). The one
  session without L3 data falls back to UIA field events plus submit-click
  coordinate clustering.

Labels are host-qualified (`{port}_{screen}`) because three separate backend
systems on ports 5132/5133/5134 emit **identical element ids** for different
business processes — `pi` alone is payroll on one system, invoice matching on
another and inventory adjustment on a third. Collapsing them would have
overstated the top candidate by 2.1×.

**Step 2.** `5132_pi` (Payroll / Salary Change Registration) ranks first:
129 executions, 11.62 active minutes (20.6% of all portal labour), across 11
of 15 sessions, with raw click-to-submit variance of CV = 0.053 confirming
deterministic, non-branching interaction.

**Step 3.** An event-driven file watcher triggers a direct-injection automator
for `5132_pi`. The submission step is simulated rather than wired to a live
system — the portal in the logs is a local test harness, not a real
enterprise system. See `reports/final_report.md` Sections 2 and 4.

## Layout

```
segments.jsonl              Step 1 deliverable (Dataset B)
src/
  segmentation/
    dataset_a_detector.py   Dataset A: UIA case-id extraction + scorer
    dataset_b_detector.py   Dataset B: DOM state machine + coordinate fallback
  analysis/
    step2_analysis.py           volume / duration / variance per process
    step2b_isolate_variance.py  separates dwell time from in-portal time
    step2c_slow_tail_check.py   row-level p90 audit for branching behaviour
    check_crosssystem_v2.py     cross-system contamination check
  automation/
    pi_5132_automator.py    Step 3 prototype (5132_pi)
    file_parser.py          .jsonl/.json/.csv/.tsv/.xlsx ingestion
    file_watcher.py         filesystem-event trigger
tests/
  test_multiformat_parity.py  all input formats agree on real data
reports/
  step2_analysis.md         Step 2 analysis and candidate ranking
  final_report.md           The four required report sections
WORKLOG.md                  Daily log: what was tried, what failed, why
data/                       Datasets (gitignored — see data/README.md)
```

## Setup

Python 3.9+.

```bash
pip install -r requirements.txt
```

Steps 1 and 2 use only the standard library; the dependencies are needed
for the Step 3 prototype.

Datasets are not in this repository (they contain personal names and total
~180k events). Place them locally as `data/dataset_a/` and
`data/dataset_b/` — see `data/README.md` for the expected layout.

## Running

Step 1 — regenerate the Dataset B deliverable:

```bash
python -m src.segmentation.dataset_b_detector data/dataset_b segments.jsonl
```

Step 1 — validate the Dataset A approach against ground truth:

```bash
python -m src.segmentation.dataset_a_detector data/dataset_a
```

Step 2 — process metrics and variance analysis:

```bash
python src/analysis/step2_analysis.py segments.jsonl
python src/analysis/step2b_isolate_variance.py data/dataset_b segments.jsonl
python src/analysis/step2c_slow_tail_check.py data/dataset_b segments.jsonl
```

Step 3 — run the prototype directly, or via the file watcher:

```bash
# batch over the deliverable
python src/automation/pi_5132_automator.py --file segments.jsonl

# single case
python src/automation/pi_5132_automator.py --case PAY-2026-0001

# event-driven: start the watcher, then drop a file into incoming_data/
python src/automation/file_watcher.py
```

Tests — verifies every supported input format produces identical output on
the real deliverable, including a file round-tripped through Excel:

```bash
python tests/test_multiformat_parity.py
```

## Known limitations

These are stated in full in `reports/final_report.md`; in brief:

- The Step 3 submission step is simulated, not a live call. The target in the
  logs is a local test harness (`127.0.0.1:5132`), so the real system's API,
  authentication and DOM structure are unknown from log data alone.
- Multi-format ingestion is verified against data this pipeline generated.
  Client-specific edge cases (localised date formats, local-timezone
  timestamps) are not yet exercised — see final report, Risk 5.
- Operator headcount cannot be confirmed from Dataset B — `machine_id` and
  `username_hash` identify the recording device, not verified staff.
- Dataset A's detector does not cover document-centric processes (~17% of
  its cases), which never expose row-level `automation_id` values.
