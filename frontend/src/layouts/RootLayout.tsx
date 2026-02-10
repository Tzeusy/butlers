import { Outlet } from 'react-router'
import Shell from '../components/layout/Shell'
import PageHeader from '../components/layout/PageHeader'
import CommandPalette from '../components/layout/CommandPalette'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { Toaster } from '../components/ui/sonner'
import { useKeyboardShortcuts } from '../hooks/use-keyboard-shortcuts'
import { ShortcutHints } from '../components/ui/shortcut-hints'

export default function RootLayout() {
  useKeyboardShortcuts()

  return (
    <>
      <Shell header={<PageHeader />}>
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </Shell>
      <CommandPalette />
      <ShortcutHints />
      <Toaster />
    </>
  )
}
