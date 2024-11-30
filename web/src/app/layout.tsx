import "./globals.css"
import { Inter } from "next/font/google"
import Providers from "./providers"

const inter = Inter({ subsets: ["latin"] })

export const metadata = {
  title: "Therapy Chatbot",
  description: "AI-powered therapy chat assistant",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <Providers>
          <main className="flex min-h-screen flex-col items-center justify-between">
            {children}
          </main>
        </Providers>
      </body>
    </html>
  )
}
