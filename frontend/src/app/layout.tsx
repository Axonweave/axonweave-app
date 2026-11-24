import type { Metadata } from "next";
import { Geist_Mono, Inter, Space_Grotesk } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

/** Headings and big numbers. */
const grotesk = Space_Grotesk({
  variable: "--font-display",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Axonweave",
  description: "Your personal academic intelligence workspace.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // The font variables live on <html> because globals.css sets `html { font-family: var(--font-sans) }`;
    // on <body> the variable was undefined where it is read and every page fell back to a serif font.
    <html
      lang="en"
      suppressHydrationWarning
      className={`${inter.variable} ${grotesk.variable} ${geistMono.variable}`}
    >
      <head>
        {/* Inline theme script: apply class before first paint to avoid flash (D-36) */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('theme');if(t==='dark'||(!t&&window.matchMedia('(prefers-color-scheme:dark)').matches)){document.documentElement.classList.add('dark')}}catch(e){}})()`,
          }}
        />
      </head>
      <body className="antialiased">{children}</body>
    </html>
  );
}
