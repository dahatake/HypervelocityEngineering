// FR-1053 / FR-1055: the world of the RPG-style map. Pure functions (no DOM), so layout and walking rules are testable.
// Castles = business goals (G-ID), towns = entities (data kinds). Q-016 [ASSUMPTION]: 1 entity = 1 town.

export const DIRS = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };

// Layout: a row block of castles at the top, a pond with bridges, then rows of towns. Every entrance is reachable.
export function buildWorld(castles, towns) {
  const n = Math.max(castles.length, towns.length, 1);
  const cols = Math.max(3, Math.min(12, Math.ceil(Math.sqrt(n))));
  const width = 3 * cols + 2;
  const blocked = new Set();
  const key = (x, y) => x + ',' + y;
  const places = [];
  const lay = (items, kind, bodyY0) => {
    let lastY = bodyY0;
    items.forEach((it, i) => {
      const x = 2 + 3 * (i % cols), by = bodyY0 + 3 * Math.floor(i / cols);
      if (kind === 'castle') for (const dx of [-1, 0, 1]) blocked.add(key(x + dx, by)); else blocked.add(key(x, by));
      places.push({ ...it, kind, x, y: by + 1 });
      lastY = by + 1;
    });
    return lastY;
  };
  const lastCastle = lay(castles, 'castle', 1);
  const pondY = (castles.length ? lastCastle : 1) + 2;
  for (let x = 0; x < width; x++) if (x % 3 !== 2) blocked.add(key(x, pondY));
  const lastTown = lay(towns, 'town', pondY + 2);
  const height = Math.max(lastTown, pondY) + 3;
  return { width, height, blocked, key, places, pondY, start: { x: 1, y: (castles.length ? lastCastle : 1) + 1 },
    pathRows: new Set([...Array(height).keys()].filter((y) => y !== pondY && !places.some((p) => p.y - 1 === y))) };
}

// One step on the grid. Out-of-map and blocked cells are refused; the facing direction still changes.
export function stepOn(world, player, dir) {
  const [dx, dy] = DIRS[dir];
  const nx = player.x + dx, ny = player.y + dy;
  const ok = nx >= 0 && ny >= 0 && nx < world.width && ny < world.height && !world.blocked.has(world.key(nx, ny));
  return ok ? { x: nx, y: ny, dir, moved: true } : { x: player.x, y: player.y, dir, moved: false };
}

export const placeAt = (world, x, y) => world.places.find((p) => p.x === x && p.y === y) || null;

// Key assignment (FR-1055). Select = Shift pressed alone. Tab is never used (it stays for moving focus).
export const KEYMAP = {
  dpad: { up: ['ArrowUp', 'w', 'W'], down: ['ArrowDown', 's', 'S'], left: ['ArrowLeft', 'a', 'A'], right: ['ArrowRight', 'd', 'D'] },
  a: ['Enter', 'z', 'Z'],
  b: ['Escape', 'x', 'X', 'Backspace'],
  start: [' '],
  select: ['Shift'],
};
export function buttonOf(e) {
  if (e.ctrlKey || e.metaKey || e.altKey) return null;           // browser / OS / assistive shortcuts are left alone
  const k = e.key;
  for (const [d, keys] of Object.entries(KEYMAP.dpad)) if (keys.includes(k)) return d;
  if (k === 'Enter' || k === 'z' || k === 'Z') return 'a';
  if (k === 'Escape' || k === 'x' || k === 'X' || k === 'Backspace') return 'b';
  if (k === ' ' || k === 'Spacebar') return 'start';
  return null;
}
