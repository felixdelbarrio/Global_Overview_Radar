"use client";

import dynamic from "next/dynamic";
import { PageSkeleton } from "@/components/PageSkeleton";

const MarketInsightsView = dynamic(
  () => import("@/components/MarketInsightsView").then((mod) => mod.MarketInsightsView),
  { ssr: false, loading: () => <PageSkeleton title="Wow Radar de mercado" /> }
);

export default function MarketsPage() {
  return <MarketInsightsView />;
}
