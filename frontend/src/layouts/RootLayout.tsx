import { Outlet } from 'react-router'
import Shell from '../components/layout/Shell'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { Toaster } from '../components/ui/sonner'

export default function RootLayout() {
  return (
    <>
      <Shell
        sidebar={<div className="p-4 text-sm text-muted-foreground">Sidebar</div>}
        header={<div className="text-sm font-medium">Butlers Dashboard</div>}
      >
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </Shell>
      <Toaster />
    </>
  )
}
