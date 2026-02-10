import { NavLink } from 'react-router'

const navItems = [
  { path: '/', label: 'Overview', end: true },
  { path: '/butlers', label: 'Butlers' },
  { path: '/sessions', label: 'Sessions' },
  { path: '/notifications', label: 'Notifications' },
  { path: '/settings', label: 'Settings' },
]

export default function Sidebar() {
  return (
    <div className="flex h-full flex-col">
      {/* Brand */}
      <div className="flex h-14 items-center border-b border-border px-4">
        <span className="text-lg font-semibold">Butlers</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-3">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.end}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground hover:bg-accent/50 hover:text-accent-foreground'
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-border p-4">
        <p className="text-xs text-muted-foreground">Today's spend</p>
        <p className="text-sm font-medium">--</p>
      </div>
    </div>
  )
}
