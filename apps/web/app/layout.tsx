import type { Metadata } from "next";
import "./style.css";

export const metadata: Metadata = { title: "NLGCP", description: "Engineering foundation status" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
