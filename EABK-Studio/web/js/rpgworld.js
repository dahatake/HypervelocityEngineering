// FR-1053 / FR-1055: the world of the RPG-style map. Pure functions (no DOM), so layout and walking rules are testable.
// Castles = business goals (G-ID). Towns = groups of entities (connected components of the FR-1026 relations; entities
// without a relation share one "no-relation town"). Residents = one entity each, standing inside their town (Q-016 2026-10-17).

export const DIRS = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };

// Group entities by the connected components of their relations. Pure, so the "every entity in exactly one town" rule is testable.
// Returns [{ id, none, members: [entityName...] }]; components of size >= 2 are towns, the loners go to one "none" town (last).
export function groupEntities(names, relations) {
  const set = new Set(names), parent = new Map(names.map((n) => [n, n]));
  const find = (a) => { while (parent.get(a) !== a) { parent.set(a, parent.get(parent.get(a))); a = parent.get(a); } return a; };
  for (const r of relations) if (set.has(r.from) && set.has(r.to)) parent.set(find(r.from), find(r.to));
  const comps = new Map();
  for (const n of names) { const k = find(n); if (!comps.has(k)) comps.set(k, []); comps.get(k).push(n); }
  const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const towns = [], loners = [];
  for (const m of comps.values()) { m.sort(cmp); if (m.length > 1) towns.push({ id: 'town:' + m[0], none: false, members: m }); else loners.push(m[0]); }
  towns.sort((a, b) => cmp(a.members[0], b.members[0]));
  if (loners.length) towns.push({ id: 'town:none', none: true, members: loners.sort(cmp) });
  return towns;
}

// Layout: a row block of castles at the top, a pond with bridges, then one block per town (entrance on the left, residents in a row/grid to its right).
export function buildWorld(castles, towns) {
  const n = Math.max(castles.length, 1);
  const cols = Math.max(3, Math.min(12, Math.ceil(Math.sqrt(n))));
  const width = Math.max(3 * cols + 2, 14);
  const perRow = width - 5;
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
  const residents = [];
  let by = pondY + 2, lastTown = pondY;
  for (const t of towns) {
    blocked.add(key(2, by));
    places.push({ ...t, kind: 'town', x: 2, y: by + 1 });
    const k = t.residents?.length || 0;
    (t.residents || []).forEach((r, i) => residents.push({ ...r, kind: 'resident', town: t.id, x: 4 + (i % perRow), y: by + 1 + Math.floor(i / perRow) }));
    lastTown = by + Math.max(1, Math.ceil(k / perRow));
    by = lastTown + 2;
  }
  const height = Math.max(lastTown, pondY) + 3;
  return { width, height, blocked, key, places, residents, pondY, start: { x: 1, y: (castles.length ? lastCastle : 1) + 1 },
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
