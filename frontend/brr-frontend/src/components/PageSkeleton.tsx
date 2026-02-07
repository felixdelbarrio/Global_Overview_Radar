"use client";

export function PageSkeleton({ title }: { title: string }) {
  return (
    <div className="min-h-screen bg-[color:var(--surface-90)] px-6 py-10 animate-pulse">
      <span className="sr-only">{title}</span>
      <div className="mx-auto w-full max-w-5xl space-y-6">
        <div className="h-5 w-44 rounded-full bg-[color:var(--surface-70)]" />
        <div className="h-10 w-80 rounded-2xl bg-[color:var(--surface-80)]" />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="h-56 rounded-[24px] bg-[color:var(--surface-80)]" />
          <div className="h-56 rounded-[24px] bg-[color:var(--surface-80)]" />
        </div>
        <div className="h-72 rounded-[28px] bg-[color:var(--surface-80)]" />
      </div>
    </div>
  );
}
