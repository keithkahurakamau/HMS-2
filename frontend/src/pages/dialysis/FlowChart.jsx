// Lightweight intradialytic trend chart (BP systolic, pulse, UF volume) drawn
// as inline SVG — no external chart dependency. Each series is normalized
// independently to the plot height so differently-scaled vitals are comparable.
const SERIES = [
  { key: 'bp_systolic', label: 'BP sys', color: '#ef4444' },
  { key: 'pulse', label: 'Pulse', color: '#3b82f6' },
  { key: 'uf_volume_ml', label: 'UF mL', color: '#10b981' },
];

const W = 100;
const H = 40;

function polyline(obs, key) {
  const vals = obs.map((o) => o[key]).filter((v) => v != null);
  if (vals.length < 2) return null;
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const step = W / (obs.length - 1);
  const pts = [];
  obs.forEach((o, i) => {
    if (o[key] == null) return;
    const x = i * step;
    const y = H - ((o[key] - min) / span) * (H - 4) - 2;
    pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  });
  return pts.join(' ');
}

export default function FlowChart({ observations = [] }) {
  if (!observations.length) {
    return <p className="text-sm text-ink-500 dark:text-ink-400">No observations yet.</p>;
  }
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none"
           className="h-32 w-full rounded-lg bg-ink-50 dark:bg-ink-800/40"
           role="img" aria-label="Dialysis flow chart of BP, pulse and ultrafiltration over the session">
        {SERIES.map((s) => {
          const pts = polyline(observations, s.key);
          return pts ? <polyline key={s.key} points={pts} fill="none" stroke={s.color} strokeWidth="0.8" vectorEffect="non-scaling-stroke" /> : null;
        })}
      </svg>
      <div className="mt-2 flex gap-4 text-xs text-ink-500 dark:text-ink-400">
        {SERIES.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: s.color }} aria-hidden="true" />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}
