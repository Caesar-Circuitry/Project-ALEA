# conf/study

Study definitions for `alea.sim.run_study`.

- `brev72.yaml`: the 72-condition robustness study (aim, flywheel speed, robot motion, ball size, bounce x 1,000,000 shots). Top-level keys `shots`, `batch`, `seed`, `out` and a `conditions` grid; command-line flags override them. For `fidelity: hifi`, `out: results/study` is redirected to `results/study-hifi` (a line is printed); use `--out` to choose another directory.
- `hifi_example.yaml`: `fidelity: hifi` example. The four values in its `hifi:` block are open placeholders for a smoke run, not decisions.

**Roadmap phase:** 1
