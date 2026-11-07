const hive = await import('/tmp/dsim-src/src/games/biobuzz/hive.ts');
const cfg = await import('/tmp/dsim-src/src/games/biobuzz/config.ts');
const math = await import('/tmp/dsim-src/src/math.ts');
console.log(Object.keys(hive).join(' '));
console.log(Object.keys(cfg).length, cfg.BB_TIP_POLLEN, cfg.BB_HIVE_X, cfg.BB_CELL_OPEN, cfg.BB_HIVE_OPEN_Z);
console.log(Object.keys(math).join(' '));
