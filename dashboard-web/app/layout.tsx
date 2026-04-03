import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'ShopGuard Dashboard',
  description: 'Real-time shoplifting detection alerts',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: 'system-ui, sans-serif', background: '#0f1117', color: '#e2e8f0' }}>
        {children}
      </body>
    </html>
  )
}
