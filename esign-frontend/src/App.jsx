import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import AuthPage from './pages/AuthPage.jsx'

import UploadPage from './pages/UploadPage.jsx'
import SignPage from './pages/SignPage.jsx'
import SuccessPage from './pages/SuccessPage.jsx'
import WorkspaceHome from './pages/WorkspaceHome.jsx'
import PackageDetailPage from './pages/PackageDetailPage.jsx'
import TemplatesPage from './pages/TemplatesPage.jsx'
import InboxPage from './pages/InboxPage.jsx'
import ContractAnalysisPage from './pages/ContractAnalysisPage.jsx'
import { RefreshCw } from 'lucide-react'

function ProtectedRoute({ children }) {
  const { user, isLoading } = useAuth()
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-dvh text-cyan-500 bg-bg-primary">
        <RefreshCw className="h-10 w-10 animate-spin" />
        <span className="mt-4 text-xs font-semibold tracking-widest uppercase animate-pulse">
          Verifying Session...
        </span>
      </div>
    )
  }
  if (!user) {
    return <Navigate to="/login" replace />
  }
  return children
}

function GuestRoute({ children }) {
  const { user, isLoading } = useAuth()
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-dvh text-cyan-500 bg-bg-primary">
        <RefreshCw className="h-10 w-10 animate-spin" />
        <span className="mt-4 text-xs font-semibold tracking-widest uppercase animate-pulse">
          Verifying Session...
        </span>
      </div>
    )
  }
  if (user) {
    return <Navigate to="/" replace />
  }
  return children
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <div className="relative min-h-dvh bg-bg-primary text-text-primary overflow-hidden font-sans selection:bg-cyan-500/30">
            {/* Ambient background glows */}
            <div className="pointer-events-none absolute -left-[20%] -top-[20%] h-[70vw] w-[70vw] rounded-full bg-cyan-900/10 blur-[120px]" />
            <div className="pointer-events-none absolute -right-[20%] top-[40%] h-[60vw] w-[60vw] rounded-full bg-violet-900/10 blur-[120px]" />
            
            <div className="relative z-10 min-h-dvh">
              <Routes>
                {/* Public Routes */}
                <Route path="/sign/:token" element={<SignPage />} />
                <Route path="/success" element={<SuccessPage />} />

                {/* Guest Only Routes */}
                <Route path="/login" element={<GuestRoute><AuthPage /></GuestRoute>} />

                {/* Protected Routes */}
                <Route path="/" element={<ProtectedRoute><WorkspaceHome /></ProtectedRoute>} />
                <Route path="/create-request" element={<ProtectedRoute><UploadPage /></ProtectedRoute>} />
                <Route path="/templates" element={<ProtectedRoute><TemplatesPage /></ProtectedRoute>} />
                <Route path="/dashboard" element={<ProtectedRoute><WorkspaceHome /></ProtectedRoute>} />
                <Route path="/packages/:id" element={<ProtectedRoute><PackageDetailPage /></ProtectedRoute>} />
                <Route path="/inbox" element={<ProtectedRoute><InboxPage /></ProtectedRoute>} />
                <Route path="/analyze" element={<ProtectedRoute><ContractAnalysisPage /></ProtectedRoute>} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </div>
          </div>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  )
}
