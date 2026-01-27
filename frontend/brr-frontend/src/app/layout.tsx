/** Layout raiz de la aplicacion Next.js. */

import "./globals.css";
import type { ReactNode } from "react";
import { Inter } from "next/font/google";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
});

/** Metadata base para SEO y titulo de la app. */
export const metadata = {
  title: "BBVA BugResolutionRadar",
  description: "Enterprise Incident Intelligence",
};

/** Envoltorio principal de HTML y body. */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es" className={inter.className}>
      <body>{children}</body>
    </html>
  );
}
