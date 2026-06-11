// ── small helpers: fuzzy search, similarity drivers, the auto-headline ────────

export const reducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const fold = (s) =>
  s
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();

// subsequence + substring scoring over name / nation / club
export function fuzzy(query, players, limit = 8) {
  const q = fold(query.trim());
  if (!q) return [];
  const scored = [];
  for (const p of players) {
    const hay = fold(`${p.name} ${p.nation} ${p.club}`);
    const name = fold(p.name);
    let score = -1;
    if (name.startsWith(q)) score = 100;
    else if (name.includes(q)) score = 80;
    else if (hay.includes(q)) score = 55;
    else {
      // subsequence match
      let i = 0;
      for (const ch of hay) if (ch === q[i]) i++;
      if (i === q.length) score = 30;
    }
    if (score > 0) scored.push([score + Math.min(20, (p.minutes || 0) / 200), p]);
  }
  scored.sort((a, b) => b[0] - a[0]);
  return scored.slice(0, limit).map((s) => s[1]);
}

// the 3 dimensions where two players are most alike + the 1 where most apart,
// read off their percentile vectors (radar features = curated + labelled)
export function drivers(hero, other, radarKeys, labelOf) {
  const rows = radarKeys.map((k) => ({
    key: k,
    label: labelOf(k),
    a: hero.pct[k],
    b: other.pct[k],
    gap: Math.abs(hero.pct[k] - other.pct[k]),
  }));
  const alike = [...rows].sort((x, y) => x.gap - y.gap).slice(0, 3);
  const apart = [...rows].sort((x, y) => y.gap - x.gap)[0];
  return { alike, apart };
}

// every selection produces a sentence, not just a number
export function headline(hero, neighbour, score) {
  if (!neighbour) return `Pick a neighbour to compare with ${hero.name}.`;
  const da = (hero.age || 0) - (neighbour.age || 0);
  const last = hero.name.split(" ").slice(-1)[0];
  if (da >= 2)
    return `Looking for a younger ${hero.name}? Meet ${neighbour.name} — ${score}% similar, and ${da} years younger.`;
  if (da <= -3)
    return `${neighbour.name} is the closest match to ${hero.name} — ${score}% similar, with ${-da} more years in the legs.`;
  return `Who plays like ${hero.name}? ${neighbour.name} is the closest match — ${score}% similar${
    Math.abs(da) <= 1 ? ", and almost exactly the same age." : "."
  }`;
}

export const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
