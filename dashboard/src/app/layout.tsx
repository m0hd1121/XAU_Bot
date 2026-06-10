import type { Metadata, Viewport } from 'next'
import './globals.css'
import { QueryProvider } from '@/contexts/QueryContext'
import { AuthProvider } from '@/contexts/AuthContext'
import { WebSocketProvider } from '@/contexts/WebSocketContext'
import AppShell from '@/components/layout/AppShell'

export const metadata: Metadata = {
  title: {
    template: '%s | XAU Control Center',
    default: 'XAU Control Center',
  },
  description: 'Institutional trading platform control center for XAU/USD',
  robots: { index: false, follow: false },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#09090b',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
      </head>
      <body>
        <QueryProvider>
          <AuthProvider>
            <WebSocketProvider>
              <AppShell>{children}</AppShell>
            </WebSocketProvider>
          </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  )
}
