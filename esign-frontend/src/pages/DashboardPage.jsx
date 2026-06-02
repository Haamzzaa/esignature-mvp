import { useEffect, useState } from 'react'
import { getDashboardData } from '../services/api.js'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  Folder, 
  FileText, 
  Send, 
  Eye, 
  CheckCircle2, 
  RefreshCw, 
  AlertCircle, 
  ArrowUpRight, 
  Clock, 
  Plus, 
  Activity, 
  ChevronRight 
} from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

export default function DashboardPage() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  async function loadDashboard() {
    setIsLoading(true)
    setError('')
    try {
      const res = await getDashboardData()
      setData(res)
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
        err?.message ||
        'Unable to load dashboard stats.'
      )
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadDashboard()
  }, [])

  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1
      }
    }
  }

  const itemVariants = {
    hidden: { y: 20, opacity: 0 },
    show: { y: 0, opacity: 1, transition: { type: 'spring', stiffness: 100 } }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:py-16 relative z-10">
      
      {/* ── Dashboard Header ── */}
      <div className="mb-10 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6">
        <motion.div 
          initial={{ opacity: 0, x: -30 }}
          animate={{ opacity: 1, x: 0 }}
          className="space-y-2"
        >
          <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-medium uppercase tracking-widest text-cyan-400 backdrop-blur-md">
            <Activity className="h-3.5 w-3.5" />
            Consolidated Platform View
          </div>
          <h1 className="text-3xl font-light tracking-tight text-white sm:text-5xl neon-text-glow">
            E-Sign Dashboard
          </h1>
          <p className="text-sm font-medium text-zinc-400 sm:text-base">
            Track packages, participants, and real-time signing activity.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
        >
          <Link
            to="/"
            className="inline-flex items-center justify-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 text-black px-5 py-3.5 text-sm font-bold transition-all duration-300 hover:shadow-[0_0_30px_rgba(34,211,238,0.4)] uppercase tracking-widest"
          >
            <Plus className="h-4 w-4 stroke-[3]" />
            New Package
          </Link>
        </motion.div>
      </div>

      <AnimatePresence mode="wait">
        {isLoading ? (
          <motion.div 
            key="loading"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center justify-center py-32 text-cyan-500"
          >
            <RefreshCw className="h-10 w-10 animate-spin" />
            <span className="mt-4 text-sm font-medium tracking-widest uppercase animate-pulse">
              Aggregating Platform Data…
            </span>
          </motion.div>
        ) : error ? (
          <motion.div
            key="error"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="flex items-center gap-4 rounded-2xl border border-red-500/30 bg-red-500/10 px-6 py-5 text-sm text-red-200 backdrop-blur-md shadow-[0_0_30px_rgba(239,68,68,0.1)]"
            role="alert"
          >
            <AlertCircle className="h-6 w-6 text-red-400 shrink-0" />
            <div>
              <h3 className="font-semibold text-lg">Load Error</h3>
              <p className="text-zinc-400 mt-1">{error}</p>
              <button 
                onClick={loadDashboard} 
                className="mt-3 text-xs font-semibold uppercase tracking-wider text-red-400 hover:text-red-300 transition-colors"
              >
                Try Again
              </button>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="dashboard"
            variants={containerVariants}
            initial="hidden"
            animate="show"
            className="space-y-8"
          >
            
            {/* ── Stats Cards Grid ── */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              
              {/* Total Packages */}
              <motion.div variants={itemVariants} className="glass-panel rounded-2xl p-5 flex flex-col justify-between min-h-[120px] relative group hover:border-cyan-500/20 transition-all duration-300">
                <div className="flex justify-between items-start">
                  <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-semibold">Total Packages</span>
                  <Folder className="h-5 w-5 text-zinc-500 group-hover:text-cyan-400 transition-colors" />
                </div>
                <div className="mt-4">
                  <span className="text-3xl font-light text-white">{data?.stats?.total_packages ?? 0}</span>
                </div>
              </motion.div>

              {/* Draft */}
              <motion.div variants={itemVariants} className="glass-panel rounded-2xl p-5 flex flex-col justify-between min-h-[120px] relative group hover:border-zinc-500/20 transition-all duration-300">
                <div className="flex justify-between items-start">
                  <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-semibold">Draft</span>
                  <FileText className="h-5 w-5 text-zinc-600 group-hover:text-zinc-400 transition-colors" />
                </div>
                <div className="mt-4">
                  <span className="text-3xl font-light text-zinc-400">{data?.stats?.draft ?? 0}</span>
                </div>
              </motion.div>

              {/* Sent */}
              <motion.div variants={itemVariants} className="glass-panel rounded-2xl p-5 flex flex-col justify-between min-h-[120px] relative group hover:border-violet-500/20 transition-all duration-300">
                <div className="flex justify-between items-start">
                  <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-semibold">Sent</span>
                  <Send className="h-5 w-5 text-violet-500/50 group-hover:text-violet-400 transition-colors" />
                </div>
                <div className="mt-4">
                  <span className="text-3xl font-light text-violet-400">{data?.stats?.sent ?? 0}</span>
                </div>
              </motion.div>

              {/* Viewed */}
              <motion.div variants={itemVariants} className="glass-panel rounded-2xl p-5 flex flex-col justify-between min-h-[120px] relative group hover:border-cyan-500/20 transition-all duration-300">
                <div className="flex justify-between items-start">
                  <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-semibold">Viewed</span>
                  <Eye className="h-5 w-5 text-cyan-500/50 group-hover:text-cyan-400 transition-colors" />
                </div>
                <div className="mt-4">
                  <span className="text-3xl font-light text-cyan-400">{data?.stats?.viewed ?? 0}</span>
                </div>
              </motion.div>

              {/* Completed */}
              <motion.div variants={itemVariants} className="glass-panel rounded-2xl p-5 flex flex-col justify-between min-h-[120px] relative group hover:border-emerald-500/20 transition-all duration-300 col-span-2 md:col-span-1">
                <div className="flex justify-between items-start">
                  <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-semibold">Completed</span>
                  <CheckCircle2 className="h-5 w-5 text-emerald-500/50 group-hover:text-emerald-400 transition-colors" />
                </div>
                <div className="mt-4">
                  <span className="text-3xl font-light text-emerald-400">{data?.stats?.completed ?? 0}</span>
                </div>
              </motion.div>

            </div>

            {/* ── Two Columns Layout ── */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              
              {/* Left Column: Recent Packages (2 Cols span) */}
              <motion.div 
                variants={itemVariants}
                className="glass-panel rounded-3xl overflow-hidden lg:col-span-2 border border-white/5"
              >
                <div className="flex items-center justify-between border-b border-white/5 bg-white/[0.01] px-6 py-5">
                  <h2 className="text-base font-semibold tracking-wide text-white flex items-center gap-2">
                    <Folder className="h-4 w-4 text-cyan-400" />
                    Recent Packages
                  </h2>
                  <span className="text-[10px] text-zinc-500 font-mono uppercase">Latest 10 entries</span>
                </div>

                <div className="overflow-x-auto min-h-[350px]">
                  {data?.recent_packages?.length > 0 ? (
                    <table className="w-full text-left border-collapse text-sm">
                      <thead>
                        <tr className="border-b border-white/5 text-zinc-500 uppercase text-[10px] font-bold tracking-wider bg-white/[0.005]">
                          <th className="px-6 py-4">Package</th>
                          <th className="px-6 py-4">Status</th>
                          <th className="px-6 py-4 text-center">Participants</th>
                          <th className="px-6 py-4">Created</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {data.recent_packages.map((pkg) => (
                          <tr 
                            key={pkg.id} 
                            onClick={() => navigate(`/packages/${pkg.id}`)}
                            className="hover:bg-white/[0.03] transition-colors group/row cursor-pointer"
                          >
                            <td className="px-6 py-4 font-medium text-white truncate max-w-[200px]">
                              {pkg.title}
                            </td>
                            <td className="px-6 py-4">
                              <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold tracking-wide capitalize ${
                                pkg.status === 'completed' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                                pkg.status === 'sent' ? 'bg-violet-500/10 text-violet-400 border border-violet-500/20' :
                                pkg.status === 'viewed' ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' :
                                pkg.status === 'draft' ? 'bg-zinc-500/10 text-zinc-400 border border-zinc-500/20' :
                                'bg-red-500/10 text-red-400 border border-red-500/20'
                              }`}>
                                {pkg.status}
                              </span>
                            </td>
                            <td className="px-6 py-4 text-center text-zinc-300 font-mono font-bold">
                              {pkg.participants_count}
                            </td>
                            <td className="px-6 py-4 text-zinc-500 text-xs font-medium">
                              {new Date(pkg.created_at).toLocaleDateString(undefined, {
                                month: 'short',
                                day: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit'
                              })}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-20 text-zinc-600">
                      <Folder className="h-10 w-10 mb-2 opacity-30" />
                      <p className="text-sm">No packages created yet.</p>
                      <Link to="/" className="text-cyan-400 hover:text-cyan-300 text-xs font-bold uppercase mt-3 tracking-widest flex items-center gap-1">
                        Create Package <ArrowUpRight className="h-3.5 w-3.5" />
                      </Link>
                    </div>
                  )}
                </div>
              </motion.div>

              {/* Right Column: Recent Activity (1 Col span) */}
              <motion.div 
                variants={itemVariants}
                className="glass-panel rounded-3xl overflow-hidden border border-white/5"
              >
                <div className="flex items-center justify-between border-b border-white/5 bg-white/[0.01] px-6 py-5">
                  <h2 className="text-base font-semibold tracking-wide text-white flex items-center gap-2">
                    <Clock className="h-4 w-4 text-cyan-400" />
                    Recent Activity
                  </h2>
                  <span className="text-[10px] text-zinc-500 font-mono uppercase">Audit Trail</span>
                </div>

                <div className="p-6 overflow-y-auto max-h-[450px] custom-scrollbar">
                  {data?.recent_activity?.length > 0 ? (
                    <div className="relative pl-6 border-l border-white/10 space-y-8">
                      {data.recent_activity.map((activity, idx) => (
                        <div key={idx} className="relative group">
                          {/* Timeline dot */}
                          <div className="absolute -left-[30px] top-1 h-2 w-2 rounded-full bg-cyan-500 group-hover:bg-cyan-400 transition-colors shadow-[0_0_10px_#22d3ee] border border-black z-10" />
                          
                          <p className="text-sm font-medium text-zinc-200">
                            {activity.event}
                          </p>
                          <span className="text-[10px] font-mono text-zinc-500 font-bold tracking-wider mt-1 block">
                            {new Date(activity.timestamp).toLocaleDateString(undefined, {
                              month: 'short',
                              day: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                              second: '2-digit'
                            })}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-20 text-zinc-600">
                      <Clock className="h-10 w-10 mb-2 opacity-30" />
                      <p className="text-sm">No activity logs recorded.</p>
                    </div>
                  )}
                </div>
              </motion.div>

            </div>

          </motion.div>
        )}
      </AnimatePresence>
      
    </div>
  )
}
