import { createBrowserRouter } from 'react-router'
import RootLayout from './layouts/RootLayout.tsx'
import DashboardPage from './pages/DashboardPage.tsx'
import ButlersPage from './pages/ButlersPage.tsx'
import ButlerDetailPage from './pages/ButlerDetailPage.tsx'
import SessionsPage from './pages/SessionsPage.tsx'
import SessionDetailPage from './pages/SessionDetailPage.tsx'
import NotificationsPage from './pages/NotificationsPage.tsx'
import SettingsPage from './pages/SettingsPage.tsx'

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: '/', element: <DashboardPage /> },
      { path: '/butlers', element: <ButlersPage /> },
      { path: '/butlers/:name', element: <ButlerDetailPage /> },
      { path: '/sessions', element: <SessionsPage /> },
      { path: '/sessions/:id', element: <SessionDetailPage /> },
      { path: '/notifications', element: <NotificationsPage /> },
      { path: '/settings', element: <SettingsPage /> },
    ],
  },
])
