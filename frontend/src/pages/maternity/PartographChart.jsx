// Custom SVG partograph — no chart library, consistent with the bundle-size
// budget. Geometry is exported pure so tests can pin the WHO line positions.
const PLOT = { x0: 60, x1: 700, y0: 40, y1: 300, hours: 12, maxCm: 10 };

export const xForHours = (h) => PLOT.x0 + h * ((PLOT.x1 - PLOT.x0) / PLOT.hours);
export const yForDilation = (cm) => PLOT.y1 - cm * ((PLOT.y1 - PLOT.y0) / PLOT.maxCm);
export const alertLinePoints = () => ({
  x1: xForHours(0), y1: yForDilation(4), x2: xForHours(6), y2: yForDilation(10),
});
export const actionLinePoints = () => ({
  x1: xForHours(4), y1: yForDilation(4), x2: xForHours(10), y2: yForDilation(10),
});

const hoursSince = (iso, startIso) =>
  (new Date(iso).getTime() - new Date(startIso).getTime()) / 3600000;

export default function PartographChart({ entries = [], activeStart = null }) {
  const alert = alertLinePoints();
  const action = actionLinePoints();
  const plotted = activeStart
    ? entries
        .filter((e) => e.cervical_dilation_cm != null)
        .map((e) => ({ ...e, h: hoursSince(e.recorded_at, activeStart) }))
        .filter((e) => e.h >= 0 && e.h <= PLOT.hours)
    : [];
  const current = plotted.filter((e) => !e.superseded);
  const fhr = activeStart
    ? entries
        .filter((e) => e.fetal_heart_rate != null && !e.superseded)
        .map((e) => ({ ...e, h: hoursSince(e.recorded_at, activeStart) }))
        .filter((e) => e.h >= 0 && e.h <= PLOT.hours)
    : [];

  return (
    <svg viewBox="0 0 720 420" role="img" aria-label="Partograph chart"
         className="w-full rounded-md border border-ink-200 dark:border-ink-700 bg-white dark:bg-ink-900">
      {/* grid */}
      {Array.from({ length: PLOT.hours + 1 }, (_, h) => (
        <g key={`gx${h}`}>
          <line x1={xForHours(h)} y1={PLOT.y0} x2={xForHours(h)} y2={PLOT.y1}
                stroke="currentColor" className="text-ink-200 dark:text-ink-700" strokeWidth="0.5" />
          <text x={xForHours(h)} y={PLOT.y1 + 16} textAnchor="middle"
                className="fill-ink-500 dark:fill-ink-400" fontSize="10">{h}h</text>
        </g>
      ))}
      {Array.from({ length: PLOT.maxCm + 1 }, (_, cm) => (
        <g key={`gy${cm}`}>
          <line x1={PLOT.x0} y1={yForDilation(cm)} x2={PLOT.x1} y2={yForDilation(cm)}
                stroke="currentColor" className="text-ink-200 dark:text-ink-700" strokeWidth="0.5" />
          <text x={PLOT.x0 - 8} y={yForDilation(cm) + 3} textAnchor="end"
                className="fill-ink-500 dark:fill-ink-400" fontSize="10">{cm}</text>
        </g>
      ))}

      {/* WHO alert + action lines */}
      <line {...alert} stroke="#f59e0b" strokeWidth="1.5" strokeDasharray="6 3" />
      <text x={alert.x2 + 4} y={alert.y2 + 4} fontSize="10" fill="#f59e0b">Alert</text>
      <line {...action} stroke="#dc2626" strokeWidth="1.5" strokeDasharray="6 3" />
      <text x={action.x2 + 4} y={action.y2 + 4} fontSize="10" fill="#dc2626">Action</text>

      {/* dilation curve (current entries only) */}
      {current.length > 1 && (
        <polyline
          points={current
            .sort((a, b) => a.h - b.h)
            .map((e) => `${xForHours(e.h)},${yForDilation(e.cervical_dilation_cm)}`)
            .join(' ')}
          fill="none" stroke="#2563eb" strokeWidth="2"
        />
      )}
      {plotted.map((e) => (
        <circle key={e.entry_id} data-kind="dilation"
                cx={xForHours(e.h)} cy={yForDilation(e.cervical_dilation_cm)} r="4"
                fill={e.superseded ? 'none' : '#2563eb'}
                stroke="#2563eb" strokeWidth="1.5" />
      ))}

      {/* FHR strip (340–400 y-band; the backend accepts 40–240 bpm on partograph
          entries, wider than the 60–200 this formula maps into the band, so
          the plotted y is clamped to [340, 400] below — an extreme value sits
          at the band edge instead of drifting past it) */}
      <text x={PLOT.x0} y={334} fontSize="10" className="fill-ink-500 dark:fill-ink-400">FHR</text>
      {fhr.map((e) => {
        const rawY = 400 - ((e.fetal_heart_rate - 60) / 140) * 60;
        const y = Math.min(400, Math.max(340, rawY));
        return <circle key={`fhr${e.entry_id}`} data-kind="fhr"
                       cx={xForHours(e.h)} cy={y} r="3" fill="#16a34a" />;
      })}
      {!activeStart && (
        <text x="380" y="180" textAnchor="middle" fontSize="12"
              className="fill-ink-500 dark:fill-ink-400">
          Active labor not started — chart begins at the first ≥4 cm entry.
        </text>
      )}
    </svg>
  );
}
