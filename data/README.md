# data/

Not committed to git (see .gitignore) — datasets are large and provided
separately. Expected local layout:

```
data/
  dataset_a/
    ses_.../
      chunk_.../
        events.jsonl
        manifest.json
        screenshots/
      gt.jsonl
      gt_manifest.json
  dataset_b/
    ses_.../
      chunk_.../
        events.jsonl
        manifest.json
        screenshots/
```

Place the provided `dataset_a/` and `dataset_b/` folders directly under
this directory.
