import time
from pathlib import Path
from file_parser import parse_incoming_file
from pi_5132_automator import HR5132PIAutomator
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

WATCH_DIR = "./incoming_data"
SUPPORTED_EXTENSIONS = {".jsonl", ".json", ".csv", ".tsv", ".xlsx"}

class UniversalPayrollHandler(FileSystemEventHandler):
    def __init__(self):
        self.automator = HR5132PIAutomator()

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            print(f"\n[AUTO-TRIGGER] Detected {file_path.suffix} file: {file_path.name}")
            
            # Step 1: Normalize file into standard list of dicts
            records = parse_incoming_file(str(file_path))
            print(f"[AUTO-TRIGGER] Extracted {len(records)} raw records.")
            
            # Step 2: Pass records directly to automator
            # (Executes in-memory without write latency)
            summary = self.automator.batch_process_records(records)
            print(f"[AUTO-TRIGGER] Done! Real human time processed: "
      f"    {summary.get('total_active_minutes_actual_human_time', 0)} min | "
      f"    Projected saved (vs. raw click): "
      f"    {summary.get('projected_minutes_saved_vs_raw_click', 0)} min.")
if __name__ == "__main__":
    Path(WATCH_DIR).mkdir(exist_ok=True)
    event_handler = UniversalPayrollHandler()
    observer = Observer()
    observer.schedule(event_handler, path=WATCH_DIR, recursive=False)
    observer.start()

    print(f"--> Multi-Format File Watcher Active! Drop files into '{WATCH_DIR}/'...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()