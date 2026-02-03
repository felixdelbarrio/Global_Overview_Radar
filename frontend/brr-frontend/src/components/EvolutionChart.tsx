"use client";

/**
 * Chart de evolucion temporal basado en Recharts.
 *
 * Se renderiza solo en cliente para evitar issues en SSR.
 */

import type { EvolutionPoint } from "@/lib/types";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export function EvolutionChart({ data }: { data: EvolutionPoint[] }) {
  /** Renderiza el grafico con los datos recibidos. */
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data}>
        <defs>
          <linearGradient id="evolutionOpen" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#004481" stopOpacity={0.28} />
            <stop offset="100%" stopColor="#004481" stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="evolutionNew" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#2dcccd" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#2dcccd" stopOpacity={0.03} />
          </linearGradient>
          <linearGradient id="evolutionClosed" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#99a4b3" stopOpacity={0.25} />
            <stop offset="100%" stopColor="#99a4b3" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis
          dataKey="date"
          tickFormatter={(d: string) => d.slice(5)}
          fontSize={11}
        />
        <YAxis fontSize={11} />
        <Tooltip
          contentStyle={{
            borderRadius: 16,
            border: "1px solid var(--border)",
            boxShadow: "var(--shadow-tooltip)",
          }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Area
          type="monotone"
          dataKey="open"
          name="Abiertas"
          fill="url(#evolutionOpen)"
          stroke="#004481"
          strokeWidth={2}
        />
        <Area
          type="monotone"
          dataKey="new"
          name="Nuevas"
          fill="url(#evolutionNew)"
          stroke="#2dcccd"
          strokeWidth={2}
        />
        <Area
          type="monotone"
          dataKey="closed"
          name="Cerradas"
          fill="url(#evolutionClosed)"
          stroke="#99a4b3"
          strokeWidth={2}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
