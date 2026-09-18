"""
Event-driven trigger for the Step 3 automation prototype.

Watches a drop directory using OS kernel filesystem events (inotify on
Linux, ReadDirectoryChangesW on Windows, FSEvents on macOS) and runs the
5132_pi automator against any supported file placed there.

This form was chosen over a REST endpoint or a polling scheduler because
it needs no open ports, no firewall rules and no server process -- see
reports/final_report.md Section 2 for the full rationale and the
alternatives that were rejected.

Run from the repository root:
    python src/automation/file_watcher.py [watch_dir]
"""
import sys
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# Allow execution both as a script and as a module, regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from file_parser import parse_incoming_file, SUPPORTED_SUFFIXES  # noqa: E402
from pi_5132_automator import HR5132PIAutomator  # noqa: E402

DEFAULT_WATCH_DIR = "./incoming_data"
# Excel is supported by the parser but intentionally not auto-triggered:
# .xlsx duration handling is not yet load-tested (WORKLOG.md Day 6).
WATCHED_SUFFIXES = SUPPORTED_SUFFIXES - {".xls"}


class UniversalPayrollHandler(FileSystemEventHandler):
    """Dispatches newly created files to the 5132_pi automator."""

    def __init__(self):
        self.automator = HR5132PIAutomator()

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if file_path.suffix.lower() not in WATCHED_SUFFIXES:
            return

        # A failure here must not kill the observer thread; a long-running
        # watcher has to survive one bad file drop.
        try:
            print(f"\n[AUTO-TRIGGER] Detected {file_path.suffix} file: {file_path.name}")

            records = parse_incoming_file(str(file_path))
            print(f"[AUTO-TRIGGER] Extracted {len(records)} raw records.")
            if not records:
                print("[AUTO-TRIGGER] Nothing to process.")
                return

            summary = self.automator.batch_process_records(records)
            print(
                f"[AUTO-TRIGGER] Done. "
                f"Matched {summary.get('total_records_processed', 0)} 5132_pi segments | "
                f"Real human time: "
                f"{summary.get('total_active_minutes_actual_human_time', 0)} min | "
                f"Projected saved (raw click only): "
                f"{summary.get('projected_minutes_saved_vs_raw_click', 0)} min"
            )
        except Exception as exc:  # deliberately broad: keep the watcher alive
            print(f"[AUTO-TRIGGER] FAILED on {file_path.name}: "
                  f"{type(exc).__name__}: {exc}")


def main():
    watch_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_WATCH_DIR
    Path(watch_dir).mkdir(parents=True, exist_ok=True)

    observer = Observer()
    observer.schedule(UniversalPayrollHandler(), path=watch_dir, recursive=False)
    observer.start()

    print(f"--> Multi-format file watcher active. Drop files into '{watch_dir}/'. "
          f"Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n--> Stopping watcher.")
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
