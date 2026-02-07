/** Layout raiz de la aplicacion Next.js. */

import "./globals.css";
import type { ReactNode } from "react";
import Script from "next/script";
import { AuthGate } from "@/components/AuthGate";

const AUTH_ENABLED = process.env.NEXT_PUBLIC_AUTH_ENABLED === "true";

/** Metadata base para SEO y titulo de la app. */
export const metadata = {
  title: "Global Overview Radar",
  description: "Enterprise Reputation Intelligence",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

/** Envoltorio principal de HTML y body. */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="es"
      data-theme="ambient-dark"
      suppressHydrationWarning
    >
      <body>
        <Script id="theme-init" strategy="beforeInteractive">
          {`(function(){try{var t=localStorage.getItem('gor-theme');if(t==='ambient-dark'||t==='ambient-light'){document.documentElement.dataset.theme=t;}else{document.documentElement.dataset.theme='ambient-dark';}}catch(e){}})();`}
        </Script>
        {AUTH_ENABLED ? <AuthGate>{children}</AuthGate> : children}
      </body>
    </html>
  );
}
