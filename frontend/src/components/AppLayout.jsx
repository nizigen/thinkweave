import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/', label: '总览' },
  { to: '/library', label: '内容库' },
  { to: '/agents', label: '工作台' },
  { to: '/history', label: '历史记录' },
]

export function AppLayout({ children }) {
  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="brand-block">
          <p className="brand-sub">AniVision</p>
          <h1>次元记录库</h1>
        </div>
        <nav className="app-nav" aria-label="主导航">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `nav-item${isActive ? ' is-active' : ''}`
              }
              end={item.to === '/'}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="app-main">
        <div className="page-container">{children}</div>
      </main>
    </div>
  )
}
