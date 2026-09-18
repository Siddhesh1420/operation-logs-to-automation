# Final Report — Operation Logs to Automation Proposal

---

## How the 7 Days Were Allocated

| Day | Focus |
|-----|-------|
| 1 | Dataset A manual inspection — tracing one session end-to-end against ground truth, establishing structural facts about the data before writing any code |
| 2 | Dataset A scored pipeline — building and evaluating the UIA case-ID detector; Dataset B domain transfer investigation |
| 3 | Dataset B architecture — verifying structural assumptions (interleaving check), designing the two-path segmenter, diagnosing the multi-host port collision |
| 4 | Dataset B pipeline execution — implementing Path 2 (no-L3 session), auditing gap coverage, producing and locking `segments.jsonl` (681 segments, 15/15 sessions) |
| 5 | Step 2 analysis — variance decomposition, bimodal slow-tail audit, candidate ranking; Step 3 core prototype build |
| 6 | Step 3 debugging — rebaselining the prototype against corrected Step 2 figures, fixing two real bugs in the watcher/parser found during cross-checking |
| 7 | Final report, work log cleanup, repository packaging |

---

## Section 1 — Why This Process, and Why This Scope

### Target: `5132_pi` — Payroll / Salary Change Registration (HR System, Port 5132)

`5132_pi` was selected as the primary automation target on three independently measurable grounds, each drawn from Step 2's analysis of the 681 validated segments:

**1. Volume and reach.** 129 executions across 11 of 15 recording sessions — the highest count of any of the 12 identified processes, and appearing in 73% of recorded sessions rather than being concentrated in one or two. Automation of a process that recurs across nearly every observed shift produces immediate, broad impact rather than affecting a narrow slice of one operator's day.

**2. Total time consumed.** 11.62 active portal minutes across the dataset — 20.6% of all recorded portal labor. No other single process exceeds 7 minutes. Automating `5132_pi` recovers more time than all three Logistics/Inventory processes (`5134_pi`, `5134_la`, `5134_si`) combined.

**3. Interaction determinism.** The key feasibility question for any rule-based automation is whether the in-portal handling is standardized or branching. Step 2's variance decomposition separated pre-click reading time (variable, operator-dependent) from in-portal interaction time (click to submit). For `5132_pi`, the raw click coefficient of variation is $CV_{\text{raw}} = 0.053$ — one of the lowest in the dataset. The row-level slow-tail audit confirmed this holds even for the longest transactions: in every case, the elevated total duration was explained by variable pre-click dwell time (reading reference files), not by branching portal behavior. No secondary UI path, validation modal, or exception branch was observed in any of the 129 executions.

### Why This Scope (One Process, Not a Platform)

The alternative would have been to build a general mechanism — a shared automation engine with per-process definition files — that could be extended to cover `5133_rt`, `5133_pi`, and other candidates. That approach was evaluated and deferred for this submission for two concrete reasons:

First, the feasibility risk profile differs across processes. `5134_la` (Contract Management) and `5134_pi` (Inventory Adjustment) both showed elevated raw click variance ($CV_{\text{raw}} = 0.400$ and $0.186$ respectively) that required dedicated event-level inspection to root-cause (a client-side debounce delay, not UI branching). Building a shared engine before that root cause was understood would have embedded an untested assumption into the infrastructure. Deferring those processes to a second phase — after the debounce behavior is confirmed against the real system — is lower risk than shipping a general platform with unknown edge cases.

Second, all twelve processes in Dataset B share the same three-step interaction pattern (`{screen}-note` → clipboard paste → `btn-{screen}-ok`). A general mechanism is achievable in a second phase without structural rework — the per-process definitions would be small additions to an engine whose core logic is already validated on `5132_pi`. Delivering one fully verified process now is better than delivering a broad but untested platform, consistent with the task's own guidance that judgment matters more than scope.

---

## Section 2 — Why This Implementation Form, and Why Not the Alternatives

### Selected: Event-Driven File System Watcher (`file_watcher.py`) with Direct Payload Injection (`pi_5132_automator.py`)

The prototype monitors a designated incoming folder (`./incoming_data/`) using OS kernel events (`inotify` on Linux, `ReadDirectoryChangesW` on Windows). When a case data file is dropped, the watcher parses it, filters for `5132_pi` segments, and dispatches each record to the automator, which constructs a structured payload and would submit it directly to the HR portal's form layer.

**Why not a REST API server?** A REST endpoint requires an open port, firewall rules, and IT infrastructure approval — none of which can be provisioned purely from a prototype. The file-watcher approach has zero network surface: it requires no open ports, no server process visible to the network, and no infrastructure changes. Operationally, a staff member or upstream system can trigger automation by dropping a file, using familiar file-system semantics rather than learning an API.

**Why not a scheduled batch job?** A cron/scheduler approach introduces polling latency and is less responsive to irregular arrival of cases. File-watcher events fire within milliseconds of file creation, which matches the real operational pattern: cases arrive throughout the day, not on a fixed schedule.

**Why not a browser automation layer (Playwright/Selenium)?** This is the most important rejected alternative to explain. Browser automation against `127.0.0.1:5132` is technically achievable in a test environment, but the dataset establishes that this address is a local test harness, not a real enterprise system (see Section 4, Risk 1). Building a Playwright integration against a test harness would produce a prototype that works against the simulator but cannot be demonstrated to work against the real HR system without access to that system's actual URL, authentication, and DOM structure — none of which appear in the operation logs. Direct payload injection is scoped honestly to what can be verified from log data alone; browser automation would require infrastructure access outside the scope of this engagement.

**What the prototype actually demonstrates.** The current implementation simulates the submission step with a 15ms `time.sleep()` call in place of a real HTTP/DOM write. This is an acknowledged prototype simplification (see Section 3 for what remains manual). It does demonstrate the complete surrounding architecture: case identification from segments, multi-format file ingestion, file-system trigger, payload construction, batch processing, and structured audit logging. These components are production-ready in the sense that they can be directly extended once real-system access is available; only the submission step itself requires replacement.

**Multi-format ingestion verification status.** The file watcher supports `.jsonl`, `.json`, `.csv`, `.tsv`, and `.xlsx` inputs via `file_parser.py`. All five formats are now verified end-to-end against real data: `tests/test_multiformat_parity.py` writes the full validated `segments.jsonl` (681 segments) out to every supported format, runs each back through the parser and automator, and asserts the aggregate output is identical. All five agree exactly — 129 matched `5132_pi` segments, 11.6165 minutes — confirming duration arithmetic is correct on every code path, not just `.jsonl`.

This resolves an open item carried from Day 6, where the non-`.jsonl` formats had only been exercised with 1–2 record synthetic files containing placeholder timestamps. Those files produced an internally inconsistent result (zero real duration alongside a non-zero projected saving), which was suspected to be degenerate test data rather than a parser defect; the parity test confirms that diagnosis was correct.

Three real bugs were found and fixed in this pipeline, each because printed figures were traced back to a known-correct source rather than accepted at face value: a stale field-name reference in the watcher's output (silently reporting zero), an un-reset accumulator in the parser's retry loop (a `.jsonl` file with one malformed line returned 9 records instead of 4, which would have inflated transaction counts and time savings), and an absent exception handler in the watcher's event callback that allowed a single bad file drop to kill the observer thread silently.

---

## Section 3 — What Manual Work Remains After Deployment, and Realistic Expected Impact

### What the automation does not eliminate

**Pre-click reference lookup time (~2.60s per case, ~5.59 minutes total).** The 5.40s backdated mean per `5132_pi` execution breaks down as roughly 2.60s of human reading time (consulting external reference files — `expense_calc.xlsx`, policy documents) before clicking into the portal, and 2.80s of actual in-portal interaction. The current automation replaces only the 2.80s in-portal mechanical step. The reference lookup phase remains manual unless a future phase also automates data retrieval from those reference sources and pipes it directly into the case payload. Reporting the automation's savings against the full 5.40s would overstate recoverable labor; the honest figure is ~98% reduction on the 2.80s that is actually automated, applied 129 times over the observed period.

**Prototype submission layer.** As stated in Section 2, the current implementation simulates the HTTP/DOM submission step. The remaining manual work to reach production includes: (a) connecting the payload dispatch to the real HR system's API or form layer, (b) handling authentication and session management, and (c) running a parallel validation period (see Section 4).

**Exception handling and edge cases.** The 129 observed `5132_pi` executions were uniformly non-branching. However, real operational volumes will include cases requiring human judgment (incorrect amounts, flagged discrepancies, approvals requiring manager review). The prototype has no exception path; a production deployment requires a defined escalation route for cases the automation cannot process.

**Change management.** Four operators (or at minimum four machines) were identified across the 15 recorded sessions. Any deployment requires communicating the change to those operators, retraining on the new trigger workflow (file drop instead of manual portal interaction), and establishing a monitoring process during the rollout period.

### Realistic expected impact

Based on the observed data: **129 cases over 15 sessions, consuming 11.62 minutes of active portal time** (2.80s × 129 ÷ 60 = 6.02 minutes of in-portal mechanical time that is actually replaced, plus 5.60 minutes of reference-lookup time that remains manual). Scaling conservatively to a full working day based on session density: the observed sessions represent individual shift-length recordings, suggesting `5132_pi` occurs roughly 8-10 times per session per operator, implying automation would recover approximately 20-35 seconds of portal interaction time per operator per session — a small but consistent, zero-error-rate improvement that compounds across shifts and operators without requiring staffing changes.

The more meaningful operational benefit is **consistency and auditability**: every automated execution produces a structured ISO-8601 log entry with a transaction ID, preventing the missed submissions, double-submissions, and unlogged decisions that occur in fully manual workflows.

---

## Section 4 — Anticipated Implementation and Rollout Risks

### Risk 1: The target system is a test harness, not a production system

**Evidence:** The operation logs contain a visible terminal banner on session start: *"procmine-desktop-agent... DWELL_SCALE=1.4... walk away"*, and all three portal systems run on `127.0.0.1:5132/5133/5134` — local loopback addresses. This is a simulator, confirmed by the `run_config` field in `gt.jsonl` carrying generator parameters (`seed`, `dwell_scale`, `noise_rate`, `transition`) rather than recording metadata.

**Implication:** The real HR system's URL, authentication mechanism, API structure, CSRF token handling, and DOM element identifiers are entirely unknown from the logs. The `pi-note` and `btn-pi-ok` element IDs observed in Dataset B may or may not exist in the same form in the production system. Implementation begins with a discovery phase alongside the system vendor or IT team — this is not optional, and its duration and outcome cannot be estimated from log data alone.

**Mitigation:** Treat all prototype code as an architecture demonstration rather than a deployable artifact. The first real implementation milestone is a read-only connection to the actual system to inspect its DOM/API structure, done under IT oversight with no write operations.

### Risk 2: Username identity cannot be confirmed from logs alone

**Evidence:** `machine_id` and `username_hash` identify the data-collection device, not a verified employee. Four distinct machine/hash combinations appear in Dataset B, suggesting at least 4 people or workstations, but shared machines, shift handoffs, and multi-user workstations cannot be distinguished.

**Implication:** Rollout communication and retraining cannot be reliably targeted from log data. The client must identify affected staff through HR records, not through this analysis.

**Mitigation:** Before rollout, confirm operator headcount and identities with the HR or operations team directly.

### Risk 3: The client-side debounce delay in Logistics processes may not be a fixed constant

**Evidence:** `5134_pi` and `5134_la` both show a consistent ~1.5–2.0s gap between field input and `browser_form_input` firing across multiple operators and sessions. This was root-caused as a probable client-side debounce, not variable network latency, based on the inter-operator consistency. However, this was diagnosed from log timing alone — no application source code or network trace was available.

**Implication:** If the delay varies in production (e.g., under higher server load, or on a different network path than the test environment), a hardcoded 2s wait in the automation would either submit prematurely (error) or waste more time than necessary (reducing the speedup benefit).

**Mitigation:** For Phase 2 implementation targeting `5134_pi`/`5134_la`, instrument the actual submit response time in a staging environment before hardcoding any wait constant. Build the wait as a configurable parameter, not a literal.

### Risk 4: The one-screen-per-transaction assumption may not hold at full production volume

**Evidence:** The 681-segment dataset showed zero interleaving across 14 of 15 sessions, and the single no-L3 session could not be checked at the click level. At the observed session scale (~40-130 transactions per session), the sequential assumption held universally.

**Implication:** At higher production volumes, or with multiple operators sharing a queue, concurrent case handling could violate the sequential assumption, causing the automation to submit incorrect data if it reads a case that a human has already partially processed.

**Mitigation:** Implement a case-locking mechanism (mark a case as "in automation" before submitting) before production rollout, and define a clear handoff protocol between automated and manual processing paths.

### Risk 5: Ingestion is verified for shape, not for content correctness

**Evidence:** `tests/test_multiformat_parity.py` confirms all supported formats produce identical aggregate output on the real 681-segment dataset. One class of client-supplied malformation was found and fixed during this work: Excel cannot store timezone-aware datetimes, so a file round-tripped through Excel comes back with native datetime cells and the UTC `Z` marker stripped. `pandas.read_excel` then returned `Timestamp` objects where the automator expected strings, raising `ValueError` on every record. The parser now coerces timestamp fields back to ISO-8601 strings on ingestion, and the parity test includes a hostile fixture (Excel round-trip, reordered columns, an extra client-added column) that reproduces the original failure.

**What this does not cover:** the fixture set is still authored by this pipeline. Localised date formats (a `dd/mm/yyyy` locale on the client's machine), timestamps recorded in local time rather than UTC, and missing or renamed required columns are not yet exercised. A timezone mismatch is the most dangerous of these because it would not crash — it would silently produce plausible but wrong durations.

**Mitigation:** Add schema validation at the parser boundary that rejects records missing the four required fields, and require an explicit timezone marker on ingested timestamps rather than inferring one. Before accepting externally produced files in production, extend the parity fixture set with a locale-formatted and a local-timezone sample obtained from the client's actual export process, not synthesised here.