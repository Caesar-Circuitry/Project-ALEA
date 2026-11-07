# alea.game

BIOBUZZ field geometry, hive geometry, game rules and robot constants. The only place game numbers live; every other module imports them from here. Units go in names (`dist_in`, `speed_in_s`).

- `biobuzz.py`: field, hive, hive-frame and StarterBot launcher constants, each with a `# source:` comment naming the `alea/sim/shotsim.py` line it copies. `shotsim.py` stays the authoritative frozen copy and does not import this module. `tests/test_game_constants.py` checks equality with the snapshot and with shotsim.

**Roadmap phase:** 1
