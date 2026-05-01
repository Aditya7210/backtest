export interface AppRoute {
  path: string;
  label: string;
  inTopNav: boolean;
}

export const APP_ROUTES: AppRoute[] = [
  { path: '/', label: 'Zerodha Authentication', inTopNav: true },
  { path: '/dashboard', label: 'Dashboard', inTopNav: true },
  { path: '/backtest', label: 'Backtests', inTopNav: true },
  { path: '/market-pulse', label: 'Market Pulse', inTopNav: true },
  { path: '/live', label: 'Live Market Data Visual', inTopNav: true },
  { path: '/strategies', label: 'Strategies', inTopNav: false },
  { path: '/settings', label: 'Settings', inTopNav: false },
];

