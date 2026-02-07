"use client";

import dynamic from "next/dynamic";
import { PageSkeleton } from "@/components/PageSkeleton";

const SentimentView = dynamic(
  () => import("@/components/SentimentView").then((mod) => mod.SentimentView),
  { ssr: false, loading: () => <PageSkeleton title="Dashboard reputacional" /> }
);

export default function DashboardPage() {
  return <SentimentView mode="dashboard" />;
}
