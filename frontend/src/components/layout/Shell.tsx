import { ReactNode } from 'react'

interface ShellProps {
  sidebar: ReactNode
  header: ReactNode
  children: ReactNode
}

export default function Shell({ sidebar, header, children }: ShellProps) {
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <aside className="hidden md:flex md:w-64 md:flex-col border-r border-border">
        {sidebar}
      </aside>

      {/* Main area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <header className="flex h-14 items-center border-b border-border px-6">
          {header}
        </header>

        {/* Content */}
        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
      </div>
    </div>
  )
}
