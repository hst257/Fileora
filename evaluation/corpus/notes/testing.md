# Software testing and cache invalidation

Unit tests check individual behaviors while integration tests verify component interaction. Deterministic fixtures make failures reproducible. A regression test prevents a previously fixed bug from returning. Content hashes invalidate cached processing when source bytes change. Idempotent indexing can repeat a job without creating duplicate evidence. Crash recovery rebuilds derived indexes from authoritative database records. Filesystem watchers can miss events, so periodic reconciliation scans verify the catalog.
