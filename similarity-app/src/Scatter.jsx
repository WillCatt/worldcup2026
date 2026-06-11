import React, { useRef, useEffect, useCallback } from "react";
import { clamp, reducedMotion } from "./util.js";

const PAD = 42;

// data coords (0..100, y already "up") -> base canvas px (pre-transform)
function baseProject(W, H) {
  return (x, y) => [PAD + (x / 100) * (W - 2 * PAD), PAD + ((100 - y) / 100) * (H - 2 * PAD)];
}

export default function Scatter({
  ex, heroId, neighbourIds, minMinutes, layout, onSelect, onHover,
}) {
  const canvasRef = useRef(null);
  const wrapRef = useRef(null);
  const tf = useRef({ k: 1, x: 0, y: 0 });
  const anim = useRef(null);
  const drag = useRef(null);
  const size = useRef({ W: 0, H: 0 });
  const tipRef = useRef(null);

  const players = ex.players;
  const coordOf = (p) => (layout === "pca" ? p.pca : p.umap);

  // ── draw ────────────────────────────────────────────────────────────────
  const draw = useCallback(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const { W, H } = size.current;
    const ctx = cv.getContext("2d");
    const { k, x: tx, y: ty } = tf.current;
    const bp = baseProject(W, H);
    const S = (x, y) => {
      const [bx, by] = bp(x, y);
      return [bx * k + tx, by * k + ty];
    };
    ctx.clearRect(0, 0, W, H);

    const hero = players.find((p) => p.id === heroId);
    const nbset = neighbourIds;

    // archetype hulls (the landscape) — behind everything
    for (const c of ex.clusters) {
      if (!c.hull || c.hull.length < 3) continue;
      ctx.beginPath();
      c.hull.forEach((pt, i) => {
        // push each vertex slightly out from the centroid for breathing room
        const ox = c.centroid[0] + (pt[0] - c.centroid[0]) * 1.08;
        const oy = c.centroid[1] + (pt[1] - c.centroid[1]) * 1.08;
        const [sx, sy] = S(ox, oy);
        i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy);
      });
      ctx.closePath();
      ctx.fillStyle = c.color + "22";
      ctx.fill();
      ctx.strokeStyle = c.color + "44";
      ctx.lineWidth = 1;
      ctx.stroke();
    }
    // cluster labels at centroid
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (const c of ex.clusters) {
      const [sx, sy] = S(c.centroid[0], c.centroid[1]);
      ctx.font = "600 12px 'Space Grotesk', sans-serif";
      ctx.fillStyle = "rgba(26,23,20,0.34)";
      ctx.fillText(c.label.toUpperCase(), sx, sy);
    }

    const heroActive = !!hero;
    const colorById = Object.fromEntries(ex.clusters.map((c) => [c.id, c.color]));

    // context dots
    for (const p of players) {
      const below = p.minutes < minMinutes;
      const isHero = p.id === heroId;
      const isNbr = nbset.has(p.id);
      if (isHero || isNbr) continue;
      const [sx, sy] = S(...coordOf(p));
      const col = colorById[p.cluster] || "#999";
      ctx.beginPath();
      ctx.arc(sx, sy, below ? 3.4 : 4.4, 0, 6.2832);
      if (below) {
        ctx.strokeStyle = col + (heroActive ? "55" : "88");
        ctx.lineWidth = 1.1;
        ctx.stroke();
      } else {
        ctx.fillStyle = col + (heroActive ? "44" : "cc");
        ctx.fill();
      }
    }

    // spokes hero -> neighbours
    if (hero) {
      const [hx, hy] = S(...coordOf(hero));
      for (const p of players) {
        if (!nbset.has(p.id)) continue;
        const [sx, sy] = S(...coordOf(p));
        ctx.beginPath();
        ctx.moveTo(hx, hy);
        ctx.lineTo(sx, sy);
        ctx.strokeStyle = "#b06a1655";
        ctx.lineWidth = 1.4;
        ctx.stroke();
      }
      // neighbour dots + labels
      ctx.font = "500 11.5px 'Space Grotesk', sans-serif";
      for (const p of players) {
        if (!nbset.has(p.id)) continue;
        const [sx, sy] = S(...coordOf(p));
        ctx.beginPath();
        ctx.arc(sx, sy, 6.2, 0, 6.2832);
        ctx.fillStyle = colorById[p.cluster] || "#999";
        ctx.fill();
        ctx.strokeStyle = "#fffdfa";
        ctx.lineWidth = 1.6;
        ctx.stroke();
        ctx.fillStyle = "#1a1714";
        ctx.fillText(p.name.split(" ").slice(-1)[0], sx, sy - 11);
      }
      // hero dot
      const [hsx, hsy] = S(...coordOf(hero));
      ctx.beginPath();
      ctx.arc(hsx, hsy, 9, 0, 6.2832);
      ctx.fillStyle = "#b06a16";
      ctx.fill();
      ctx.strokeStyle = "#fffdfa";
      ctx.lineWidth = 2.4;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(hsx, hsy, 13.5, 0, 6.2832);
      ctx.strokeStyle = "#b06a1688";
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.font = "600 13px 'Space Grotesk', sans-serif";
      ctx.fillStyle = "#1a1714";
      ctx.fillText(hero.name, hsx, hsy - 19);
    }
  }, [ex, heroId, neighbourIds, minMinutes, layout, players]);

  // ── camera fit helpers ────────────────────────────────────────────────
  const fitTo = useCallback(
    (pts, animate = true) => {
      const { W, H } = size.current;
      if (!W || !pts.length) return;
      const bp = baseProject(W, H);
      const bs = pts.map((p) => bp(...coordOf(p)));
      let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
      for (const [bx, by] of bs) {
        minx = Math.min(minx, bx); maxx = Math.max(maxx, bx);
        miny = Math.min(miny, by); maxy = Math.max(maxy, by);
      }
      const bw = Math.max(maxx - minx, 60), bh = Math.max(maxy - miny, 60);
      const k = clamp(Math.min((W * 0.62) / bw, (H * 0.62) / bh), 1, 5.5);
      const cx = (minx + maxx) / 2, cy = (miny + maxy) / 2;
      const target = { k, x: W / 2 - cx * k, y: H / 2 - cy * k };
      animateTo(target, animate);
    },
    [coordOf, layout] // eslint-disable-line
  );

  const animateTo = (target, animate = true) => {
    if (anim.current) cancelAnimationFrame(anim.current);
    if (!animate || reducedMotion()) {
      tf.current = target;
      draw();
      return;
    }
    const start = { ...tf.current };
    const t0 = performance.now();
    const dur = 520;
    const ease = (t) => 1 - Math.pow(1 - t, 3);
    const step = (now) => {
      const t = clamp((now - t0) / dur, 0, 1);
      const e = ease(t);
      tf.current = {
        k: start.k + (target.k - start.k) * e,
        x: start.x + (target.x - start.x) * e,
        y: start.y + (target.y - start.y) * e,
      };
      draw();
      if (t < 1) anim.current = requestAnimationFrame(step);
    };
    anim.current = requestAnimationFrame(step);
  };

  // ── resize / DPR ──────────────────────────────────────────────────────
  useEffect(() => {
    const cv = canvasRef.current;
    const resize = () => {
      const W = wrapRef.current.clientWidth;
      const H = wrapRef.current.clientHeight;
      size.current = { W, H };
      const dpr = window.devicePixelRatio || 1;
      cv.width = W * dpr;
      cv.height = H * dpr;
      cv.style.width = W + "px";
      cv.style.height = H + "px";
      cv.getContext("2d").setTransform(dpr, 0, 0, dpr, 0, 0);
      draw();
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [draw]);

  // fly camera when hero/group/layout changes
  const heroRef = useRef(heroId);
  useEffect(() => {
    const hero = players.find((p) => p.id === heroId);
    const focus = hero
      ? [hero, ...players.filter((p) => neighbourIds.has(p.id))]
      : players;
    fitTo(focus, true);
    heroRef.current = heroId;
    // eslint-disable-next-line
  }, [heroId, ex, layout]);

  useEffect(() => { draw(); }, [draw, minMinutes, neighbourIds]);

  // ── interaction ───────────────────────────────────────────────────────
  const screenToHit = (mx, my) => {
    const { k, x: tx, y: ty } = tf.current;
    const { W, H } = size.current;
    const bp = baseProject(W, H);
    let best = null, bd = 14 * 14;
    for (const p of players) {
      const [bx, by] = bp(...coordOf(p));
      const sx = bx * k + tx, sy = by * k + ty;
      const d = (sx - mx) ** 2 + (sy - my) ** 2;
      if (d < bd) { bd = d; best = p; }
    }
    return best;
  };

  const onMove = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    if (drag.current) {
      tf.current = {
        ...tf.current,
        x: drag.current.x + (mx - drag.current.mx),
        y: drag.current.y + (my - drag.current.my),
      };
      draw();
      return;
    }
    const hit = screenToHit(mx, my);
    onHover(hit ? hit.id : null);
    const tip = tipRef.current;
    if (hit && tip) {
      tip.style.display = "block";
      tip.style.left = mx + "px";
      tip.style.top = my + "px";
      tip.innerHTML = `<div class="tn">${hit.name}</div><div class="tm">${hit.flag} ${hit.nation} · ${hit.club}</div>`;
    } else if (tip) tip.style.display = "none";
  };

  const onDown = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    drag.current = { mx, my, x: tf.current.x, y: tf.current.y, moved: false, t: Date.now() };
    canvasRef.current.classList.add("grabbing");
  };
  const onUp = (e) => {
    const d = drag.current;
    canvasRef.current.classList.remove("grabbing");
    drag.current = null;
    if (!d) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const moved = Math.hypot(mx - d.mx, my - d.my) > 4;
    if (!moved) {
      const hit = screenToHit(mx, my);
      if (hit) onSelect(hit.id);
    }
  };
  const onWheel = (e) => {
    e.preventDefault();
    const rect = canvasRef.current.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const { k, x, y } = tf.current;
    const factor = Math.exp(-e.deltaY * 0.0014);
    const nk = clamp(k * factor, 0.7, 9);
    tf.current = { k: nk, x: mx - (mx - x) * (nk / k), y: my - (my - y) * (nk / k) };
    draw();
  };

  return (
    <div ref={wrapRef} className="mapviewport">
      <canvas
        ref={canvasRef}
        className="mapcanvas"
        onMouseMove={onMove}
        onMouseDown={onDown}
        onMouseUp={onUp}
        onMouseLeave={(e) => { onUp(e); onHover(null); if (tipRef.current) tipRef.current.style.display = "none"; }}
        onWheel={onWheel}
      />
      <div ref={tipRef} className="tooltip" style={{ display: "none" }} />
    </div>
  );
}
