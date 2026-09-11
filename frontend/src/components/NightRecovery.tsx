import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { HeatData } from "../types";
import { Note, Panel } from "./ui";
import { weatherSource } from "../summary";

const RECOVERY_THRESHOLD_C = 27;

export function NightRecovery({ data }: { data: HeatData }) {
  const nights = data.city.night_recovery;
  const noRecovery = nights.filter((n) => n.min_c >= RECOVERY_THRESHOLD_C).length;
  const worst = nights.reduce((a, b) => (b.min_c > a.min_c ? b : a), nights[0]);

  const chart = nights.map((n) => ({
    date: n.date.slice(5),
    min_c: n.min_c,
    max_c: n.max_c,
  }));

  return (
    <Panel
      title="Did the nights cool down?"
      subtitle="Lowest overnight air temperature each night (22:00 to 06:00). Bodies need cool nights to recover."
      right={
        <div className="text-right bg-flag-bg border border-flag/30 px-3.5 py-1.5 rounded-xl shadow-2xs">
          <div className="text-[22px] font-black tnum leading-none text-flag">
            {noRecovery}
          </div>
          <div className="text-[10px] uppercase font-black tracking-wider text-flag/90 mt-0.5">
            nights without cooling
          </div>
        </div>
      }
    >
      <div className="h-64 bg-surface p-3 rounded-xl border border-line shadow-2xs">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chart} margin={{ top: 10, right: 12, left: -16, bottom: 4 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: "#475569", fontWeight: 700 }}
              axisLine={{ stroke: "#cbd5e1" }}
              tickLine={false}
            />
            <YAxis
              domain={[(min: number) => Math.floor(Math.min(min, RECOVERY_THRESHOLD_C) - 1), (max: number) => Math.ceil(Math.max(max, RECOVERY_THRESHOLD_C) + 1)]}
              tick={{ fontSize: 11, fill: "#475569", fontWeight: 700 }}
              axisLine={false}
              tickLine={false}
              unit="°"
            />
            <Tooltip
              contentStyle={{
                fontSize: 12,
                borderRadius: 12,
                border: "1px solid #cbd5e1",
                boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
                fontWeight: 700,
              }}
              formatter={(v) => [`${Number(v).toFixed(1)} °C`, "Overnight Min"]}
            />
            <ReferenceLine
              y={RECOVERY_THRESHOLD_C}
              stroke="#dc2626"
              strokeDasharray="4 3"
              strokeWidth={2}
              label={{
                value: `Recovery threshold ${RECOVERY_THRESHOLD_C} °C`,
                position: "insideTopLeft",
                fontSize: 11,
                fill: "#dc2626",
                fontWeight: 800,
              }}
            />
            <Bar dataKey="min_c" radius={[6, 6, 0, 0]}>
              {chart.map((d) => (
                <Cell
                  key={d.date}
                  fill={
                    d.min_c >= 30
                      ? "var(--color-ramp-6)"
                      : d.min_c >= RECOVERY_THRESHOLD_C
                        ? "var(--color-ramp-4)"
                        : "var(--color-ramp-2)"
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-4 p-3.5 bg-flag-bg/70 border border-flag/30 rounded-xl shadow-2xs">
        <p className="text-[12px] leading-relaxed text-ink font-medium">
          Overnight minima never dropped below <strong className="text-flag font-black tnum">{Math.min(...nights.map((n) => n.min_c)).toFixed(1)} °C</strong>, reaching <strong className="text-flag font-black tnum">{worst.min_c.toFixed(1)} °C</strong> on {worst.date}. Cumulative physiological heat strain builds when human bodies cannot shed thermal load overnight.
        </p>
      </div>

      <Note>
        Data source: {weatherSource(data)}, city-average air temperature. Homes with metal or asbestos roofs hold heat longer into the night.
      </Note>
    </Panel>
  );
}


