import { formatPercent } from "@/lib/api/revision";

/** Small dependency-free SVG charts. Colours come from the theme's chart tokens. */

export interface TrendPoint {
  label: string;
  value: number | null;
}

const W = 320;
const H = 140;
const PAD = { top: 10, right: 10, bottom: 22, left: 30 };

/** x/y positions for a 0-100 series spread evenly across the plot area. */
export function trendCoordinates(points: TrendPoint[]) {
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  return points
    .map((p, i) => ({ p, i }))
    .filter(({ p }) => p.value !== null)
    .map(({ p, i }) => ({
      label: p.label,
      value: p.value as number,
      x: PAD.left + (points.length === 1 ? innerW / 2 : (i / (points.length - 1)) * innerW),
      y: PAD.top + innerH - (Math.min(100, Math.max(0, p.value as number)) / 100) * innerH,
    }));
}

export function TrendChart({ title, points }: { title: string; points: TrendPoint[] }) {
  const coords = trendCoordinates(points);
  if (coords.length === 0) return null;
  const line = coords.map((c) => `${c.x},${c.y}`).join(" ");
  return (
    <figure className="space-y-2">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`${title}: ${coords.length} results, latest ${formatPercent(coords[coords.length - 1].value)}`}
        className="h-auto w-full max-w-xl"
      >
        {[0, 50, 100].map((tick) => {
          const y = PAD.top + (H - PAD.top - PAD.bottom) * (1 - tick / 100);
          return (
            <g key={tick}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y} stroke="var(--border)" />
              <text x={PAD.left - 4} y={y + 3} textAnchor="end" fontSize="9" fill="currentColor">
                {tick}%
              </text>
            </g>
          );
        })}
        {coords.length > 1 ? (
          <polyline fill="none" stroke="var(--chart-1)" strokeWidth="2" points={line} />
        ) : null}
        {coords.map((c) => (
          <circle key={`${c.label}-${c.x}`} cx={c.x} cy={c.y} r="3" fill="var(--chart-1)">
            <title>{`${c.label}: ${formatPercent(c.value)}`}</title>
          </circle>
        ))}
      </svg>
      <figcaption className="text-muted-foreground text-xs">{title}</figcaption>
    </figure>
  );
}

export interface BarDatum {
  label: string;
  value: number;
}

/** Bar heights as 0-1 fractions of the largest value (all zero gives zero bars). */
export function barFractions(data: BarDatum[]): number[] {
  const max = Math.max(0, ...data.map((d) => d.value));
  return data.map((d) => (max === 0 ? 0 : d.value / max));
}

export function BarChart({ title, data }: { title: string; data: BarDatum[] }) {
  if (data.length === 0) return null;
  const fractions = barFractions(data);
  const total = data.reduce((sum, d) => sum + d.value, 0);
  const slot = (W - PAD.left - PAD.right) / data.length;
  const innerH = H - PAD.top - PAD.bottom;
  return (
    <figure className="space-y-2">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`${title}: ${total} in total over ${data.length} days`}
        className="h-auto w-full max-w-xl"
      >
        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={H - PAD.bottom}
          y2={H - PAD.bottom}
          stroke="var(--border)"
        />
        {data.map((d, i) => {
          const h = fractions[i] * innerH;
          return (
            <rect
              key={d.label}
              x={PAD.left + i * slot + slot * 0.15}
              y={H - PAD.bottom - h}
              width={Math.max(1, slot * 0.7)}
              height={h}
              fill="var(--chart-2)"
            >
              <title>{`${d.label}: ${d.value}`}</title>
            </rect>
          );
        })}
        <text x={PAD.left} y={H - 6} fontSize="9" fill="currentColor">
          {data[0].label}
        </text>
        <text x={W - PAD.right} y={H - 6} fontSize="9" textAnchor="end" fill="currentColor">
          {data[data.length - 1].label}
        </text>
      </svg>
      <figcaption className="text-muted-foreground text-xs">{title}</figcaption>
    </figure>
  );
}
