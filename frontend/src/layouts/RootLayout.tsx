import { Outlet } from 'react-router'
import Shell from '../components/layout/Shell'

export default function RootLayout() {
  return (
    <Shell
      sidebar={<div className="p-4 text-sm text-muted-foreground">Sidebar</div>}
      header={<div className="text-sm font-medium">Butlers Dashboard</div>}
    >
      <Outlet />
    </Shell>
  )
}
