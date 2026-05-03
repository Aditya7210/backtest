import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import LiveMarket from './pages/LiveMarket';
import BacktestPage from './pages/Backtest';
import StrategiesPage from './pages/Strategies';
import SettingsPage from './pages/Settings';
import MarketPulsePage from './pages/MarketPulse';
import ZerodhaAuthPage from './pages/ZerodhaAuth';
import { APP_ROUTES } from './config/routes';
import ErrorBoundary from './components/ErrorBoundary';

function TopNav() {
  const primaryItems = APP_ROUTES.filter((route) => route.inTopNav);

  return (
    <header className="app-topbar">
      <div className="app-topbar-inner">
        <div className="app-nav-logo-zone" aria-hidden="true">
          <span className="app-nav-logo-circle">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M4 15.5 9 10l3 2.7L17.8 7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M16 7h3v3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        </div>

        <nav className="app-topnav-links" aria-label="Primary Navigation">
          {primaryItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              className={({ isActive }) => `app-topnav-link ${isActive ? 'active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="app-nav-user-zone">
          <span className="app-nav-user-dot" />
          <span className="app-nav-user-text">trader@local</span>
        </div>
      </div>
    </header>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <TopNav />
        <main className="app-stage">
          <div className="app-stage-canvas">
            <Routes>
              <Route path="/" element={<ZerodhaAuthPage />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/market-pulse" element={<MarketPulsePage />} />
              <Route path="/live" element={<LiveMarket />} />
              <Route
                path="/backtest"
                element={(
                  <ErrorBoundary title="Backtest Page Crashed">
                    <BacktestPage />
                  </ErrorBoundary>
                )}
              />
              <Route path="/strategies" element={<StrategiesPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </div>
        </main>
      </div>
    </BrowserRouter>
  );
}
