"use client";

import dynamic from "next/dynamic";
import { PageSkeleton } from "@/components/PageSkeleton";

const SentimentView = dynamic(
  () => import("@/components/SentimentView").then((mod) => mod.SentimentView),
  { ssr: false, loading: () => <PageSkeleton title="Sentimiento histórico" /> }
);

export default function SentimientoPage() {
  return <SentimentView mode="sentiment" />;
}
