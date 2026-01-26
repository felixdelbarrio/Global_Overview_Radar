import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "BBVA BugResolutionRadar",
  description: "Enterprise Incident Intelligence",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}