import { createBrowserRouter } from 'react-router'
import RootLayout from './layouts/RootLayout.tsx'
import DashboardPage from './pages/DashboardPage.tsx'
import ButlersPage from './pages/ButlersPage.tsx'
import ButlerDetailPage from './pages/ButlerDetailPage.tsx'
import SessionsPage from './pages/SessionsPage.tsx'
import SessionDetailPage from './pages/SessionDetailPage.tsx'
import TracesPage from './pages/TracesPage.tsx'
import TraceDetailPage from './pages/TraceDetailPage.tsx'
import TimelinePage from './pages/TimelinePage.tsx'
import NotificationsPage from './pages/NotificationsPage.tsx'
import CostsPage from './pages/CostsPage.tsx'
import SettingsPage from './pages/SettingsPage.tsx'
import AuditLogPage from './pages/AuditLogPage.tsx'

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: '/', element: <DashboardPage /> },
      { path: '/butlers', element: <ButlersPage /> },
      { path: '/butlers/:name', element: <ButlerDetailPage /> },
      { path: '/sessions', element: <SessionsPage /> },
      { path: '/sessions/:id', element: <SessionDetailPage /> },
      { path: '/traces', element: <TracesPage /> },
      { path: '/traces/:traceId', element: <TraceDetailPage /> },
      { path: '/timeline', element: <TimelinePage /> },
      { path: '/notifications', element: <NotificationsPage /> },
      { path: '/audit-log', element: <AuditLogPage /> },
      { path: '/costs', element: <CostsPage /> },
      { path: '/settings', element: <SettingsPage /> },
    ],
  },
])
