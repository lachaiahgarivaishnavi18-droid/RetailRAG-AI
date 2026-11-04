import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Context Cart · RetailRAG AI', description: 'Evidence-backed retail discovery' };
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
