// Records dsim hive traces. Usage (inside the alea-dev container, cwd /tmp/dsim-rec):
//   ./node_modules/.bin/tsx record_hive.mjs <dsim-src-dir> <out-dir>
// Every number in the output comes from running dsim's own hive.ts / config.ts. The only things
// defined here are INPUTS (grids, scenarios), the kindOf callbacks and the RNGs the caller owns.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const SRC = resolve(process.argv[2] ?? '/tmp/dsim-src');
const OUT = resolve(process.argv[3] ?? '.');
mkdirSync(OUT, { recursive: true });
const imp = (rel) => import(pathToFileURL(join(SRC, 'src', rel)).href);
const H = await imp('games/biobuzz/hive.ts');
const C = await imp('games/biobuzz/config.ts');

// pinned commit: read from the checkout's metadata files (no VCS program is run)
function commit() {
  const gd = join(SRC, '.git');
  const head = readFileSync(join(gd, 'HEAD'), 'utf8').trim();
  if (!head.startsWith('ref:')) return head;
  const ref = head.slice(5).trim();
  const p = join(gd, ref);
  if (existsSync(p)) return readFileSync(p, 'utf8').trim();
  for (const l of readFileSync(join(gd, 'packed-refs'), 'utf8').split('\n'))
    if (l.endsWith(' ' + ref)) return l.split(' ')[0];
  throw new Error('cannot resolve commit');
}
const DSIM_COMMIT = commit();
const GEN = 'tests/hifi_traces/record/record_hive.mjs';
const CMD = 'cd /tmp/dsim-rec && ./node_modules/.bin/tsx record_hive.mjs /tmp/dsim-src <out-dir>   (run through `just dev`)';

// ---- compact, stable serializer: objects pretty to depth 1, row arrays one row per line ----
function ser(v, depth = 0) {
  const pad = '  '.repeat(depth + 1);
  const end = '  '.repeat(depth);
  if (Array.isArray(v)) {
    if (v.every((e) => e === null || typeof e !== 'object')) return JSON.stringify(v);
    return '[\n' + v.map((e) => pad + JSON.stringify(e)).join(',\n') + '\n' + end + ']';
  }
  if (v && typeof v === 'object') {
    if (depth >= 2) return JSON.stringify(v);
    return '{\n' + Object.keys(v).map((k) => `${pad}${JSON.stringify(k)}: ${ser(v[k], depth + 1)}`).join(',\n') + '\n' + end + '}';
  }
  if (v === undefined || (typeof v === "number" && !Number.isFinite(v))) throw new Error("bad value in fixture");
  return JSON.stringify(v);
}
function emit(file, scenario, inputs, outputs) {
  const doc = { dsim_commit: DSIM_COMMIT, source_file: 'src/games/biobuzz/hive.ts', scenario, generator: { script: GEN, command: CMD }, inputs, ...outputs };
  const text = ser(doc) + '\n';
  writeFileSync(join(OUT, file), text);
  console.log(file, text.length, 'bytes');
}
const clean = (h) => JSON.parse(JSON.stringify(h)); // drops undefined (e.g. absent swingRate)
const ALL = ['red', 'blue'];
const SIDES = ['north', 'south'];
const mkHive = (up, over = {}) => ({ up, contents: [], tips: 0, tipping: 0, released: false, ...over });
// hive states that differ in what hiveTakingSide sees
const PHASES = [
  ['settled', { tipping: 0, released: false }],
  ['swing_before_release', { tipping: 3, released: false }],
  ['swing_after_release', { tipping: 1.5, released: true, swingRate: 1 }],
];
const kindOfFrom = (kinds) => (id) => kinds[id];
const zMid = (C.BB_HIVE_OPEN_Z[0] + C.BB_HIVE_OPEN_Z[1]) / 2;

// ================= 1. capture.json =================
{
  const W = C.BB_CELL_OPEN.w, D = C.BB_CELL_OPEN.d;
  const xs = [-W / 2 - 1e-3, -W / 2, -W / 2 + 1e-3, 0, W / 2 - 1e-3, W / 2, W / 2 + 1e-3];
  const ys = [-D / 2 - 1e-3, -D / 2, 0, D / 2, D / 2 + 1e-3];
  const M = H.BB_HIVE_ACCEPT_MARGIN;
  const zs = [C.BB_HIVE_OPEN_Z[0] - 1e-3, C.BB_HIVE_OPEN_Z[0], zMid, C.BB_HIVE_OPEN_Z[1], C.BB_HIVE_OPEN_Z[1] + M - 1e-3, C.BB_HIVE_OPEN_Z[1] + M, C.BB_HIVE_OPEN_Z[1] + M + 1e-3];
  // [vx, vy sign relative to inbound for ref cell (1 inbound, -1 outbound, 0), vz]
  const vels = [[0, 1, -10], [0, -1, -10], [0, 1, 10], [0, 1, 0], [0, 0, -10], [3, 1, -0.001]];
  const margins = [null, 0, 5];
  const rows = [];
  const geom = [];
  for (const alliance of ALL) {
    geom.push({ alliance, pivot: H.hivePivot(alliance), cell: { north: H.hiveCellPos(alliance, 'north'), south: H.hiveCellPos(alliance, 'south') } });
    for (const up of SIDES) for (const [ph, over] of PHASES) {
      const hive = clean(mkHive(up, over));
      for (const ref of SIDES) {
        const c = H.hiveCellPos(alliance, ref);
        const inbound = H.hiveApproachSign(ref);
        const add = (dx, dy, z, v, m) => {
          const pos = { x: c.x + dx, y: c.y + dy };
          const vel = { x: v[0], y: v[1] * inbound, z: v[2] };
          const r = m === null ? H.hiveAccepts(hive, alliance, pos, z, vel) : H.hiveAccepts(hive, alliance, pos, z, vel, m);
          rows.push({ alliance, up, phase: ph, ref, pos, z, vel, margin: m, accepts: r });
        };
        for (const x of xs) for (const y of ys) add(x, y, zMid, [0, 1, -10], null);
        if (ref === up) for (const m of margins) for (const z of zs) for (const v of vels) add(0, 0, z, v, m);
      }
    }
  }
  emit('capture.json', 'Capture of single launches into the up CELL: accept footprint, opening heights, margin, descent and inbound tests, per alliance, up side and swing phase. ref = the CELL whose centre the position offset is relative to (inbound = toward the pivot for that cell).', {
    margin_default_in: H.BB_HIVE_ACCEPT_MARGIN, cell_open_in: C.BB_CELL_OPEN, open_z_in: C.BB_HIVE_OPEN_Z,
    note: 'each row: hive state is {up, tipping, released[, swingRate]} from phases[phase] (contents empty, tips 0); margin null = dsim default argument; vel.y already signed',
    phases: Object.fromEntries(PHASES),
  }, { geometry: geom, accepts: rows });
}

// ================= 2. load.json =================
{
  const mixes = [
    { name: 'pollen_only', kinds: ['pollen', 'pollen', 'pollen'] },
    { name: 'red_nectar', kinds: ['red', 'red'] },
    { name: 'blue_nectar', kinds: ['blue', 'blue'] },
    { name: 'mixed', kinds: ['pollen', 'red', 'pollen', 'blue', 'pollen', 'red'] },
  ];
  const loads = mixes.map((m) => ({ ...m, ids: m.kinds.map((_, i) => i * 3 + 1), load: H.hiveLoad(m.kinds.map((_, i) => i * 3 + 1), (id) => m.kinds[(id - 1) / 3]) }));
  const grid = [];
  for (let n = 0; n <= 9; n++) for (let p = 0; p <= 14; p++) {
    const load = { pollen: p, nectar: n };
    grid.push({ pollen: p, nectar: n, will_tip: H.hiveWillTip(load), surplus: H.hiveSurplus(load), swing_rate: H.hiveSwingRate(load) });
  }
  const viaContents = [];
  for (const [p, n] of [[8, 0], [7, 0], [7, 1], [6, 2], [5, 2], [3, 3], [2, 3], [1, 4], [0, 4], [0, 5], [0, 6], [4, 3]])
    for (const colour of ALL) {
      const kinds = [...Array(p).fill('pollen'), ...Array(n).fill(colour)];
      for (const ks of [kinds, [...kinds].reverse()]) {
        const load = H.hiveLoad(ks.map((_, i) => i), kindOfFrom(ks));
        viaContents.push({ kinds: ks, load, will_tip: H.hiveWillTip(load), surplus: H.hiveSurplus(load), swing_rate: H.hiveSwingRate(load) });
      }
    }
  emit('load.json', 'Loadable threshold: hiveLoad counts pollen vs everything else (red or blue nectar); hiveWillTip/hiveSurplus/hiveSwingRate over the (pollen, nectar) grid incl. beyond the end of the tip table.', {
    kindOf: 'ids are indices into the kinds list (hiveLoad_cases: id = 3*index+1); kind is pollen | red | blue; any non-pollen kind counts as nectar',
    pollen_range: [0, 14], nectar_range: [0, 9],
  }, { hiveLoad_cases: loads, via_contents: viaContents, grid });
}

// ================= 3. sides.json =================
{
  const rows = [];
  for (const alliance of ALL) for (const up of SIDES) for (const [ph, over] of PHASES) {
    const hive = clean(mkHive(up, over));
    const taking = H.hiveTakingSide(hive);
    rows.push({ alliance, phase: ph, hive, taking_side: taking, approach_sign_up: H.hiveApproachSign(up), approach_sign_taking: H.hiveApproachSign(taking), taking_cell_pos: H.hiveCellPos(alliance, taking), other_side_of_up: H.otherSide(up) });
  }
  emit('sides.json', 'Both CELL sides and both alliances: otherSide, pivot, approach sign and taking side/cell for settled, pre-release and post-release states.', {
    sides: SIDES, alliances: ALL,
  }, { otherSide: Object.fromEntries(SIDES.map((s) => [s, H.otherSide(s)])), pivot: Object.fromEntries(ALL.map((a) => [a, H.hivePivot(a)])), approach_sign: Object.fromEntries(SIDES.map((s) => [s, H.hiveApproachSign(s)])), rows });
}

// ================= 4. timer traces =================
// A launch offered at a step is added to the tray only if hiveAccepts (dsim) says yes for an
// inbound, descending shot at the centre of the taking cell; the add rule itself is the recorder's.
function runScenario(sc, fn) {
  const kinds = [...sc.kinds];
  const kindOf = (id) => kinds[id];
  let hive = clean(mkHive(sc.up, { contents: kinds.map((_, i) => i) }));
  const steps = [];
  const launches = [];
  let tippedAt = null;
  for (let i = 0; i < sc.max_steps; i++) {
    for (const L of sc.launches ?? []) if (Math.round(L.t_s / sc.dt) === i) {
      const side = H.hiveTakingSide(hive);
      const c = H.hiveCellPos('red', side);
      const ok = H.hiveAccepts(hive, 'red', c, zMid, { x: 0, y: H.hiveApproachSign(side), z: -10 });
      launches.push({ step: i, kind: L.kind, taking_side: side, accepted: ok });
      if (ok) { kinds.push(L.kind); hive = { ...hive, contents: [...hive.contents, kinds.length - 1] }; }
    }
    const timerPrev = hive;
    const r = fn === 'timer' ? H.hiveTimerStep(hive, sc.dt, kindOf) : H.hiveStep(hive, sc.dt, kindOf);
    hive = r.hive;
    if (fn === 'timer') { // hiveTimerStep carries contents through untouched; verify, then omit to keep files small
      if (r.hive.contents !== undefined && JSON.stringify(r.hive.contents) !== JSON.stringify(timerPrev.contents) && !r.tipped) throw new Error('contents changed');
      if (r.tipped && JSON.stringify(r.hive.contents) !== JSON.stringify(timerPrev.contents)) throw new Error('contents changed at tip');
    }
    steps.push(fn === 'timer' ? { i, hive: (({ contents, ...h }) => clean(h))(r.hive), tipped: r.tipped, releasing: r.releasing } : { i, hive: clean(r.hive), tipped: r.tipped, spilled: r.spilled });
    if (r.tipped && tippedAt === null) tippedAt = i;
    if (tippedAt !== null && i - tippedAt >= (sc.after ?? 2)) break;
  }
  const not_reached = (sc.launches ?? []).filter((L) => Math.round(L.t_s / sc.dt) >= steps.length);
  return { launches, steps, not_reached };
}
const P = (n) => Array(n).fill('pollen');
const N = (n, c = 'red') => Array(n).fill(c);
function scenarios(dt, group) {
  return [
    { name: 'at_threshold_8p_north', up: 'north', kinds: P(8) },
    { name: 'at_threshold_8p_south', up: 'south', kinds: P(8) },
    { name: 'nectar_only_5n_blue', up: 'north', kinds: N(5, 'blue') },
    { name: 'mixed_3p_3n', up: 'south', kinds: [...P(3), ...N(3)] },
    { name: 'surplus2_10p', up: 'north', kinds: P(10) },
    { name: 'surplus_cap_14p', up: 'north', kinds: P(14) },
    { name: 'below_threshold_7p', up: 'north', kinds: P(7), max_steps: 60, after: 0 },
    { name: 'fire_into_swinging_tray', up: 'north', kinds: P(8), launches: [{ t_s: 1 / 60, kind: 'pollen' }, { t_s: 0.5, kind: 'red' }, { t_s: 1, kind: 'pollen' }, { t_s: 1.5, kind: 'pollen' }, { t_s: 1.75, kind: 'blue' }] },
  ].filter((s) => group === undefined || group.includes(s.name)).map((s) => ({ ...s, dt, max_steps: s.max_steps ?? 1200 }));
}
function timerFile(file, scenario, dts, group) {
  const outs = [];
  for (const dt of dts) for (const sc of scenarios(dt, group)) {
    const t = runScenario(sc, 'timer');
    const s = runScenario(sc, 'step');
    outs.push({ name: sc.name, dt_s: dt, up: sc.up, initial_kinds: sc.kinds, launches_offered: sc.launches ?? [], max_steps: sc.max_steps, launches_not_reached_timer: t.not_reached, launches_not_reached_step: s.not_reached, launches_timer: t.launches, launches_step: s.launches, timer_steps: t.steps, step_steps: s.steps });
  }
  emit(file, scenario, {
    consts: { swing_s: H.BB_TIP_SWING_S, release_s: H.BB_TIP_RELEASE_S },
    kindOf: 'kinds list indexed by id; ids 0..n-1 initially, launches get the next id',
    launch_rule: 'recorder: a launch offered at time t_s is applied at step round(t_s/dt) (so launch times scale with dt; launches whose step is past the end of the run are listed in launches_not_reached_*; applied ones, with accepted flags, in launches_timer / launches_step). It is added iff hiveAccepts(hive, red, centre of taking cell, mid opening z, vel = {x:0, y:hiveApproachSign(taking), z:-10}); then that step is run. The add rule always aims at the taking-cell centre, inbound and descending, so these traces never contain a refused launch; refusal is covered only by capture.json. Each scenario is run twice from the same inputs, once with hiveTimerStep and once with hiveStep. A run stops 2 steps after the first tipped=true step (never for below_threshold), or at max_steps.',
    timer_steps_note: 'IMPORTANT: hiveTimerStep never clears contents (the caller does); the recorder keeps the tray full, so after the settle the timer run starts a SECOND swing (tips can reach 2 at dt 3 and 5 while hiveStep rows show tips 1, because hiveStep empties the tray at the release). Compare the two series only up to the first tipped=true. timer_steps rows omit hive.contents (hiveTimerStep returns it untouched; the recorder asserts it); step_steps rows carry it',
    scenarios_in_file: outs.map((o) => o.name),
    initial_hive: 'contents = ids of initial_kinds, tips 0, tipping 0, released false, no swingRate key',
    key_note: 'a hive with no swingRate key means undefined (key omitted)',
  }, { runs: outs });
}
const A = ['at_threshold_8p_north', 'at_threshold_8p_south', 'nectar_only_5n_blue', 'mixed_3p_3n'];
const B = ['surplus2_10p', 'surplus_cap_14p', 'below_threshold_7p', 'fire_into_swinging_tray'];
timerFile('timer_dt60_threshold.json', 'Release and spill timing at dt = 1/60 s, loads exactly at threshold (pollen, nectar-only, mixed; both sides): swing start, release at BB_TIP_RELEASE_S, settle, per-step state; hiveTimerStep (releasing) and hiveStep (spilled).', [1 / 60], A);
timerFile('timer_dt60_surplus.json', 'Release and spill timing at dt = 1/60 s: surplus loads (faster swing, rate cap), an idle below-threshold tray, and elements fired into a swinging tray.', [1 / 60], B);
timerFile('timer_coarse.json', 'Release and spill timing at coarser dt (0.25, 1, 3, 5 s): includes dt longer than half a swing (fallback spill at settle) and longer than a whole swing.', [0.25, 1, 3, 5]);

// ================= 5. spill.json =================
function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const SPILL_SEED = 20261107;
const CYCLE = [0.0, 0.25, 0.5, 0.75, 0.999, 0.1, 0.9, 0.333333333333, 0.6180339887498949];
{
  const SEED = SPILL_SEED;
  const cases = [];
  for (const alliance of ALL) for (const [label, hive] of [
    ['mid_swing_up_north', mkHive('north', { tipping: 2, released: true })],
    ['mid_swing_up_south', mkHive('south', { tipping: 2, released: false })],
    ['settled_up_north', mkHive('north')],
    ['settled_up_south', mkHive('south')],
  ]) for (const count of [0, 1, 3, 8, 14]) for (const rngKind of ['mulberry32', 'cycle']) {
    let draws = 0;
    const base = rngKind === 'mulberry32' ? mulberry32(SEED) : (() => { let k = 0; return () => CYCLE[k++ % CYCLE.length]; })();
    const rng = () => { draws++; return base(); };
    const poses = H.spillPoses(clean(hive), alliance, count, rng);
    cases.push({ alliance, label, hive: clean(hive), count, rng: rngKind, draws, poses });
  }
  emit('spill.json', 'spillPoses with caller-owned deterministic RNGs: outboard cell, positions, speeds, fan and kick, both alliances and sides, mid-swing and settled. Six draws per pose, in order (x, y, speed, fan angle, kick direction, kick magnitude).', {
    rng: {
      mulberry32: { seed: SEED, source: 'function mulberry32(seed){let a=seed>>>0;return()=>{a=(a+0x6d2b79f5)>>>0;let t=a;t=Math.imul(t^(t>>>15),t|1);t^=t+Math.imul(t^(t>>>7),t|61);return((t^(t>>>14))>>>0)/4294967296;};}', note: 'fresh generator per case, seeded with seed; 32-bit unsigned arithmetic, Math.imul = low 32 bits of the product' },
      cycle: { values: CYCLE, note: 'returns values[k % len] for draw k = 0,1,2,...; fresh per case' },
    },
    draws_per_pose: 6,
  }, { cases });
}

// ================= 8. trig.json =================
{
  const M = await imp('math.ts');
  const D = Math.PI / 180;
  const sample = (a) => ({ a, sin: M.dsin(a), cos: M.dcos(a) });
  const degs = [];
  for (let d = 0; d <= 360; d++) degs.push({ deg: d, ...sample(d * D) });
  const neg = [];
  for (let d = -360; d < 0; d += 15) neg.push({ deg: d, ...sample(d * D) });
  // the angles spillPoses feeds dsin/dcos: fan a = (u*2-1)*FAN*PI/180 and kick ka = u*2*PI, for the draws
  // of the spill.json mulberry32 stream (6 draws per pose, 14 poses), plus the fan extremes
  const rng = mulberry32(SPILL_SEED);
  const used = [];
  for (let i = 0; i < 14; i++) {
    const d = [rng(), rng(), rng(), rng(), rng(), rng()];
    const a = (d[3] * 2 - 1) * H.BB_SPILL_FAN * (Math.PI / 180);
    const ka = d[4] * 2 * Math.PI;
    used.push({ pose: i, fan: sample(a), kick: sample(ka) });
  }
  const ext = [-1, 0, 1].map((u) => sample(u * H.BB_SPILL_FAN * (Math.PI / 180)));
  emit('trig.json', "dsim's deterministic dsin/dcos (src/math.ts, polynomial, not Math.sin/cos; ~1e-11 error) sampled for the Python port: whole degrees 0..360, -360..-15 step 15, the fan/kick angles spillPoses uses for the spill.json mulberry32 stream, and the fan extremes.", {
    functions: 'dsin(a), dcos(a) with a in RADIANS; sample angle a = deg * (Math.PI / 180) computed in JS',
    spill_seed: SPILL_SEED,
  }, { degrees_0_360: degs, degrees_neg: neg, spill_stream_angles: used, fan_extremes: ext });
}

// ================= 6. constants.json =================
{
  const cfg = {};
  for (const k of Object.keys(C).sort()) if (/^(BB3?_HIVE_|BB_TIP_|BB_SPILL_|BB_CELL_OPEN|BB_POLLEN_R$|BB_NECTAR_R$)/.test(k) && typeof C[k] !== 'function') cfg[k] = C[k];
  const hiveTs = {};
  for (const k of Object.keys(H).sort()) if (typeof H[k] !== 'function') hiveTs[k] = H[k];
  const table = [];
  for (let n = 0; n <= 12; n++) {
    let thr = null;
    for (let p = 0; p <= 40; p++) if (H.hiveWillTip({ pollen: p, nectar: n })) { thr = p; break; }
    const row = Math.min(n, C.BB_TIP_POLLEN.length - 1);
    table.push({ nectar: n, row, table_pollen: C.BB_TIP_POLLEN[row], min_pollen_that_tips: thr });
  }
  let fd = null;
  try { const G = await imp('games/biobuzz/fieldDims.gen.ts'); if (G.HIVE) fd = G.HIVE; } catch (e) { fd = { error: String(e) }; }
  emit('constants.json', 'Hive constants as dsim exports them (config.ts hive/tip/spill block and hive.ts own exports), and the tip-table lookup for nectar 0..12.', {
    config_filter_note: 'BB_SPILL_* is not defined in config.ts: those constants live in hive.ts and are in hive_ts (the pattern is kept so a future config.ts addition shows up). ', config_filter: '/^(BB3?_HIVE_|BB_TIP_|BB_SPILL_|BB_CELL_OPEN|BB_POLLEN_R$|BB_NECTAR_R$)/ over the exports of config.ts, non-functions',
    hive_ts_reads: ['BB_CELL_OPEN', 'BB_HIVE_BOTTOM_Z', 'BB_HIVE_CELL_DY', 'BB_HIVE_LEN', 'BB_HIVE_OPEN_Z', 'BB_HIVE_W', 'BB_HIVE_X', 'BB_TIP_POLLEN'],
  }, { config_ts: cfg, hive_ts: hiveTs, fieldDims_gen_HIVE: fd, tip_table_lookup: table });
}

// ================= 7. deflect.json =================
{
  const rows = [];
  for (const alliance of ALL) for (const up of SIDES) for (const [ph, over] of PHASES.slice(0, 2)) {
    const hive = clean(mkHive(up, over));
    const p = H.hivePivot(alliance);
    const hw = C.BB_HIVE_W / 2, hl = C.BB_HIVE_LEN / 2, zb = C.BB_HIVE_BOTTOM_Z, zt = C.BB_HIVE_OPEN_Z[1];
    const zm = (zb + zt) / 2;
    const V = (x, y, z) => ({ x: p.x + x, y: p.y + y, z });
    const mv = (name, prev, pos, vel) => rows.push({ name, alliance, phase: ph, hive, prev, pos, vel, result: H.hiveDeflect(hive, alliance, prev, pos, vel) });
    mv('side_east', V(hw + 3, 10, zm), V(hw - 1, 10, zm), { x: -20, y: 2, z: 5 });
    mv('side_west', V(-hw - 3, -10, zm), V(-hw + 1, -10, zm), { x: 20, y: -2, z: -5 });
    mv('end_north', V(2, hl + 3, zm), V(2, hl - 1, zm), { x: 1, y: -30, z: 0 });
    mv('end_south', V(2, -hl - 3, zm), V(2, -hl + 1, zm), { x: 1, y: 30, z: 0 });
    mv('underside', V(2, 15, zb - 3), V(2, 15, zb + 1), { x: 4, y: 6, z: 12 });
    mv('top_open', V(2, 15, zt + 3), V(2, 15, zt - 1), { x: 4, y: 6, z: -12 });
    mv('pivot_plane_from_north', V(0, 4, zm), V(0, -4, zm), { x: 5, y: -30, z: 0 });
    mv('pivot_plane_from_south', V(-3, -4, zm), V(-3, 4, zm), { x: 5, y: 30, z: 0 });
    mv('pivot_plane_fast_through_face', V(1, hl + 5, zm), V(1, -hl + 20, zm), { x: 0, y: -80, z: 0 });
    mv('inside_to_inside', V(0, 10, zm), V(0, 12, zm), { x: 0, y: 5, z: 0 });
    mv('outside_to_outside', V(100, 100, 10), V(99, 100, 10), { x: -5, y: 0, z: 0 });
    mv('corner_x_last', V(hw + 1, hl + 3, zm), V(hw - 1, hl - 1, zm), { x: -10, y: -10, z: 0 });
    mv('low_pivot_under_lip', V(0, 4, zb - 5), V(0, -4, zb - 5), { x: 0, y: -30, z: 0 });
  }
  emit('deflect.json', 'hiveDeflect (a missed shot bouncing off the hive body box): each face, the open top and mouth, the pivot plane, inside and outside cases, per alliance and up side.', {
    box: 'W = BB_HIVE_W, LEN = BB_HIVE_LEN centred on the pivot, z from BB_HIVE_BOTTOM_Z to BB_HIVE_OPEN_Z[1]; prev/pos/vel are absolute (pivot + recorder offsets)',
  }, { rows });
}
