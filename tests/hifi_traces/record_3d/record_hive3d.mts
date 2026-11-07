// Ported from dsim by genius0412, commit 62d2446e2ebdf416548fa1641847289bf47cdf36 (staging rule copied from
// scripts/smoke-biobuzz/hive3d.ts). License: PolyForm Noncommercial 1.0.0 (see alea/hifi/LICENSE-dsim).
// Records dsim 3D hive traces by running dsim's REAL sim3d code (hive3d.ts, contacts3d.ts, and the
// Rapier3d engine layer under them) through the real step3d pipeline. Usage, inside the alea-dev
// container, with cwd NOT the dsim clone (see ../README.md for the exact commands):
//   tsx record_hive3d.mts <dsim-src-dir> <out-dir>
// Every number in the output comes from running dsim. The only things defined here are INPUTS
// (staging rules, scenario lists) and the serializer. Nothing is typed in or reconstructed.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const SRC = resolve(process.argv[2] ?? '/tmp/dsim-src');
const OUT = resolve(process.argv[3] ?? '.');
mkdirSync(OUT, { recursive: true });
const imp = (rel: string): Promise<any> => import(pathToFileURL(join(SRC, 'src', rel)).href);

const PE = await imp('sim/physicsEngine.ts');
const E3 = await imp('games/biobuzz/sim3d/engine.ts');
await PE.initPhysics();
await E3.initPhysics3d();
const SPAWN = await imp('games/biobuzz/spawn.ts');
const SIMSPAWN = await imp('sim/spawn.ts');
const RC = await imp('games/biobuzz/robotConfig.ts');
const S3 = await imp('games/biobuzz/sim3d/step3d.ts');
const BODIES = await imp('games/biobuzz/sim3d/bodies.ts');
const H3 = await imp('games/biobuzz/sim3d/hive3d.ts');
const EI = await imp('games/biobuzz/sim3d/engineImpl.ts');
const M3 = await imp('games/biobuzz/sim3d/math3.ts');
const TILT = await imp('games/biobuzz/sim3d/tilt.ts');
const CFG = await imp('games/biobuzz/config.ts');
const HIVE2D = await imp('games/biobuzz/hive.ts');
const SCORE = await imp('games/biobuzz/score.ts');
const GCFG = await imp('config.ts');

// pinned commit: read from the checkout's metadata files (no VCS program is run)
function commit(): string {
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
const GEN = 'tests/hifi_traces/record_3d/record_hive3d.mts';
const CMD = 'just dev /tmp/dsim3d-XXXX/node_modules/.bin/tsx /tmp/dsim3d-XXXX/record_hive3d.mts /tmp/dsim3d-XXXX/src <wt>/tests/hifi_traces/sim3d';

// ---- compact, stable serializer (same style as ../record/record_hive.mjs) ----
function ser(v: any, depth = 0): string {
  const pad = '  '.repeat(depth + 1);
  const end = '  '.repeat(depth);
  if (Array.isArray(v)) {
    if (v.every((e) => e === null || typeof e !== 'object')) return JSON.stringify(v);
    return '[\n' + v.map((e) => pad + JSON.stringify(e)).join(',\n') + '\n' + end + ']';
  }
  if (v && typeof v === 'object') {
    if (depth >= 3) return JSON.stringify(v);
    return '{\n' + Object.keys(v).map((k) => `${pad}${JSON.stringify(k)}: ${ser(v[k], depth + 1)}`).join(',\n') + '\n' + end + '}';
  }
  if (v === undefined || (typeof v === 'number' && !Number.isFinite(v))) throw new Error('bad value in fixture');
  return JSON.stringify(v);
}
function emit(file: string, source_files: string[], scenario: string, inputs: any, outputs: any): void {
  const doc = {
    dsim_commit: DSIM_COMMIT,
    source_file: source_files[0],
    source_files,
    scenario,
    generator: { script: GEN, command: CMD },
    inputs,
    ...outputs,
  };
  const text = ser(doc) + '\n';
  if (text.length > 900_000) throw new Error(file + ' too large: ' + text.length);
  writeFileSync(join(OUT, file), text);
  console.log(file, text.length, 'bytes');
}

const HIVE3D = 'src/games/biobuzz/sim3d/hive3d.ts';
const CONTACTS3D = 'src/games/biobuzz/sim3d/contacts3d.ts';
const DT = 1 / 60;
const A = 'blue';
const REST_RAD = (CFG.BB_HIVE_TILT_DEG * Math.PI) / 180;

// ---- world staging (the INPUT side; mirrors dsim's own scripts/smoke-biobuzz/hive3d.ts) ----
function setup(id: number, alliance: string, startIndex = 0): any {
  return {
    id,
    alliance,
    spec: { ...RC.BB_DEFAULT_SPEC },
    assists: { ...SIMSPAWN.DEFAULT_ASSISTS, fieldCentric: false, aimAssist: false },
    startIndex,
  };
}
function mkWorld(seed: number): any {
  const w = SPAWN.createBiobuzzWorld('free', seed, [setup(0, 'blue', 0)], undefined, '3d');
  w.balls.length = 0;
  return w;
}
type Packing = 'guide' | 'line2';
function fillCell(w: any, alliance: string, pollen: number, nectar: number, packing: Packing = 'guide'): number[] {
  const theta = TILT.hiveTiltAngle(w, alliance);
  const side: 1 | -1 = w.biobuzz.hives[alliance].up === 'north' ? 1 : -1;
  const box = BODIES.hiveCellLocalBox(side, alliance);
  const innerV = side > 0 ? box.vMin : box.vMax;
  const perRow = packing === 'line2' ? 2 : 4;
  const ids: number[] = [];
  let i = 0;
  const put = (isNectar: boolean): void => {
    const r = isNectar ? CFG.BB_NECTAR_R : CFG.BB_POLLEN_R;
    const col = i % perRow;
    const row = Math.floor(i / perRow);
    const x = (col - (perRow - 1) / 2) * 4.6;
    const v = innerV + side * (r + 0.2 + row * 3.4);
    const wLocal = box.wMin + r + 0.2;
    const { a: y, b: z } = M3.rotate2(v, wLocal, theta);
    const id = i + 1;
    ids.push(id);
    w.balls.push({
      id,
      color: isNectar ? alliance : 'yellow',
      state: { kind: 'ground' },
      pos: { x: BODIES.hivePivotX(alliance) + x, y },
      vel: { x: 0, y: 0 },
      z: CFG.BB3_HIVE_PIVOT_Z + z - r,
      vz: 0,
      r,
    });
    i++;
  };
  for (let k = 0; k < nectar; k++) put(true);
  for (let k = 0; k < pollen; k++) put(false);
  return ids;
}
const withTray = <T,>(fn: () => T): T => {
  BODIES.__setHiveDynamicOverrideForTests(true);
  try {
    return fn();
  } finally {
    BODIES.__setHiveDynamicOverrideForTests(null);
  }
};

// ---- scenario: per-tick trace of a staged load through the real step3d ----
function loadTrace(alliance: string, pollen: number, nectar: number, packing: Packing, seed: number, ticks: number): any {
  return withTray(() => {
    const w = mkWorld(seed);
    const ids = fillCell(w, alliance, pollen, nectar, packing);
    const kindOf = SCORE.bbKindIndex(w);
    const col: Record<string, any[]> = {
      tray_theta_rad: [], tray_omega_rad_s: [], hive_angle_rad: [], hive_ang_vel_rad_s: [], tipping_s: [], released: [],
      tips: [], up: [], contents_n: [], spill_n: [], tray_held: [], nectar_due: [],
    };
    const events: [number, string][] = [];
    let first_tipping_tick: number | null = null;
    let first_released_tick: number | null = null;
    let tip_tick: number | null = null;
    for (let t = 0; t < ticks; t++) {
      const nEv = w.events.length;
      S3.step3d(w, DT, new Map());
      const eng = EI.engineFor(w);
      const body = eng.hiveTrays[alliance];
      const h = w.biobuzz.hives[alliance];
      col.tray_theta_rad.push(EI.trayTilt(body));
      col.tray_omega_rad_s.push(body.angvel().x);
      col.hive_angle_rad.push(h.angle);
      col.hive_ang_vel_rad_s.push(h.angVel);
      col.tipping_s.push(h.tipping);
      col.released.push(h.released ? 1 : 0);
      col.tips.push(h.tips);
      col.up.push(h.up);
      col.contents_n.push(h.contents.length);
      col.spill_n.push(Object.values(w.biobuzz.spill ?? {}).filter((x) => x === alliance).length);
      col.tray_held.push(eng.hiveHeld[alliance] ? 1 : 0);
      col.nectar_due.push(w.biobuzz.nectarDue[alliance]);
      for (const e of w.events.slice(nEv)) events.push([t, e]);
      if (first_tipping_tick === null && h.tipping > 0) first_tipping_tick = t;
      if (first_released_tick === null && h.released) first_released_tick = t;
      if (tip_tick === null && h.tips > 0) tip_tick = t;
    }
    const hNow = w.biobuzz.hives[alliance];
    const load = HIVE2D.hiveLoad(hNow.contents, kindOf);
    return {
      pollen,
      nectar,
      alliance,
      packing,
      seed,
      ticks,
      element_ids: ids,
      summary: {
        first_tipping_tick,
        first_released_tick,
        tip_tick,
        final_tips: hNow.tips,
        final_up: hNow.up,
        final_tray_theta_rad: EI.trayTilt(EI.engineFor(w).hiveTrays[alliance]),
        final_contents_n: hNow.contents.length,
        elements_below_z_2in: w.balls.filter((b: any) => b.z < 2).length,
        elements_total: w.balls.length,
        final_load: load,
      },
      events,
      columns: col,
    };
  });
}

// =============================== constants3d.json ===============================
{
  const keys = Object.keys(CFG).filter((k) => /^BB3_HIVE_|^BB3_CELL_SEAT|^BB3_ELEMENT_MASS|^BB3_NECTAR_MASS|^BB3_TRAY_OUTER|^BB3_REST_SPEED|^BB_TIP_POLLEN|^BB_HIVE_TILT_DEG|^BB_POLLEN_R|^BB_NECTAR_R/.test(k));
  const c: any = {};
  for (const k of keys.sort()) c[k] = CFG[k];
  emit('constants3d.json', [HIVE3D, 'src/games/biobuzz/config.ts'], 'config.ts constants the 3D hive reads (BB3_HIVE_*, seat depth, element mass, tilt), plus GRAVITY and SIM_DT', {
    note: 'values read from the loaded modules; BB3_HIVE_DETENT/DAMPING/BALLAST are hive-calibrate outputs',
  }, {
    config: c,
    GRAVITY: GCFG.GRAVITY,
    SIM_DT: GCFG.SIM_DT,
    BB_TIP_SWING_S: HIVE2D.BB_TIP_SWING_S,
    use_hive_dynamic_default: BODIES.useHiveDynamic(),
    mass_props: Object.fromEntries(['red', 'blue'].map((a) => [a, BODIES.hiveTrayMassProps(a)])),
    tray_com_w: Object.fromEntries(['red', 'blue'].map((a) => [a, BODIES.hiveTrayComW(a)])),
    pivot_x_in: Object.fromEntries(['red', 'blue'].map((a) => [a, BODIES.hivePivotX(a)])),
    ref_theta: Object.fromEntries(['red', 'blue'].map((a) => [a, TILT.hiveTrayRefTheta(a)])),
    cell_local_box: Object.fromEntries(['red', 'blue'].map((a) => [a, { north: BODIES.hiveCellLocalBox(1, a), south: BODIES.hiveCellLocalBox(-1, a) }])),
    element_mass: { pollen: BODIES.elementMass(false), nectar: BODIES.elementMass(true) },
  });
}

// =============================== statics3d.json ===============================
{
  const thetas: number[] = [];
  for (let k = -12; k <= 12; k++) thetas.push(k * 0.05);
  thetas.push(REST_RAD, -REST_RAD, 0.5061, -0.5061);
  const loads: [number, number][] = [[0, 0], [3, 0], [8, 0], [3, 3], [0, 5]];
  const torque_rows: any[] = [];
  for (const alliance of ['red', 'blue']) {
    for (const [p, n] of loads) {
      const w = withTray(() => { const x = mkWorld(11); fillCell(x, alliance, p, n); return x; });
      for (const th of thetas) {
        torque_rows.push([alliance, p, n, th, H3.hiveContentsTorque(w, alliance, th)]);
      }
    }
  }
  const restoring_rows: any[] = [];
  for (const alliance of ['red', 'blue']) {
    for (const th of thetas) restoring_rows.push([alliance, th, H3.hiveRestoringTorque(alliance, th), H3.hiveHoldTorque(alliance, th)]);
  }
  const inside_rows: any[] = [];
  for (const alliance of ['red', 'blue']) {
    const px = BODIES.hivePivotX(alliance);
    for (const side of [1, -1]) {
      for (const th of [REST_RAD, 0, -REST_RAD]) {
        for (const md of [0, CFG.BB3_CELL_SEAT_DEPTH]) {
          for (const dx of [-10, 0, 10]) {
            for (let y = -20; y <= 20; y += 5) {
              for (let z = 35; z <= 70; z += 5) {
                inside_rows.push([alliance, side, th, md, px + dx, y, z, H3.insideCell(px + dx, y, z, alliance, side, th, md)]);
              }
            }
          }
        }
      }
    }
  }
  emit('statics3d.json', [HIVE3D], 'pure hive3d functions: hiveContentsTorque (staged guide-packing loads), hiveRestoringTorque, hiveHoldTorque, insideCell', {
    columns: {
      torque_rows: '[alliance, pollen, nectar, theta_rad, hiveContentsTorque(world, alliance, theta)] (world: elements staged by the guide packing, tray at rest, no step)',
      restoring_rows: '[alliance, theta_rad, hiveRestoringTorque, hiveHoldTorque]',
      inside_rows: '[alliance, side_sign (1 north, -1 south), theta_rad, min_depth_in, x_in, y_in, z_in, insideCell(...)] in the field-centred frame',
    },
    staging: 'fillCell in record_hive3d.mts: nectar first, then pollen, 4 per row across x at 4.6 in, rows outward from the inner end of the up cell (same as dsim scripts/smoke-biobuzz/hive3d.ts)',
    loads,
  }, { torque_rows, restoring_rows, inside_rows });
}

// =============================== load traces ===============================
{
  const below = [[0, 0, 240], [7, 0, 480], [2, 3, 480], [0, 4, 480]] as const;
  const rows = below.map(([p, n, t], i) => loadTrace(A, p, n, 'guide', 100 + i, t));
  emit('loads_no_tip_blue.json', [HIVE3D, 'src/games/biobuzz/sim3d/step3d.ts'],
    'step3d trace, blue hive, loads below the tip table (BB_TIP_POLLEN = [8,7,6,3,1,0] by nectar): empty rest, 7P, 2P+3N, 0P+4N; detent hold', {
      dt_s: DT, packing: 'guide', seeds: 'row index + 100', note: 'world.balls cleared then staged; robot 0 (blue) at its anchor; columns are one entry per step3d call',
    }, { rows });
}
{
  const tip = [[8, 0, 'guide'], [3, 3, 'guide'], [1, 4, 'guide'], [0, 5, 'guide'], [8, 0, 'line2']] as const;
  const rows = tip.map(([p, n, pk], i) => loadTrace(A, p, n, pk, 200 + i, 540));
  emit('loads_tip_blue.json', [HIVE3D, 'src/games/biobuzz/sim3d/step3d.ts'],
    'step3d trace, blue hive, loads at or above the tip table: 8P, 3P+3N, 1P+4N, 0P+5N (guide packing) and 8P (line2 packing); breakaway, swing, release, tip', {
      dt_s: DT, seeds: 'row index + 200',
    }, { rows });
}
{
  const rows = [[8, 0], [7, 0]].map(([p, n], i) => loadTrace('red', p, n, 'guide', 300 + i, 540));
  emit('loads_red.json', [HIVE3D, 'src/games/biobuzz/sim3d/step3d.ts'],
    'step3d trace, RED hive (up cell is south, angle sign opposite): 8P tips, 7P holds', { dt_s: DT, seeds: 'row index + 300' }, { rows });
}

// =============================== joint tick ===============================
{
  // direct hive3dJointTick calls on staged hive states: one call each, outputs recorded
  const cases: any[] = [];
  const mk = (alliance: string, p: number, n: number, hive: any, label: string): void => {
    const out = withTray(() => {
      const w = mkWorld(400 + cases.length);
      fillCell(w, alliance, p, n);
      const eng = EI.engineFor(w);
      const before = { ...w.biobuzz.hives[alliance], ...hive };
      w.biobuzz.hives[alliance] = before;
      const ev0 = w.events.length;
      H3.hive3dJointTick(w, eng);
      const h = w.biobuzz.hives[alliance];
      return {
        label,
        alliance,
        staged: { pollen: p, nectar: n },
        hive_in: before,
        hive_out: h,
        nectar_due: w.biobuzz.nectarDue[alliance],
        spill: w.biobuzz.spill ?? null,
        events: w.events.slice(ev0),
      };
    });
    cases.push(out);
  };
  const upN = (a: string) => (a === 'blue' ? 'north' : 'south');
  for (const alliance of ['blue', 'red']) {
    const s = alliance === 'blue' ? 1 : -1; // up sign
    const up = upN(alliance);
    mk(alliance, 4, 0, { up, angle: s * REST_RAD, angVel: 0, tipping: 0, released: false }, 'settled at the near stop');
    mk(alliance, 4, 0, { up, angle: s * 0.50, angVel: 0.1, tipping: 0, released: false }, 'just off the stop: tags the cell contents as spill, starts tipping');
    mk(alliance, 4, 0, { up, angle: s * 0.2, angVel: -s * 0.3, tipping: 2, released: false }, 'mid swing before level');
    mk(alliance, 4, 0, { up, angle: -s * 0.1, angVel: -s * 0.3, tipping: 2, released: false }, 'passes level: releases and writes the SPILLS event');
    mk(alliance, 4, 0, { up, angle: 0, angVel: -s * 0.3, tipping: 2, released: false }, 'exactly level');
    mk(alliance, 4, 0, { up, angle: -s * REST_RAD, angVel: -s * 0.05, tipping: 0.01, released: true }, 'far stop, spent: scores the TIP and flips up');
    mk(alliance, 4, 0, { up, angle: -s * REST_RAD, angVel: -s * 0.2, tipping: 0.01, released: true }, 'far stop but still moving (above BB3_HIVE_REST_W)');
    mk(alliance, 4, 0, { up, angle: s * REST_RAD, angVel: 0.01, tipping: 1, released: true }, 'swing failed: back on its own stop, resets tipping and released');
    mk(alliance, 0, 0, { up, angle: s * 0.50, angVel: 0, tipping: 0, released: false }, 'empty cell just off the stop');
  }
  // angle absent: the function reads the body's own tilt (full precision, not the rounded JSON)
  mk('blue', 4, 0, { angle: undefined, angVel: undefined, tipping: 0, released: false }, 'hive.angle and angVel undefined: reads trayTilt(body)');
  emit('joint_tick.json', [HIVE3D], 'hive3dJointTick (hiveDynamicTick) called directly on staged hive states, one call each', {
    note: 'hive_in is the BiobuzzState hive record handed in; elements are staged by fillCell in the up cell; hive.angle undefined means the key is absent',
  }, { cases: JSON.parse(JSON.stringify(cases)) });
}

// =============================== G409 contact pass ===============================
{
  function tipWithRobot(under: boolean, seed: number): any {
    return withTray(() => {
      const w = mkWorld(seed);
      fillCell(w, A, 8, 0);
      const theta = TILT.hiveTiltAngle(w, A);
      const upSide: 1 | -1 = w.biobuzz.hives[A].up === 'north' ? 1 : -1;
      const r = w.robots[0];
      if (under) {
        const box = BODIES.hiveCellLocalBox(upSide, A);
        const mouthV = upSide > 0 ? box.vMax : box.vMin;
        const { a: y } = M3.rotate2(mouthV, box.wMin, theta);
        r.pos.x = BODIES.hivePivotX(A);
        r.pos.y = y;
        r.heading = 0;
        r.vel.x = 0;
        r.vel.y = 0;
      } else {
        r.pos.x = 0;
        r.pos.y = 60;
      }
      const spill_n: number[] = [];
      const g409_total: number[] = [];
      const lowest_tagged_z_in: number[] = [];
      const events: [number, string][] = [];
      let g409 = 0;
      for (let t = 0; t < 600; t++) {
        const nEv = w.events.length;
        S3.step3d(w, DT, new Map());
        const spill = w.biobuzz.spill ?? {};
        spill_n.push(Object.keys(spill).length);
        let low = 1e9;
        for (const b of w.balls) if (spill[b.id] !== undefined && b.z < low) low = b.z;
        lowest_tagged_z_in.push(low === 1e9 ? -1 : low);
        for (const e of w.events.slice(nEv)) {
          events.push([t, e]);
          if (e.includes('G409')) g409++;
        }
        g409_total.push(g409);
      }
      const hv = w.biobuzz.hives[A];
      return {
        robot_under_down_cell: under,
        seed,
        robot_start_xy_in: [r.pos.x, r.pos.y],
        final_tips: hv.tips,
        final_spill_map_empty: w.biobuzz.spill === undefined || Object.keys(w.biobuzz.spill).length === 0,
        columns: { spill_n, g409_lines_total: g409_total, lowest_tagged_z_in },
        events,
      };
    });
  }
  const rows = [tipWithRobot(false, 870), tipWithRobot(true, 871)];
  emit('g409_contacts.json', [CONTACTS3D, HIVE3D, 'src/games/biobuzz/sim3d/step3d.ts'],
    'hiveContactPass through step3d: 8P tip with the robot parked away vs under the down cell; spill tag count, G409 events, lowest tagged z per tick', {
      dt_s: DT, ticks: 600, note: 'lowest_tagged_z_in is -1 when no element is tagged that tick; the robot is moved after the engine is built via world.robots[0].pos',
    }, { rows });
}
console.log('done', DSIM_COMMIT, process.version);
