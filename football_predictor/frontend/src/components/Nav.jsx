import { NavLink } from 'react-router-dom'
import './Nav.css'

export default function Nav() {
  return (
    <nav className="nav">
      <div className="container nav-inner">
        <NavLink to="/" className="nav-logo">
          <span className="logo-icon">⚽</span>
          <span className="logo-text">Match<span className="logo-accent">Mind</span></span>
        </NavLink>
        <div className="nav-links">
          <NavLink to="/"             end className={navCls}>Dashboard</NavLink>
          <NavLink to="/predictions"      className={navCls}>Predictions</NavLink>
          <NavLink to="/matches"          className={navCls}>Matches</NavLink>
          <NavLink to="/teams"            className={navCls}>Teams</NavLink>
          <NavLink to="/backtest"         className={navCls}>Back-test</NavLink>
          <NavLink to="/worldcup"         className={navCls}>
            <span style={{ color: 'var(--acid)' }}>🏆</span> World Cup
          </NavLink>
          <NavLink to="/admin"            className={navCls}>Admin</NavLink>
        </div>
      </div>
    </nav>
  )
}

const navCls = ({ isActive }) => `nav-link${isActive ? ' nav-link-active' : ''}`
