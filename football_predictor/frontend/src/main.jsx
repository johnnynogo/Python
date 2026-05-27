import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import Nav         from './components/Nav'
import Dashboard   from './pages/Dashboard'
import Predictions from './pages/Predictions'
import Matches     from './pages/Matches'
import MatchDetail from './pages/MatchDetail'
import Teams       from './pages/Teams'
import Backtest    from './pages/Backtest'
import WorldCup    from './pages/WorldCup'
import Admin       from './pages/Admin'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <Nav />
      <Routes>
        <Route path="/"            element={<Dashboard />} />
        <Route path="/predictions" element={<Predictions />} />
        <Route path="/matches"     element={<Matches />} />
        <Route path="/matches/:id" element={<MatchDetail />} />
        <Route path="/teams"       element={<Teams />} />
        <Route path="/backtest"    element={<Backtest />} />
        <Route path="/worldcup"    element={<WorldCup />} />
        <Route path="/admin"       element={<Admin />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
)
