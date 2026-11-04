import { NavLink, Route, Routes } from 'react-router-dom'

import AdvancedChartPage from './pages/AdvancedChartPage'
import ComparePage from './pages/ComparePage'
import ForecastPage from './pages/ForecastPage'
import IndicatorsPage from './pages/IndicatorsPage'
import PortfolioPage from './pages/PortfolioPage'
import QualityPage from './pages/QualityPage'
import QuotePage from './pages/QuotePage'

const navItems = [
  { to: '/', label: 'Indicateurs', end: true },
  { to: '/quote', label: 'Cotation' },
  { to: '/charts', label: 'Graphiques avancés' },
  { to: '/forecast', label: 'Prévision' },
  { to: '/compare', label: 'Comparer' },
  { to: '/quality', label: 'Qualité' },
  { to: '/portfolio', label: 'Portefeuille' },
]

function App() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-800 bg-slate-900/60">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
          <span className="font-semibold tracking-tight text-slate-100">Finance Bro</span>
          <nav className="flex gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-sky-500/15 text-sky-300'
                      : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        <Routes>
          <Route path="/" element={<IndicatorsPage />} />
          <Route path="/quote" element={<QuotePage />} />
          <Route path="/charts" element={<AdvancedChartPage />} />
          <Route path="/compare" element={<ComparePage />} />
          <Route path="/quality" element={<QualityPage />} />
          <Route path="/forecast" element={<ForecastPage />} />
          <Route path="/portfolio" element={<PortfolioPage />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
