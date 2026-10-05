# http-cache-replay dev tools (never upload these)

- `generate.py` writes the request log to `tasks/http-cache-replay/environment/data/` and the
  identical verifier copy in `tests/data/`, and writes `tests/case_tags.json` (rule tags per
  request, used by the grouped tests). Seed 9111, deterministic. `--seed N --out DIR` writes an
  alternate log for cross-checking only.
- `calibrate.py` (run from repo root, needs writable `/app`):
  - engine (verifier) vs solve (oracle) on the shipped log and, with `--seeds N`, on N other logs;
  - oracle passes, empty output fails;
  - each common RFC 9111 shortcut (browser-cache semantics, Authorization handling, s-maxage
    ignored, heuristic on any status, Expires vs max-age precedence, Expires on the cache clock,
    Age shortcuts, `>=` freshness, invalidation on any/no status, no-cache as no-store, invalid
    Expires as unstorable, 304 not refreshing) fails at least one test.

Last run: 0 mismatches over 200 extra seeds (36,400 rows); all 17 shortcuts fail.
