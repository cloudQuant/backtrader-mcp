# Retention and cleanup

Every stored object class has a retention path:

```bash
backtrader-mcp clean --kind jobs --before 2026-01-01       # terminal jobs + dirs
backtrader-mcp clean --kind cas --before 2026-01-01        # unreferenced CAS objects
backtrader-mcp clean --kind drafts --before 2026-01-01     # unreferenced drafts
backtrader-mcp clean --kind approvals --before 2026-01-01  # used/expired approvals
backtrader-mcp clean --kind nonces --before 2026-01-01     # consumed token nonces
backtrader-mcp clean --kind audit --before 2026-01-01      # audit history
backtrader-mcp clean --kind idempotency --before 2026-01-01
```

- `jobs` deletes only terminal jobs finished before the date (rows and
  directories) and validates the timestamp strictly.
- `cas` scans every dataset manifest for referenced objects first — a
  referenced object is never deleted; only hash-named files older than the
  cutoff are removed.
- `drafts` keeps any draft referenced by a run plan or job.
- All cleanups write an audit record and checkpoint the WAL afterwards.
- `--before` accepts `YYYY-MM-DD` or a full ISO timestamp.

The `doctor` command reports a read-only jobs section (state counts, oldest
active job, WAL size) when the state database exists; it never creates the
state root.
