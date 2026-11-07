# tests/hifi_traces/record

Recorder for the dsim hive traces in `tests/hifi_traces/`. `record_hive.mjs` imports dsim's real
`src/games/biobuzz/hive.ts` (and its `config.ts`) at the pinned commit and writes the JSON
fixtures. dsim is untrusted third-party code: run it only in the `alea-dev` container, copy this
script out of the repo into `/tmp/dsim-rec/`, never run it from inside the dsim checkout. See
`../README.md` for the exact commands.

**Roadmap phase:** 1b (hifi port, traces).
