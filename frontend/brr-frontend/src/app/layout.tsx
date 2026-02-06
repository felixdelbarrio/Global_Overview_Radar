/** Layout raiz de la aplicacion Next.js. */

import "./globals.css";
import type { ReactNode } from "react";
import { Space_Grotesk, Source_Sans_3 } from "next/font/google";
import Script from "next/script";

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
  title: "Global Overview Radar",
  description: "Market & Sentiment Intelligence Console",
};

/** Envoltorio principal de HTML y body. */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="es"
      data-theme="ambient-light"
      suppressHydrationWarning
      className={`${body.variable} ${display.variable}`}
    >
      <body>
        <Script id="theme-init" strategy="beforeInteractive">
          {`(function(){try{var t=localStorage.getItem('gor-theme');if(t==='ambient-dark'||t==='ambient-light'){document.documentElement.dataset.theme=t;}}catch(e){}})();`}
        </Script>
        {children}
      </body>
    </html>
  );
}
