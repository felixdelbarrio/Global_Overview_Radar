"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Formatter, ValueType } from "recharts/types/component/DefaultTooltipContent";

export function SentimentChart({
  data,
  principalLabel,
  actorLabel,
}: {
  data: { date: string; principal: number | null; actor: number | null }[];
  principalLabel: string;
  actorLabel: string;
}) {
  const tooltipFormatter: Formatter<ValueType, string | number> = (value) => {
    if (typeof value === "number") {
      return value.toFixed(2);
    }
    return value ?? "";
  };

  if (!data.length) {
    return (
      <div className="h-full grid place-items-center text-sm text-[color:var(--text-45)]">
        No hay datos para el periodo seleccionado.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} fontSize={11} />
        <YAxis domain={["auto", "auto"]} fontSize={11} tickFormatter={(v: number) => v.toFixed(2)} />
        <ReferenceLine y={0} stroke="var(--chart-reference)" strokeDasharray="3 3" />
        <Tooltip
          formatter={tooltipFormatter}
          labelFormatter={(label) => `Fecha ${String(label ?? "")}`}
          contentStyle={{
            borderRadius: 16,
            border: "1px solid var(--border)",
            boxShadow: "var(--shadow-tooltip)",
          }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line
          type="monotone"
          dataKey="principal"
          name={principalLabel}
          stroke="#004481"
          strokeWidth={2}
          dot={false}
          connectNulls
        />
        <Line
          type="monotone"
          dataKey="actor"
          name={actorLabel}
          stroke="#2dcccd"
          strokeWidth={2}
          dot={false}
          strokeDasharray="6 4"
          connectNulls
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function DashboardChart({
  data,
  sentimentLabel,
}: {
  data: { date: string; sentiment: number | null }[];
  sentimentLabel: string;
}) {
  const tooltipFormatter: Formatter<ValueType, string | number> = (value) => {
    if (typeof value === "number") {
      return value.toFixed(2);
    }
    return value ?? "";
  };

  if (!data.length) {
    return (
      <div className="h-full grid place-items-center text-sm text-[color:var(--text-45)]">
        No hay datos para el periodo seleccionado.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} fontSize={11} />
        <YAxis yAxisId="sentiment" fontSize={11} />
        <Tooltip
          formatter={tooltipFormatter}
          contentStyle={{
            borderRadius: 16,
            border: "1px solid var(--border)",
            boxShadow: "var(--shadow-tooltip)",
          }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line
          type="monotone"
          dataKey="sentiment"
          name={sentimentLabel}
          stroke="#004481"
          strokeWidth={2.5}
          dot={false}
          yAxisId="sentiment"
          connectNulls
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
