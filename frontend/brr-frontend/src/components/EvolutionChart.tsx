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
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          dataKey="date"
          tickFormatter={(d: string) => d.slice(5)}
          fontSize={11}
        />
        <YAxis fontSize={11} />
        <Tooltip />
        <Legend />
        <Area
          type="monotone"
          dataKey="open"
          name="Abiertas"
          fill="#004481"
          stroke="#004481"
          fillOpacity={0.15}
        />
        <Area
          type="monotone"
          dataKey="new"
          name="Nuevas"
          fill="#2dcccd"
          stroke="#2dcccd"
          fillOpacity={0.2}
        />
        <Area
          type="monotone"
          dataKey="closed"
          name="Cerradas"
          fill="#99a4b3"
          stroke="#99a4b3"
          fillOpacity={0.15}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
