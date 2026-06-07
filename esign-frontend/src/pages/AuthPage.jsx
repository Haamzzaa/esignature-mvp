import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import { useNavigate } from 'react-router-dom'
import { KeyRound, User, Mail, Lock, Sparkles, AlertCircle } from 'lucide-react'

export default function AuthPage() {
  const [activeTab, setActiveTab] = useState('login') // login, register
  const { login, register } = useAuth()
  const navigate = useNavigate()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setIsSubmitting(true)

    try {
      if (activeTab === 'login') {
        if (!username || !password) {
          throw new Error('All fields are required.')
        }
        await login(username, password)
      } else {
        if (!username || !password || !email) {
          throw new Error('All fields are required.')
        }
        if (password !== confirmPassword) {
          throw new Error('Passwords do not match.')
        }
        await register(username, email, password)
      }
      navigate('/')
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
        err?.message ||
        'Authentication failed. Please verify inputs.'
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-md px-4 py-20 min-h-dvh flex flex-col justify-center relative z-10">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: 'easeOut' }}
      >
        <div className="glass-panel rounded-[2rem] p-8 sm:p-12 relative overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/5 via-transparent to-violet-500/5 opacity-50 pointer-events-none group-hover:opacity-100 transition-opacity duration-700" />
          
          <div className="relative z-10 mb-8 flex flex-col items-center text-center">
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-widest text-cyan-400 backdrop-blur-md mb-4">
              <Sparkles className="h-3.5 w-3.5" />
              E-Sign Security Gateway
            </div>
            <h1 className="text-3xl font-light tracking-tight text-white neon-text-glow">
              Welcome back
            </h1>
            <p className="text-sm font-medium text-zinc-400 mt-2">
              Sign in to manage your document signing workflows.
            </p>
          </div>

          {/* Login/Register Tabs */}
          <div className="relative z-10 flex items-center bg-black/40 rounded-xl p-1 border border-white/5 mb-6">
            <button
              type="button"
              onClick={() => {
                setActiveTab('login')
                setError('')
              }}
              className={`flex-1 py-2.5 rounded-lg text-xs font-bold tracking-wide uppercase transition-all duration-200 cursor-pointer ${
                activeTab === 'login'
                  ? 'bg-cyan-500 text-black shadow-[0_0_10px_rgba(34,211,238,0.2)]'
                  : 'text-zinc-400 hover:text-white'
              }`}
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveTab('register')
                setError('')
              }}
              className={`flex-1 py-2.5 rounded-lg text-xs font-bold tracking-wide uppercase transition-all duration-200 cursor-pointer ${
                activeTab === 'register'
                  ? 'bg-cyan-500 text-black shadow-[0_0_10px_rgba(34,211,238,0.2)]'
                  : 'text-zinc-400 hover:text-white'
              }`}
            >
              Register
            </button>
          </div>

          <form onSubmit={handleSubmit} className="relative z-10 space-y-4">
            {error && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-xs text-red-200 backdrop-blur-md"
              >
                <AlertCircle className="h-4 w-4 text-red-400 shrink-0" />
                <span className="font-medium">{error}</span>
              </motion.div>
            )}

            {/* Username Field */}
            <div className="space-y-1.5">
              <label className="block text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">Username</label>
              <div className="relative">
                <User className="absolute left-3.5 h-4 w-4 text-zinc-500 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="enter username"
                  className="w-full rounded-2xl border border-white/10 bg-white/[0.02] px-4 py-3.5 pl-11 text-xs text-zinc-200 placeholder:text-zinc-600 outline-none backdrop-blur-xl transition-all duration-300 focus:border-cyan-500/50 focus:bg-cyan-950/10 focus:ring-1 focus:ring-cyan-500/20"
                  required
                />
              </div>
            </div>

            {/* Register Fields */}
            {activeTab === 'register' && (
              <div className="space-y-1.5">
                <label className="block text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">Email Address</label>
                <div className="relative">
                  <Mail className="absolute left-3.5 h-4 w-4 text-zinc-500 top-1/2 -translate-y-1/2" />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="enter email address"
                    className="w-full rounded-2xl border border-white/10 bg-white/[0.02] px-4 py-3.5 pl-11 text-xs text-zinc-200 placeholder:text-zinc-600 outline-none backdrop-blur-xl transition-all duration-300 focus:border-cyan-500/50 focus:bg-cyan-950/10 focus:ring-1 focus:ring-cyan-500/20"
                    required
                  />
                </div>
              </div>
            )}

            {/* Password Field */}
            <div className="space-y-1.5">
              <label className="block text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">Password</label>
              <div className="relative">
                <Lock className="absolute left-3.5 h-4 w-4 text-zinc-500 top-1/2 -translate-y-1/2" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="enter password"
                  className="w-full rounded-2xl border border-white/10 bg-white/[0.02] px-4 py-3.5 pl-11 text-xs text-zinc-200 placeholder:text-zinc-600 outline-none backdrop-blur-xl transition-all duration-300 focus:border-cyan-500/50 focus:bg-cyan-950/10 focus:ring-1 focus:ring-cyan-500/20"
                  required
                />
              </div>
            </div>

            {/* Confirm Password Field for Register */}
            {activeTab === 'register' && (
              <div className="space-y-1.5">
                <label className="block text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">Confirm Password</label>
                <div className="relative">
                  <Lock className="absolute left-3.5 h-4 w-4 text-zinc-500 top-1/2 -translate-y-1/2" />
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="re-enter password"
                    className="w-full rounded-2xl border border-white/10 bg-white/[0.02] px-4 py-3.5 pl-11 text-xs text-zinc-200 placeholder:text-zinc-600 outline-none backdrop-blur-xl transition-all duration-300 focus:border-cyan-500/50 focus:bg-cyan-950/10 focus:ring-1 focus:ring-cyan-500/20"
                    required
                  />
                </div>
              </div>
            )}

            {/* Primary Action Button */}
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black px-6 py-3.5 text-xs font-bold transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] hover:shadow-[0_0_30px_rgba(34,211,238,0.4)] uppercase tracking-wider cursor-pointer mt-4"
            >
              <KeyRound className="h-4 w-4 shrink-0" />
              <span>{isSubmitting ? 'Authenticating...' : activeTab === 'login' ? 'Sign In' : 'Register Account'}</span>
            </button>
          </form>
        </div>
      </motion.div>
    </div>
  )
}
