import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import UploadPage from './pages/UploadPage.jsx'
import SignPage from './pages/SignPage.jsx'
import SuccessPage from './pages/SuccessPage.jsx'

export default function App() {
  return (
    <BrowserRouter>
      <div className="relative min-h-dvh bg-[#050505] text-zinc-100 overflow-hidden font-sans selection:bg-cyan-500/30">
        {/* Ambient background glows */}
        <div className="pointer-events-none absolute -left-[20%] -top-[20%] h-[70vw] w-[70vw] rounded-full bg-cyan-900/10 blur-[120px]" />
        <div className="pointer-events-none absolute -right-[20%] top-[40%] h-[60vw] w-[60vw] rounded-full bg-violet-900/10 blur-[120px]" />
        
        <div className="relative z-10 min-h-dvh">
          <Routes>
            <Route path="/" element={<UploadPage />} />
            <Route path="/sign/:token" element={<SignPage />} />
            <Route path="/success" element={<SuccessPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  )
}
