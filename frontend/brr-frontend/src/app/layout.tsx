/** Layout raiz de la aplicacion Next.js. */

import "./globals.css";
import type { ReactNode } from "react";
import { Space_Grotesk, Source_Sans_3 } from "next/font/google";

const display = Space_Grotesk({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-display",
  weight: ["400", "500", "600", "700"],
});

const body = Source_Sans_3({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-body",
  weight: ["400", "500", "600"],
});

/** Metadata base para SEO y titulo de la app. */
export const metadata = {
  title: "BBVA Empresas – Global Overview Radar",
  description: "Enterprise Incident Intelligence",
};

/** Envoltorio principal de HTML y body. */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es" className={`${body.variable} ${display.variable}`}>
      <body>{children}</body>
    </html>
  );
}
