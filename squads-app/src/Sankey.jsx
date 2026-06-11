import { useMemo } from "react";
import { sankey, sankeyLinkHorizontal, sankeyJustify } from "d3-sankey";

// Categorical colours for the destination leagues/clubs (house palette family).
const PALETTE = ["#b06a16", "#2a8f8f", "#4a6d8c", "#3a8f57", "#c0533b", "#7d5ba6",
  "#9a7b1e", "#1f6e6e", "#8c6d4a", "#5a8c3a", "#a8473b", "#6a5b9a"];

export function colorFor(name, i) {
  return PALETTE[i % PALETTE.length];
}

// Pure-layout wrapper: d3-sankey computes geometry, React renders the SVG. The
// `active` nation (hovered or selected) isolates its ribbons; everything else dims.
export default function Sankey({ nodes, links, height, active, onHover, showSourceLabels }) {
  const W = 720;
  const layout = useMemo(() => {
    if (!nodes.length || !links.length) return null;
    const sk = sankey()
      .nodeId((d) => d.id)
      .nodeWidth(13)
      .nodePadding(showSourceLabels ? 12 : 4)
      .nodeAlign(sankeyJustify)
      .extent([[1, 6], [W - 1, height - 6]]);
    return sk({
      nodes: nodes.map((d) => ({ ...d })),
      links: links.map((d) => ({ ...d })),
    });
  }, [nodes, links, height, showSourceLabels]);

  if (!layout) return <div className="sankey-empty">No flows to show.</div>;

  const targetColor = {};
  layout.nodes.filter((n) => n.side !== "nation").forEach((n, i) => (targetColor[n.id] = colorFor(n.name, i)));
  const path = sankeyLinkHorizontal();
  const isActive = (l) => !active || l.source.name === active;

  return (
    <svg className="sankey" viewBox={`0 0 ${W} ${height}`} role="img"
         aria-label="Sankey of national squads to leagues">
      <g>
        {layout.links.map((l, i) => (
          <path
            key={i} d={path(l)} fill="none"
            stroke={targetColor[l.target.id] || "#b06a16"}
            strokeWidth={Math.max(1, l.width)}
            strokeOpacity={active ? (isActive(l) ? 0.62 : 0.05) : 0.34}
            onMouseEnter={() => onHover(l.source.name)}
            onMouseLeave={() => onHover(null)}
            style={{ cursor: "pointer", transition: "stroke-opacity .12s" }}
          >
            <title>{`${l.source.name} → ${l.target.name}: ${l.value}`}</title>
          </path>
        ))}
      </g>
      <g>
        {layout.nodes.map((n) => {
          const nation = n.side === "nation";
          const on = !active || n.name === active || (!nation);
          const dimNation = nation && active && n.name !== active;
          return (
            <g key={n.id} transform={`translate(${n.x0},${n.y0})`}
               onMouseEnter={() => nation && onHover(n.name)}
               onMouseLeave={() => nation && onHover(null)}
               style={{ cursor: nation ? "pointer" : "default" }}>
              <rect
                width={n.x1 - n.x0} height={Math.max(1, n.y1 - n.y0)} rx={2}
                fill={nation ? "#b06a16" : (targetColor[n.id] || "#2a8f8f")}
                fillOpacity={dimNation ? 0.25 : 0.9}
              >
                <title>{`${n.name}: ${n.value}`}</title>
              </rect>
              {/* league/club labels (right side) always; nation labels on demand */}
              {!nation && (
                <text className="sk-label" x={(n.x1 - n.x0) + 6} y={(n.y1 - n.y0) / 2}
                      dy="0.35em">{n.name}</text>
              )}
              {nation && (showSourceLabels || n.name === active) && (
                <text className="sk-label src" x={-6} y={(n.y1 - n.y0) / 2}
                      dy="0.35em" textAnchor="end"
                      fillOpacity={dimNation ? 0.3 : 1}>{n.name}</text>
              )}
            </g>
          );
        })}
      </g>
    </svg>
  );
}
