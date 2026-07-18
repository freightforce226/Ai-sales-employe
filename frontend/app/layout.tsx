import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "../components/providers";

export const metadata: Metadata = {
  title: "FreightForce AI - AI Sales Agent for Freight Forwarding",
  description: "White label multi-tenant AI Sales Engine",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-brand-background text-brand-text">
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
