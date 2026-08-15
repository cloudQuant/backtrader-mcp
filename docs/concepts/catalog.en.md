# Strategy catalog

## Snapshot

`get_catalog_snapshot` returns the slim header by default (counts, hashes,
provenance, `extensions.entry_count`) without the 1,155-record entry list —
about 340 bytes instead of ~315 KB. Set `include_entries=true` to page with
`limit` (1-100) and `offset`; pagination reports
`total`/`has_more`/`truncated`. Every packaged record has
`source_available=false`: search and provenance are available, but the
original source bytes were not shipped.

## Search

`search_strategy_catalog` matches text tokens and archetype filters with
deterministic ranking, `total`/`has_more`/`offset` metadata, and actionable
empty-result suggestions. Unknown archetypes enumerate the valid values.

## Source-attached refresh

`refresh_strategy_catalog` scans a registered target root (AST-only, at most
5,000 files) or rebuilds the dual functional/package corpus. Scans hash and
parse only — corpus files are never imported or executed. The refresh uses an
(mtime,size) fingerprint cache (unchanged files are not re-hashed), writes
entries in single transactions, and drops stale entries for deleted sources.

## Templates

`list_strategy_templates` (tool and resource) returns all fourteen
archetype/profile combinations; `inspect_strategy` reads bundled or
source-attached metadata without importing it and reports staleness
diagnostics when source bytes changed since the refresh.
