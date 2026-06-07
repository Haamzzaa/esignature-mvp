import { useEffect, useState } from 'react'
import { getDashboardData } from '../services/api.js'
import UserNav from '../components/UserNav.jsx'

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
  ChevronRight,
  Inbox,
  Layers,
  TrendingUp,
  Sparkles,
  FileUp,
  Users,
  Shield,
  XCircle,
  FileSpreadsheet
} from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

export default function WorkspaceHome() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  async function loadWorkspaceData() {
    setIsLoading(true)
    setError('')
    try {
      const res = await getDashboardData()
      setData(res)
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
        err?.message ||
        'Unable to synchronize workspace dashboard.'
      )
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadWorkspaceData()
  }, [])

  // Derived metrics calculations
  const pendingRequests = (data?.stats?.sent ?? 0) + (data?.stats?.viewed ?? 0)
  const recentActivityCount = data?.recent_activity?.length ?? 0

  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: { staggerChildren: 0.08 }
    }
  }

  const itemVariants = {
    hidden: { y: 15, opacity: 0 },
    show: { y: 0, opacity: 1, transition: { type: 'spring', stiffness: 100, damping: 15 } }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:py-16 relative z-10 space-y-12">
      
      {/* ── Top Action Bar ── */}
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-6 border-b border-white/5 pb-8">
        <motion.div 
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          className="space-y-2"
        >
          <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-cyan-400 backdrop-blur-md">
            <Sparkles className="h-3.5 w-3.5" />
            Enterprise Workflow Hub
          </div>
          <h1 className="text-3xl font-light tracking-tight text-white sm:text-5xl neon-text-glow">
            E-Sign Workspace
          </h1>
          <p className="text-sm font-medium text-zinc-400 sm:text-base">
            Manage document workflows, approvals, signatures, and package activity from a centralized workspace.
          </p>
        </motion.div>

        {/* Action Controls */}
        <motion.div 
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-wrap items-center gap-3 w-full lg:w-auto"
        >
          <UserNav />

          {/* Secondary Actions (Comming Soon) */}
          {/* Templates Library Link */}
          <Link
            to="/templates"
            className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.02] hover:bg-cyan-500/10 hover:border-cyan-500/30 px-4 py-3 text-xs font-bold text-zinc-300 hover:text-cyan-400 transition-all cursor-pointer"
          >
            <Layers className="h-3.5 w-3.5 shrink-0" />
            Templates
          </Link>

          <Link
            to="/inbox"
            className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.02] hover:bg-cyan-500/10 hover:border-cyan-500/30 px-4 py-3 text-xs font-bold text-zinc-300 hover:text-cyan-400 transition-all cursor-pointer"
          >
            <Inbox className="h-3.5 w-3.5 shrink-0" />
            Inbox
          </Link>

          <div className="relative group">
            <button 
              type="button" 
              disabled 
              className="inline-flex items-center gap-1.5 rounded-xl border border-white/5 bg-white/[0.01] px-4 py-3 text-xs font-bold text-zinc-500 cursor-not-allowed select-none transition-all"
            >
              <TrendingUp className="h-3.5 w-3.5 text-zinc-600" />
              Analytics
            </button>
            <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded bg-cyan-950 border border-cyan-500/30 px-1.5 py-0.5 text-[8px] font-bold text-cyan-400 opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
              Coming Soon
            </span>
          </div>

          {/* Primary CTA */}
          <Link
            to="/create-request"
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black px-6 py-3.5 text-xs font-bold transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] hover:shadow-[0_0_30px_rgba(34,211,238,0.45)] uppercase tracking-wider cursor-pointer ml-auto sm:ml-0"
          >
            <Plus className="h-4 w-4 stroke-[3]" />
            Create New Request
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
            className="flex flex-col items-center justify-center py-40 text-cyan-500"
          >
            <RefreshCw className="h-10 w-10 animate-spin" />
            <span className="mt-4 text-xs font-semibold tracking-widest uppercase animate-pulse">
              Synchronizing Workspace Environment…
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
              <h3 className="font-semibold text-lg">Synchronization Error</h3>
              <p className="text-zinc-400 mt-1">{error}</p>
              <button 
                onClick={loadWorkspaceData} 
                className="mt-3 text-xs font-semibold uppercase tracking-wider text-red-400 hover:text-red-300 transition-colors"
              >
                Retry Setup
              </button>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="content"
            variants={containerVariants}
            initial="hidden"
            animate="show"
            className="space-y-12"
          >
            
            {/* ── Summary Metrics Grid ── */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
              
              {/* Awaiting Me */}
              <motion.div 
                variants={itemVariants} 
                onClick={() => navigate('/inbox?category=awaiting-me')}
                className="glass-panel rounded-2xl p-5 flex flex-col justify-between min-h-[130px] relative group hover:border-cyan-500/30 hover:bg-cyan-500/5 transition-all duration-300 cursor-pointer"
              >
                <div className="flex justify-between items-start">
                  <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">Awaiting Me</span>
                  <Inbox className="h-5 w-5 text-zinc-500 group-hover:text-cyan-400 transition-colors" />
                </div>
                <div className="mt-4">
                  <span className="text-3xl font-light text-white">{data?.stats?.awaiting_me ?? 0}</span>
                  <p className="text-[9px] text-zinc-500 mt-1">Needs your action</p>
                </div>
              </motion.div>

              {/* Awaiting Others */}
              <motion.div 
                variants={itemVariants} 
                onClick={() => navigate('/inbox?category=awaiting-others')}
                className="glass-panel rounded-2xl p-5 flex flex-col justify-between min-h-[130px] relative group hover:border-violet-500/30 hover:bg-violet-500/5 transition-all duration-300 cursor-pointer"
              >
                <div className="flex justify-between items-start">
                  <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">Awaiting Others</span>
                  <Users className="h-5 w-5 text-zinc-500 group-hover:text-violet-400 transition-colors" />
                </div>
                <div className="mt-4">
                  <span className="text-3xl font-light text-white">{data?.stats?.awaiting_others ?? 0}</span>
                  <p className="text-[9px] text-zinc-500 mt-1">Pending subsequent steps</p>
                </div>
              </motion.div>

              {/* In Progress */}
              <motion.div 
                variants={itemVariants} 
                onClick={() => navigate('/inbox?category=in-progress')}
                className="glass-panel rounded-2xl p-5 flex flex-col justify-between min-h-[130px] relative group hover:border-sky-500/30 hover:bg-sky-500/5 transition-all duration-300 cursor-pointer"
              >
                <div className="flex justify-between items-start">
                  <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">In Progress</span>
                  <Clock className="h-5 w-5 text-zinc-500 group-hover:text-sky-400 transition-colors" />
                </div>
                <div className="mt-4">
                  <span className="text-3xl font-light text-white">{data?.stats?.in_progress ?? 0}</span>
                  <p className="text-[9px] text-zinc-500 mt-1">Actively routing</p>
                </div>
              </motion.div>

              {/* Completed */}
              <motion.div 
                variants={itemVariants} 
                onClick={() => navigate('/inbox?category=completed')}
                className="glass-panel rounded-2xl p-5 flex flex-col justify-between min-h-[130px] relative group hover:border-emerald-500/30 hover:bg-emerald-500/5 transition-all duration-300 cursor-pointer"
              >
                <div className="flex justify-between items-start">
                  <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">Completed</span>
                  <CheckCircle2 className="h-5 w-5 text-zinc-500 group-hover:text-emerald-400 transition-colors" />
                </div>
                <div className="mt-4">
                  <span className="text-3xl font-light text-white">{data?.stats?.completed ?? 0}</span>
                  <p className="text-[9px] text-zinc-500 mt-1">Signed & archived</p>
                </div>
              </motion.div>

              {/* Drafts */}
              <motion.div 
                variants={itemVariants} 
                onClick={() => navigate('/inbox?category=drafts')}
                className="glass-panel rounded-2xl p-5 flex flex-col justify-between min-h-[130px] relative group hover:border-zinc-500/30 hover:bg-zinc-500/5 transition-all duration-300 cursor-pointer"
              >
                <div className="flex justify-between items-start">
                  <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">Drafts</span>
                  <FileText className="h-5 w-5 text-zinc-500 group-hover:text-zinc-300 transition-colors" />
                </div>
                <div className="mt-4">
                  <span className="text-3xl font-light text-white">{data?.stats?.draft ?? 0}</span>
                  <p className="text-[9px] text-zinc-500 mt-1">Awaiting configuration</p>
                </div>
              </motion.div>

            </div>

            {/* ── Main Workspace Dashboard Layout ── */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              
              {/* Left Column: Quick Starts & Recent Requests (2/3 width) */}
              <div className="lg:col-span-2 space-y-8">
                
                {/* 1. Quick Start Section */}
                <motion.div variants={itemVariants} className="space-y-4">
                  <h2 className="text-lg font-light text-white flex items-center gap-2">
                    <Layers className="h-4 w-4 text-cyan-400" />
                    Quick Start Workflows
                  </h2>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Shortcut 1 */}
                    <div 
                      onClick={() => navigate('/create-request')}
                      className="glass-panel rounded-2xl p-5 border border-white/5 bg-white/[0.005] hover:bg-cyan-500/5 hover:border-cyan-500/30 transition-all duration-300 cursor-pointer group flex items-start gap-4 relative overflow-hidden"
                    >
                      <div className="rounded-xl p-3 bg-cyan-500/10 text-cyan-400 group-hover:bg-cyan-500 group-hover:text-black transition-colors shrink-0">
                        <Plus className="h-5 w-5 stroke-[2.5]" />
                      </div>
                      <div className="space-y-1">
                        <h4 className="text-sm font-bold text-white group-hover:text-cyan-400 transition-colors">Create New Request</h4>
                        <p className="text-xs text-zinc-500">Design sequential steps, upload payloads, and securely route copy.</p>
                      </div>
                      <ChevronRight className="h-4 w-4 text-zinc-700 group-hover:text-cyan-400 transition-colors absolute right-4 top-1/2 -translate-y-1/2" />
                    </div>

                    {/* Shortcut 2 */}
                    <div 
                      onClick={() => navigate('/create-request')}
                      className="glass-panel rounded-2xl p-5 border border-white/5 bg-white/[0.005] hover:bg-violet-500/5 hover:border-violet-500/30 transition-all duration-300 cursor-pointer group flex items-start gap-4 relative overflow-hidden"
                    >
                      <div className="rounded-xl p-3 bg-violet-500/10 text-violet-400 group-hover:bg-violet-500 group-hover:text-black transition-colors shrink-0">
                        <FileUp className="h-5 w-5 stroke-[2.5]" />
                      </div>
                      <div className="space-y-1">
                        <h4 className="text-sm font-bold text-white group-hover:text-violet-400 transition-colors">Upload Document</h4>
                        <p className="text-xs text-zinc-500">Instantly parse PDF file elements and define target coordinates.</p>
                      </div>
                      <ChevronRight className="h-4 w-4 text-zinc-700 group-hover:text-violet-400 transition-colors absolute right-4 top-1/2 -translate-y-1/2" />
                    </div>

                    {/* Shortcut 3: Use Template */}
                    <div 
                      onClick={() => navigate('/templates')}
                      className="glass-panel rounded-2xl p-5 border border-white/5 bg-white/[0.005] hover:bg-emerald-500/5 hover:border-emerald-500/30 transition-all duration-300 cursor-pointer group flex items-start gap-4 relative overflow-hidden"
                    >
                      <div className="rounded-xl p-3 bg-emerald-500/10 text-emerald-400 group-hover:bg-emerald-500 group-hover:text-black transition-colors shrink-0">
                        <Layers className="h-5 w-5 stroke-[2.5]" />
                      </div>
                      <div className="space-y-1">
                        <h4 className="text-sm font-bold text-white group-hover:text-emerald-400 transition-colors">Use Template</h4>
                        <p className="text-xs text-zinc-500">Deploy standard business workflows and prepopulate parameters instantly.</p>
                      </div>
                      <ChevronRight className="h-4 w-4 text-zinc-700 group-hover:text-emerald-400 transition-colors absolute right-4 top-1/2 -translate-y-1/2" />
                    </div>

                    {/* Shortcut 4 */}
                    <div 
                      onClick={() => navigate('/inbox')}
                      className="glass-panel rounded-2xl p-5 border border-white/5 bg-white/[0.005] hover:bg-cyan-500/5 hover:border-cyan-500/30 transition-all duration-300 cursor-pointer group flex items-start gap-4 relative overflow-hidden"
                    >
                      <div className="rounded-xl p-3 bg-cyan-500/10 text-cyan-400 group-hover:bg-cyan-500 group-hover:text-black transition-colors shrink-0">
                        <Inbox className="h-5 w-5 stroke-[2.5]" />
                      </div>
                      <div className="space-y-1">
                        <h4 className="text-sm font-bold text-white group-hover:text-cyan-400 transition-colors">View Inbox</h4>
                        <p className="text-xs text-zinc-500">Inspect outstanding incoming actions and monitor active routing steps.</p>
                      </div>
                      <ChevronRight className="h-4 w-4 text-zinc-700 group-hover:text-cyan-400 transition-colors absolute right-4 top-1/2 -translate-y-1/2" />
                    </div>
                  </div>
                </motion.div>

                {/* 2. Recent Requests Section */}
                <motion.div variants={itemVariants} className="glass-panel rounded-3xl overflow-hidden border border-white/5 shadow-2xl">
                  <div className="flex items-center justify-between border-b border-white/5 bg-white/[0.01] px-6 py-5">
                    <h2 className="text-base font-semibold tracking-wide text-white flex items-center gap-2">
                      <Folder className="h-4 w-4 text-cyan-400" />
                      Recent Requests
                    </h2>
                    <span className="text-[10px] text-zinc-500 font-mono uppercase">Transaction Monitor</span>
                  </div>

                  <div className="overflow-x-auto min-h-[280px]">
                    {data?.recent_packages?.length > 0 ? (
                      <table className="w-full text-left border-collapse text-sm">
                        <thead>
                          <tr className="border-b border-white/5 text-zinc-500 uppercase text-[9px] font-bold tracking-wider bg-white/[0.002]">
                            <th className="px-6 py-4">Package Name</th>
                            <th className="px-6 py-4">Status</th>
                            <th className="px-6 py-4 text-center">Participants</th>
                            <th className="px-6 py-4">Created Date</th>
                            <th className="px-6 py-4 text-right">Actions</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                          {data.recent_packages.map((pkg) => {
                            const isCompleted = pkg.status === 'completed';
                            const isSent = pkg.status === 'sent';
                            const isViewed = pkg.status === 'viewed';
                            const isDraft = pkg.status === 'draft';
                            const isDeclined = pkg.status === 'declined';
                            
                            return (
                              <tr 
                                key={pkg.id} 
                                onClick={() => navigate(`/packages/${pkg.id}`)}
                                className="hover:bg-white/[0.02] transition-colors group/row cursor-pointer"
                              >
                                <td className="px-6 py-4 font-medium text-white max-w-[200px] truncate">
                                  {pkg.title}
                                </td>
                                <td className="px-6 py-4">
                                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold tracking-wide uppercase ${
                                    isCompleted ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                                    isSent ? 'bg-violet-500/10 text-violet-400 border border-violet-500/20 shadow-[0_0_10px_rgba(139,92,246,0.1)]' :
                                    isViewed ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 shadow-[0_0_10px_rgba(34,211,238,0.1)]' :
                                    isDraft ? 'bg-zinc-500/10 text-zinc-400 border border-zinc-500/20' :
                                    isDeclined ? 'bg-red-500/10 text-red-400 border border-red-500/20' :
                                    'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                                  }`}>
                                    {(isSent || isViewed || isCompleted) && (
                                      <span className={`h-1.5 w-1.5 rounded-full ${
                                        isCompleted ? 'bg-emerald-400 animate-pulse' :
                                        isSent ? 'bg-violet-400 animate-pulse' : 'bg-cyan-400 animate-pulse'
                                      }`} />
                                    )}
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
                                <td className="px-6 py-4 text-right align-middle" onClick={(e) => e.stopPropagation()}>
                                  <div className="flex items-center justify-end gap-2">
                                    <Link 
                                      to={`/packages/${pkg.id}`}
                                      className="inline-flex items-center gap-1 rounded-lg bg-zinc-800 hover:bg-cyan-500 hover:text-black border border-white/5 hover:border-cyan-400 px-3 py-1.5 text-[11px] font-bold text-zinc-300 transition-all"
                                    >
                                      Open Package
                                      <ArrowUpRight className="h-3 w-3" />
                                    </Link>
                                  </div>
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    ) : (
                      /* Onboarding Empty State */
                      <div className="flex flex-col items-center justify-center py-20 px-4 text-center space-y-4">
                        <div className="rounded-full bg-cyan-500/10 border border-cyan-500/20 p-5 text-cyan-400 animate-pulse">
                          <Folder className="h-10 w-10" />
                        </div>
                        <div className="space-y-1 max-w-sm">
                          <h3 className="text-base font-semibold text-white">Welcome to E-Sign Workspace</h3>
                          <p className="text-xs text-zinc-500">Create your first document workflow, upload securely, set recipients and track signatures.</p>
                        </div>
                        <Link 
                          to="/create-request"
                          className="inline-flex items-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black px-5 py-3 text-xs font-bold transition-all shadow-[0_0_15px_rgba(34,211,238,0.2)]"
                        >
                          <Plus className="h-3.5 w-3.5 stroke-[3]" />
                          Create New Request
                        </Link>
                      </div>
                    )}
                  </div>
                </motion.div>

              </div>
              
              {/* Right Column: Workflow Insights & Recent Activity (1/3 width) */}
              <div className="space-y-8">
                
                {/* 1. Workflow Overview Section */}
                <motion.div variants={itemVariants} className="glass-panel rounded-3xl overflow-hidden border border-white/5 shadow-2xl p-6 space-y-5">
                  <h2 className="text-sm font-bold uppercase tracking-wider text-white border-b border-white/5 pb-3 flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-cyan-400" />
                    Workflow Insights
                  </h2>

                  <div className="space-y-4">
                    {/* Insight Card 1 */}
                    <div className="flex items-center justify-between bg-black/40 border border-white/5 rounded-2xl p-4">
                      <div className="space-y-0.5">
                        <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Pending Approvals</span>
                        <h4 className="text-xs font-bold text-white">Review & Approve Stages</h4>
                      </div>
                      <span className="text-2xl font-light text-cyan-400 font-mono">
                        {data?.recent_packages?.filter(p => p.status === 'viewed').length ?? 0}
                      </span>
                    </div>

                    {/* Insight Card 2 */}
                    <div className="flex items-center justify-between bg-black/40 border border-white/5 rounded-2xl p-4">
                      <div className="space-y-0.5">
                        <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Awaiting Signature</span>
                        <h4 className="text-xs font-bold text-white">Active Signing Steps</h4>
                      </div>
                      <span className="text-2xl font-light text-violet-400 font-mono">
                        {data?.recent_packages?.filter(p => p.status === 'sent').length ?? 0}
                      </span>
                    </div>

                    {/* Insight Card 3 */}
                    <div className="flex items-center justify-between bg-black/40 border border-white/5 rounded-2xl p-4">
                      <div className="space-y-0.5">
                        <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Recently Completed</span>
                        <h4 className="text-xs font-bold text-white">Fully Executed Packages</h4>
                      </div>
                      <span className="text-2xl font-light text-emerald-400 font-mono">
                        {data?.recent_packages?.filter(p => p.status === 'completed').length ?? 0}
                      </span>
                    </div>
                  </div>
                </motion.div>

                {/* 2. Recent Activity Section */}
                <motion.div 
                  variants={itemVariants}
                  className="glass-panel rounded-3xl overflow-hidden border border-white/5 shadow-2xl"
                >
                  <div className="flex items-center justify-between border-b border-white/5 bg-white/[0.01] px-6 py-5">
                    <h2 className="text-base font-semibold tracking-wide text-white flex items-center gap-2">
                      <Clock className="h-4 w-4 text-cyan-400" />
                      Recent Activity
                    </h2>
                    <span className="text-[10px] text-zinc-500 font-mono uppercase">Audit Trail</span>
                  </div>

                  <div className="p-6 overflow-y-auto max-h-[400px] custom-scrollbar">
                    {data?.recent_activity?.length > 0 ? (
                      <div className="relative pl-6 border-l border-white/10 space-y-6">
                        {data.recent_activity.map((activity, idx) => (
                          <div key={idx} className="relative group">
                            {/* Timeline dot */}
                            <div className="absolute -left-[30px] top-1 h-2 w-2 rounded-full bg-cyan-500 group-hover:bg-cyan-400 transition-colors shadow-[0_0_10px_#22d3ee] border border-black z-10" />
                            
                            <p className="text-xs font-semibold text-zinc-300 leading-relaxed">
                              {activity.event}
                            </p>
                            <span className="text-[9px] font-mono text-zinc-500 font-bold tracking-wider mt-1 block">
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
                        <Clock className="h-8 w-8 mb-2 opacity-30 animate-pulse" />
                        <p className="text-xs font-semibold">No activity logs recorded.</p>
                      </div>
                    )}
                  </div>
                </motion.div>

              </div>

            </div>

          </motion.div>
        )}
      </AnimatePresence>
      
    </div>
  )
}
