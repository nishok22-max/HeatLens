import type { Insights } from "../types";
import { Panel } from "./ui";

/**
 * Sensitivity Analysis — What drives the heat right now.
 */
export function Drivers({ insights }: { insights: Insights }) {
  const drivers = [...insights.drivers].sort((a, b) => b.share - a.share);
  const colours = [
    "var(--color-ramp-6)",
    "var(--color-ramp-4)",
    "var(--color-ramp-2)",
    "var(--color-ramp-1)",
  ];

  const top = drivers[0];
  const R = 54;
  const C = 2 * Math.PI * R;

  // Compute accumulated dash offsets
  const offsets = drivers.reduce<number[]>((acc, _, i) => {
    const prev = i === 0 ? 0 : acc[i - 1];
    const len = (drivers[i - 1]?.share ?? 0) / 100 * C;
    acc.push(prev + len);
    return acc;
  }, []);

  const windRaises = drivers.some(
    (d) => d.driver === "Wind" && d.direction === "raises",
  );

  return (
    <Panel
      title="What is driving the heat?"
      subtitle="How much each part of the weather adds to the heat people feel"
    >
      <div className="flex flex-col sm:flex-row items-center gap-6">
        <div className="relative shrink-0">
          <svg width="150" height="150" viewBox="0 0 140 140" role="img"
               aria-label={`Largest driver contribution: ${top?.driver} at ${top?.share}% share`}>
            <circle cx="70" cy="70" r={R} fill="none" stroke="var(--color-sunken)"
                    strokeWidth="18" />
            {drivers.map((d, i) => {
              const len = (d.share / 100) * C;
              const currentOffset = offsets[i] ?? 0;
              return (
                <circle
                  key={d.driver}
                  cx="70" cy="70" r={R} fill="none"
                  stroke={colours[i % colours.length]}
                  strokeWidth="18"
                  strokeDasharray={`${len} ${C - len}`}
                  strokeDashoffset={-currentOffset}
                  transform="rotate(-90 70 70)"
                  className="transition-all duration-300 hover:opacity-80"
                />
              );
            })}
          </svg>

          <div className="absolute inset-0 grid place-items-center pointer-events-none">
            <div className="text-center px-2">
              <div className="text-[9px] font-black uppercase tracking-wider text-ink-faint leading-none">
                TOP DRIVER
              </div>
              <div className="text-[22px] font-black text-ink tnum leading-tight tracking-tight my-0.5">
                {top ? `${top.share.toFixed(0)}%` : "—"}
              </div>
              <div className="text-[10px] font-extrabold text-accent uppercase leading-tight truncate max-w-28">
                {top?.driver}
              </div>
            </div>
          </div>
        </div>

        <div className="flex-1 min-w-0 w-full space-y-2.5">
          <div className="text-[10px] uppercase font-black tracking-wider text-ink-faint">
            Contribution to current heat-stress signal
          </div>
          <ul className="space-y-2">
            {drivers.map((d, i) => (
              <li key={d.driver} className="flex items-center gap-2.5 text-[12px] bg-sunken/40 p-2 rounded-xl border border-line/60">
                <span
                  className="w-3 h-3 rounded-full shrink-0 shadow-2xs"
                  style={{ background: colours[i % colours.length] }}
                  aria-hidden
                />
                <span className="text-ink font-bold flex-1 truncate">{d.driver}</span>
                <span
                  className={`text-[10px] font-black uppercase px-2 py-0.5 rounded-md border ${
                    d.direction === "raises"
                      ? "bg-flag-bg text-flag border-flag/30"
                      : "bg-ok-bg text-ok border-ok/30"
                  }`}
                >
                  {d.direction === "raises" ? "+ Raises" : "- Lowers"}
                </span>
                <span className="tnum font-black text-ink w-12 text-right">
                  {d.share.toFixed(0)}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {windRaises && (
        <div className="mt-4 p-3 bg-flag-bg/70 border border-flag/30 rounded-xl shadow-2xs">
          <p className="text-[12px] leading-relaxed text-ink-soft font-medium">
            <strong className="text-flag font-black">⚠️ Wind Amplification Alert:</strong>{" "}
            Above ~35 °C skin temperature, air movement delivers convective heat to the human body faster than sweat evaporation can cool it. Wind acts like a convection oven at extreme temperatures.
          </p>
        </div>
      )}
    </Panel>
  );
}



