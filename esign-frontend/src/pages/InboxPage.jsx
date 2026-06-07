import { useEffect, useState, useMemo } from 'react'
import { getPackages } from '../services/api.js'
import UserNav from '../components/UserNav.jsx'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  Inbox, 
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
  Search, 
  Filter, 
  ArrowLeft, 
  Calendar, 
  User, 
  Mail, 
  X,
  ChevronDown,
  Download
} from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { PdfPreviewModal } from './SuccessPage.jsx'

// Simple time-ago formatter helper
function formatTimeAgo(dateString) {
  try {
    const now = new Date()
    const past = new Date(dateString)
    const diffMs = now - past
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMins / 60)
    const diffDays = Math.floor(diffHours / 24)

    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays === 1) return 'Yesterday'
    return past.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  } catch (e) {
    return 'Recently'
  }
}

export default function InboxPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const categoryParam = searchParams.get('category') || 'awaiting-me'

  const [packages, setPackages] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  const [isPreviewOpen, setIsPreviewOpen] = useState(false)
  const [selectedPreviewUrl, setSelectedPreviewUrl] = useState('')
  const [selectedPreviewTitle, setSelectedPreviewTitle] = useState('')

  // Search & Filter local states
  const [searchTerm, setSearchTerm] = useState('')
  const [sortField, setSortField] = useState('newest') // newest, oldest, activity
  const [statusFilter, setStatusFilter] = useState('all') // all, sent, viewed, completed, draft, declined
  const [roleFilter, setRoleFilter] = useState('all') // all, signer, approver, reviewer, cc

  async function loadInboxPackages() {
    setIsLoading(true)
    setError('')
    try {
      const res = await getPackages()
      setPackages(res)
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
        err?.message ||
        'Unable to synchronize inbox requests.'
      )
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadInboxPackages()
  }, [])

  // Group counters (based on unfiltered packages)
  const counts = useMemo(() => {
    const countsObj = {
      'awaiting-me': 0,
      'awaiting-others': 0,
      'in-progress': 0,
      'completed': 0,
      'drafts': 0,
      'all': packages.length
    }

    packages.forEach(pkg => {
      // 1. Drafts
      if (pkg.status === 'draft') {
        countsObj['drafts']++
      }
      // 2. Completed
      else if (pkg.status === 'completed') {
        countsObj['completed']++
      }
      // 3. In Progress (sent or viewed status)
      else if (pkg.status === 'sent' || pkg.status === 'viewed') {
        countsObj['in-progress']++
        
        // Check if there is an active participant currently
        if (pkg.active_participant) {
          countsObj['awaiting-me']++
        }
        
        // Awaiting others: in sequential flows, any sent/viewed workflow is waiting for a participant
        countsObj['awaiting-others']++
      }
    })

    return countsObj
  }, [packages])

  // Filter & Sort requests
  const processedPackages = useMemo(() => {
    // 1. Filter by category parameter
    let list = packages.filter(pkg => {
      if (categoryParam === 'drafts') return pkg.status === 'draft'
      if (categoryParam === 'completed') return pkg.status === 'completed'
      if (categoryParam === 'in-progress') return pkg.status === 'sent' || pkg.status === 'viewed'
      if (categoryParam === 'awaiting-me') return (pkg.status === 'sent' || pkg.status === 'viewed') && pkg.active_participant !== null
      if (categoryParam === 'awaiting-others') return pkg.status === 'sent' || pkg.status === 'viewed'
      return true // 'all'
    })

    // 2. Search query filter
    if (searchTerm.trim()) {
      const query = searchTerm.toLowerCase().trim()
      list = list.filter(pkg => {
        const matchesTitle = pkg.title?.toLowerCase().includes(query)
        const matchesParticipant = pkg.participants?.some(p => 
          p.name?.toLowerCase().includes(query) || p.email?.toLowerCase().includes(query)
        )
        return matchesTitle || matchesParticipant
      })
    }

    // 3. Filter by individual Status Select
    if (statusFilter !== 'all') {
      list = list.filter(pkg => pkg.status === statusFilter)
    }

    // 4. Filter by role in workflow
    if (roleFilter !== 'all') {
      list = list.filter(pkg => pkg.participants?.some(p => p.role === roleFilter))
    }

    // 5. Apply sorting
    list.sort((a, b) => {
      if (sortField === 'newest') {
        return new Date(b.created_at) - new Date(a.created_at)
      }
      if (sortField === 'oldest') {
        return new Date(a.created_at) - new Date(b.created_at)
      }
      if (sortField === 'activity') {
        return new Date(b.last_activity) - new Date(a.last_activity)
      }
      return 0
    })

    return list
  }, [packages, categoryParam, searchTerm, statusFilter, roleFilter, sortField])

  const currentCategoryLabel = useMemo(() => {
    if (categoryParam === 'awaiting-me') return 'Awaiting Me'
    if (categoryParam === 'awaiting-others') return 'Awaiting Others'
    if (categoryParam === 'in-progress') return 'In Progress'
    if (categoryParam === 'completed') return 'Completed'
    if (categoryParam === 'drafts') return 'Drafts'
    return 'All Requests'
  }, [categoryParam])

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:py-16 relative z-10 space-y-8 font-sans">
      
      {/* Return link */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-400 hover:text-cyan-400 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Dashboard
        </Link>
      </motion.div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6 border-b border-white/5 pb-6">
        <div className="space-y-2">
          <h1 className="text-3xl font-light tracking-tight text-white sm:text-5xl neon-text-glow flex items-center gap-3">
            <Inbox className="h-10 w-10 text-cyan-400 stroke-[1.5]" />
            Inbox Command Center
          </h1>
          <p className="text-sm font-medium text-zinc-400">
            Monitor pending approvals, track routing status, check audit logs, and manage drafts from your work queue.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
          <UserNav />
          <Link
            to="/create-request"
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black px-6 py-3.5 text-xs font-bold transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] hover:shadow-[0_0_30px_rgba(34,211,238,0.4)] uppercase tracking-wider cursor-pointer"
          >
            <Plus className="h-4 w-4 stroke-[3]" />
            Create New Request
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8 items-start">
        
        {/* Category Sidebar Navigation */}
        <div className="glass-panel rounded-3xl p-4 border border-white/5 bg-[#0B1220] space-y-1 lg:col-span-1 shadow-2xl">
          <span className="block text-[10px] font-bold uppercase tracking-wider text-zinc-500 px-3 pb-3 border-b border-white/5 mb-2">
            Work Queues
          </span>
          {[
            { id: 'awaiting-me', label: 'Awaiting Me', desc: 'Needs your immediate action' },
            { id: 'awaiting-others', label: 'Awaiting Others', desc: 'Waiting for subsequent roles' },
            { id: 'in-progress', label: 'In Progress', desc: 'Actively routing payloads' },
            { id: 'completed', label: 'Completed', desc: 'Successfully executed & archived' },
            { id: 'drafts', label: 'Drafts', desc: 'Awaiting configuration presets' },
            { id: 'all', label: 'All Requests', desc: 'Complete historical logs view' }
          ].map(cat => {
            const isActive = categoryParam === cat.id
            const count = counts[cat.id]
            
            return (
              <button
                key={cat.id}
                type="button"
                onClick={() => setSearchParams({ category: cat.id })}
                className={`w-full flex items-center justify-between px-3 py-3 rounded-2xl text-left transition-all duration-200 cursor-pointer border ${
                  isActive 
                    ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400 shadow-[0_0_15px_rgba(34,211,238,0.05)]' 
                    : 'text-zinc-400 hover:text-white hover:bg-white/[0.02] border-transparent'
                }`}
              >
                <div className="space-y-0.5">
                  <span className="text-xs font-bold uppercase tracking-wider block">{cat.label}</span>
                  <span className="text-[10px] text-zinc-600 block group-hover:text-zinc-500 truncate max-w-[160px]">{cat.desc}</span>
                </div>
                
                <span className={`h-5 min-w-5 px-1.5 flex items-center justify-center rounded-full text-[10px] font-bold font-mono ${
                  isActive
                    ? 'bg-cyan-500 text-black shadow-[0_0_8px_rgba(34,211,238,0.3)]'
                    : count > 0 
                      ? 'bg-white/10 text-zinc-300' 
                      : 'bg-white/5 text-zinc-600'
                }`}>
                  {count}
                </span>
              </button>
            )
          })}
        </div>

        {/* Inbox Grid Contents (3/4 width) */}
        <div className="lg:col-span-3 space-y-6">
          
          {/* Search, Filter, Sort Controls panel */}
          <div className="glass-panel rounded-3xl p-5 border border-white/5 bg-[#0B1220] flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-xl">
            
            {/* Search Box */}
            <div className="relative flex-1 max-w-md w-full">
              <Search className="absolute left-3.5 h-4 w-4 text-zinc-500 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search by package name, signer, approver name or email..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full rounded-2xl border border-white/10 bg-black/40 px-4 py-3.5 pl-11 text-xs text-zinc-200 placeholder:text-zinc-600 outline-none transition-all focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/20"
              />
              {searchTerm && (
                <button
                  type="button"
                  onClick={() => setSearchTerm('')}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-white"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>

            {/* Filters Area */}
            <div className="flex flex-wrap items-center gap-3">
              
              {/* Status Selector */}
              <div className="flex flex-col gap-1">
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="rounded-xl border border-white/10 bg-black/60 px-3 py-2 text-xs text-zinc-300 outline-none cursor-pointer focus:border-cyan-500/40 transition-all"
                >
                  <option value="all" className="bg-[#0B1220]">All Statuses</option>
                  <option value="draft" className="bg-[#0B1220]">Draft</option>
                  <option value="sent" className="bg-[#0B1220]">Sent</option>
                  <option value="viewed" className="bg-[#0B1220]">Viewed</option>
                  <option value="completed" className="bg-[#0B1220]">Completed</option>
                  <option value="declined" className="bg-[#0B1220]">Declined</option>
                </select>
              </div>

              {/* Role Selector */}
              <div className="flex flex-col gap-1">
                <select
                  value={roleFilter}
                  onChange={(e) => setRoleFilter(e.target.value)}
                  className="rounded-xl border border-white/10 bg-black/60 px-3 py-2 text-xs text-zinc-300 outline-none cursor-pointer focus:border-cyan-500/40 transition-all"
                >
                  <option value="all" className="bg-[#0B1220]">All Roles</option>
                  <option value="signer" className="bg-[#0B1220]">Signers Only</option>
                  <option value="approver" className="bg-[#0B1220]">Approvers Only</option>
                  <option value="reviewer" className="bg-[#0B1220]">Reviewers Only</option>
                  <option value="cc" className="bg-[#0B1220]">CC Only</option>
                </select>
              </div>

              {/* Sort selector */}
              <div className="flex flex-col gap-1">
                <select
                  value={sortField}
                  onChange={(e) => setSortField(e.target.value)}
                  className="rounded-xl border border-white/10 bg-black/60 px-3 py-2 text-xs text-zinc-300 outline-none cursor-pointer focus:border-cyan-500/40 transition-all"
                >
                  <option value="newest" className="bg-[#0B1220]">Newest Created</option>
                  <option value="oldest" className="bg-[#0B1220]">Oldest Created</option>
                  <option value="activity" className="bg-[#0B1220]">Last Active</option>
                </select>
              </div>

            </div>

          </div>

          {/* Table Area */}
          <AnimatePresence mode="wait">
            {isLoading ? (
              <motion.div 
                key="loading"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex flex-col items-center justify-center py-32 text-cyan-500 bg-white/[0.005] border border-white/5 rounded-3xl"
              >
                <RefreshCw className="h-8 w-8 animate-spin" />
                <span className="mt-4 text-xs font-semibold tracking-widest uppercase animate-pulse">Syncing Work Queue...</span>
              </motion.div>
            ) : error ? (
              <motion.div
                key="error"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                className="flex items-center gap-4 rounded-3xl border border-red-500/30 bg-red-500/10 px-6 py-5 text-sm text-red-200 backdrop-blur-md"
              >
                <AlertCircle className="h-6 w-6 text-red-400 shrink-0" />
                <div>
                  <h3 className="font-semibold text-lg">Failed to Synchronize Inbox</h3>
                  <p className="text-zinc-400 mt-1">{error}</p>
                  <button onClick={loadInboxPackages} className="mt-3 text-xs font-semibold uppercase tracking-wider text-red-400 hover:text-red-300">Retry Fetch</button>
                </div>
              </motion.div>
            ) : processedPackages.length > 0 ? (
              <motion.div 
                key="content"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="glass-panel rounded-3xl overflow-hidden border border-white/5 shadow-2xl"
              >
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-sm">
                    <thead>
                      <tr className="border-b border-white/5 text-zinc-500 uppercase text-[9px] font-bold tracking-wider bg-white/[0.002]">
                        <th className="px-6 py-4 min-w-[200px]">Package Name</th>
                        <th className="px-6 py-4">Status</th>
                        <th className="px-6 py-4 text-center">Progress</th>
                        <th className="px-6 py-4">Active Participant</th>
                        <th className="px-6 py-4">Created</th>
                        <th className="px-6 py-4">Last Activity</th>
                        <th className="px-6 py-4 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {processedPackages.map(pkg => {
                        const isCompleted = pkg.status === 'completed'
                        const isSent = pkg.status === 'sent'
                        const isViewed = pkg.status === 'viewed'
                        const isDraft = pkg.status === 'draft'
                        const isDeclined = pkg.status === 'declined'

                        return (
                          <tr 
                            key={pkg.id} 
                            onClick={() => navigate(`/packages/${pkg.id}`)}
                            className="hover:bg-white/[0.015] transition-colors group/row cursor-pointer"
                          >
                            {/* Title */}
                            <td className="px-6 py-4 font-semibold text-white max-w-[200px] align-middle">
                              <div className="flex items-center gap-2">
                                <FileText className="h-4 w-4 text-zinc-500 group-hover:text-cyan-400 transition-colors shrink-0" />
                                <span className="truncate group-hover:text-cyan-400 transition-colors" title={pkg.title}>
                                  {pkg.title}
                                </span>
                              </div>
                            </td>

                            {/* Status */}
                            <td className="px-6 py-4 align-middle">
                              <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold border capitalize ${
                                isCompleted ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400' :
                                isSent ? 'border-violet-500/20 bg-violet-500/10 text-violet-400' :
                                isViewed ? 'border-cyan-500/20 bg-cyan-500/10 text-cyan-400' :
                                isDraft ? 'border-zinc-500/20 bg-zinc-500/10 text-zinc-400' :
                                isDeclined ? 'border-red-500/20 bg-red-500/10 text-red-400' :
                                'border-amber-500/20 bg-amber-500/10 text-amber-400'
                              }`}>
                                {(isSent || isViewed || isCompleted) && (
                                  <span className={`h-1.5 w-1.5 rounded-full ${
                                    isCompleted ? 'bg-emerald-400' :
                                    isSent ? 'bg-violet-400 animate-pulse' : 'bg-cyan-400 animate-pulse'
                                  }`} />
                                )}
                                {pkg.status}
                              </span>
                            </td>

                            {/* Current Step Progress */}
                            <td className="px-6 py-4 text-center font-mono font-bold text-zinc-300 align-middle">
                              <span className="inline-flex items-center justify-center bg-black/40 px-2.5 py-1 rounded-lg border border-white/5 text-[10px]">
                                Step {pkg.current_step} of {pkg.total_steps}
                              </span>
                            </td>

                            {/* Active Participant */}
                            <td className="px-6 py-4 text-xs font-medium text-zinc-400 align-middle">
                              {pkg.active_participant ? (
                                <div className="space-y-0.5">
                                  <span className="text-zinc-200 font-bold block">{pkg.active_participant.name}</span>
                                  <span className={`inline-flex items-center px-1 rounded text-[8px] font-bold uppercase tracking-wider border ${
                                    pkg.active_participant.role === 'signer' ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20' :
                                    pkg.active_participant.role === 'approver' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                                    pkg.active_participant.role === 'reviewer' ? 'bg-violet-500/10 text-violet-400 border-violet-500/20' :
                                    'bg-zinc-800 text-zinc-400 border-white/5'
                                  }`}>
                                    {pkg.active_participant.role}
                                  </span>
                                </div>
                              ) : (
                                <span className="text-zinc-600 font-mono text-[10px]">--</span>
                              )}
                            </td>

                            {/* Created Date */}
                            <td className="px-6 py-4 text-zinc-500 text-xs font-semibold align-middle">
                              <div className="flex items-center gap-1.5">
                                <Calendar className="h-3 w-3 text-zinc-600" />
                                {new Date(pkg.created_at).toLocaleDateString(undefined, {
                                  month: 'short',
                                  day: 'numeric',
                                  year: 'numeric'
                                })}
                              </div>
                            </td>

                            {/* Last Activity */}
                            <td className="px-6 py-4 text-zinc-400 text-xs font-medium align-middle">
                              <div className="flex items-center gap-1.5">
                                <Clock className="h-3.5 w-3.5 text-zinc-500" />
                                <span>{formatTimeAgo(pkg.last_activity)}</span>
                              </div>
                            </td>

                            {/* Action Links */}
                            <td className="px-6 py-4 text-right align-middle" onClick={e => e.stopPropagation()}>
                              <div className="flex items-center justify-end gap-1.5">
                                {pkg.status === 'completed' && pkg.signed_document ? (
                                  <>
                                    <button 
                                      onClick={() => {
                                        setSelectedPreviewUrl(pkg.signed_document.preview_url)
                                        setSelectedPreviewTitle(pkg.title)
                                        setIsPreviewOpen(true)
                                      }}
                                      className="inline-flex items-center gap-1 rounded-lg bg-emerald-500/10 hover:bg-emerald-500 hover:text-black border border-emerald-500/20 px-2.5 py-1.5 text-[11px] font-bold text-emerald-400 transition-all cursor-pointer shrink-0"
                                      title="Preview signed document"
                                    >
                                      <Eye className="h-3.5 w-3.5" />
                                      View
                                    </button>
                                    <a 
                                      href={pkg.signed_document.download_url}
                                      download
                                      className="inline-flex items-center gap-1 rounded-lg bg-zinc-800 hover:bg-zinc-700 border border-white/5 px-2.5 py-1.5 text-[11px] font-bold text-zinc-300 transition-all cursor-pointer shrink-0"
                                      title="Download signed document"
                                    >
                                      <Download className="h-3.5 w-3.5" />
                                      Download
                                    </a>
                                  </>
                                ) : null}
                                <Link 
                                  to={`/packages/${pkg.id}`}
                                  className="inline-flex items-center gap-1 rounded-lg bg-zinc-800 hover:bg-cyan-500 hover:text-black border border-white/5 hover:border-cyan-400 px-3 py-1.5 text-[11px] font-bold text-zinc-300 transition-all cursor-pointer shrink-0"
                                >
                                  Details
                                  <ArrowUpRight className="h-3 w-3" />
                                </Link>
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </motion.div>
            ) : (
              /* Empty State */
              <motion.div
                key="empty"
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                className="flex flex-col items-center justify-center py-24 text-center space-y-4 bg-white/[0.005] border border-dashed border-white/10 rounded-[2rem] px-4 shadow-xl"
              >
                <div className="rounded-full bg-cyan-500/10 border border-cyan-500/20 p-5 text-cyan-400 animate-pulse">
                  <Inbox className="h-10 w-10" />
                </div>
                <div className="space-y-1 max-w-sm">
                  <h3 className="text-base font-semibold text-white">
                    {searchTerm ? 'No Search Results Match' : `No ${currentCategoryLabel} Requests Found`}
                  </h3>
                  <p className="text-xs text-zinc-500">
                    {searchTerm 
                      ? 'Adjust your query, names, or email parameters and try searching again.' 
                      : categoryParam === 'completed' 
                        ? 'No completed packages yet. Workflows will archive here once fully executed.' 
                        : `Your queue is currently clear of any ${currentCategoryLabel.toLowerCase()} envelopes.`}
                  </p>
                </div>
                
                <div className="flex items-center gap-3 pt-2">
                  <Link 
                    to="/create-request"
                    className="inline-flex items-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black px-5 py-3 text-xs font-bold transition-all shadow-[0_0_15px_rgba(34,211,238,0.2)]"
                  >
                    <Plus className="h-3.5 w-3.5 stroke-[3]" />
                    Create Request
                  </Link>
                  <Link 
                    to="/"
                    className="inline-flex items-center gap-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 border border-white/10 text-zinc-300 px-5 py-3 text-xs font-bold transition-all"
                  >
                    Dashboard Home
                  </Link>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

        </div>

      </div>

      <PdfPreviewModal
        isOpen={isPreviewOpen}
        onClose={() => setIsPreviewOpen(false)}
        previewUrl={selectedPreviewUrl}
        title={selectedPreviewTitle}
      />
    </div>
  )
}
