import { Outlet } from 'react-router'
import Shell from '../components/layout/Shell'
import PageHeader from '../components/layout/PageHeader'
import CommandPalette from '../components/layout/CommandPalette'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { Toaster } from '../components/ui/sonner'

export default function RootLayout() {
  return (
    <>
      <Shell header={<PageHeader />}>
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </Shell>
      <CommandPalette />
      <Toaster />
    </>
  )
}
