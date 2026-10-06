import { useEffect, useState, useMemo } from 'react'
import { getPackages } from '../services/api.js'
import UserNav from '../components/UserNav.jsx'
import { useLocale } from '../context/LocaleContext'
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
function formatTimeAgo(dateString, t) {
  try {
    const now = new Date()
    const past = new Date(dateString)
    const diffMs = now - past
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMins / 60)
    const diffDays = Math.floor(diffHours / 24)

    if (diffMins < 1) return t ? t('common.just_now') : 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays === 1) return t ? t('common.yesterday') : 'Yesterday'
    return past.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  } catch (e) {
    return t ? t('common.recently') : 'Recently'
  }
}

export default function InboxPage() {
  const { t } = useLocale()
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
        t('inbox.sync_error_title')
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
    if (categoryParam === 'awaiting-me') return t('inbox.queue_awaiting_me')
    if (categoryParam === 'awaiting-others') return t('inbox.queue_awaiting_others')
    if (categoryParam === 'in-progress') return t('inbox.queue_in_progress')
    if (categoryParam === 'completed') return t('inbox.queue_completed')
    if (categoryParam === 'drafts') return t('inbox.queue_drafts')
    return t('inbox.queue_all')
  }, [categoryParam, t])

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:py-16 relative z-10 space-y-8 font-sans">
      
      {/* Return link */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-400 hover:text-cyan-400 transition-colors"
        >
          <ArrowLeft className="h-4 w-4 rtl:rotate-180" />
          {t('nav.back_to_dashboard')}
        </Link>
      </motion.div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6 border-b border-border-color pb-6">
        <div className="space-y-2">
          <h1 className="text-3xl font-light tracking-tight text-text-primary sm:text-5xl neon-text-glow flex items-center gap-3">
            <Inbox className="h-10 w-10 text-cyan-400 stroke-[1.5]" />
            {t('inbox.title')}
          </h1>
          <p className="text-sm font-medium text-text-secondary">
            {t('inbox.subtitle')}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
          <UserNav />
          <Link
            to="/create-request"
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black px-6 py-3.5 text-xs font-bold transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] hover:shadow-[0_0_30px_rgba(34,211,238,0.4)] uppercase tracking-wider cursor-pointer"
          >
            <Plus className="h-4 w-4 stroke-[3]" />
            {t('nav.create_request')}
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8 items-start">
        
        {/* Category Sidebar Navigation */}
        <div className="glass-panel rounded-3xl p-4 space-y-1 lg:col-span-1">
          <span className="block text-[10px] font-bold uppercase tracking-wider text-text-secondary px-3 pb-3 border-b border-border-color mb-2">
            {t('inbox.work_queues')}
          </span>
          {[
            { id: 'awaiting-me', label: t('inbox.queue_awaiting_me'), desc: t('inbox.queue_awaiting_me_desc') },
            { id: 'awaiting-others', label: t('inbox.queue_awaiting_others'), desc: t('inbox.queue_awaiting_others_desc') },
            { id: 'in-progress', label: t('inbox.queue_in_progress'), desc: t('inbox.queue_in_progress_desc') },
            { id: 'completed', label: t('inbox.queue_completed'), desc: t('inbox.queue_completed_desc') },
            { id: 'drafts', label: t('inbox.queue_drafts'), desc: t('inbox.queue_drafts_desc') },
            { id: 'all', label: t('inbox.queue_all'), desc: t('inbox.queue_all_desc') }
          ].map(cat => {
            const isActive = categoryParam === cat.id
            const count = counts[cat.id]
            
            return (
              <button
                key={cat.id}
                type="button"
                onClick={() => setSearchParams({ category: cat.id })}
                className={`w-full flex items-center justify-between px-3 py-3 rounded-2xl text-left rtl:text-right transition-all duration-200 cursor-pointer border ${
                  isActive 
                    ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400 shadow-[0_0_15px_rgba(34,211,238,0.05)]' 
                    : 'text-text-secondary hover:text-text-primary hover:bg-text-primary/5 border-transparent'
                }`}
              >
                <div className="space-y-0.5">
                  <span className="text-xs font-bold uppercase tracking-wider block">{cat.label}</span>
                  <span className="text-[10px] text-text-secondary block group-hover:text-text-primary truncate max-w-[160px]">{cat.desc}</span>
                </div>
                
                <span className={`h-5 min-w-5 px-1.5 flex items-center justify-center rounded-full text-[10px] font-bold font-mono ${
                  isActive
                    ? 'bg-cyan-500 text-black shadow-[0_0_8px_rgba(34,211,238,0.3)]'
                    : count > 0 
                      ? 'bg-text-primary/10 text-text-primary' 
                      : 'bg-text-primary/5 text-text-secondary'
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
          <div className="glass-panel rounded-3xl p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
            
            {/* Search Box */}
            <div className="relative flex-1 max-w-md w-full">
              <Search className="absolute left-3.5 rtl:left-auto rtl:right-3.5 h-4 w-4 text-text-secondary top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder={t('inbox.search_placeholder')}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full rounded-2xl border border-border-color bg-card-bg px-4 py-3.5 pl-11 rtl:pl-4 rtl:pr-11 text-xs text-text-primary placeholder:text-text-secondary/60 outline-none transition-all focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/20"
              />
              {searchTerm && (
                <button
                  type="button"
                  onClick={() => setSearchTerm('')}
                  className="absolute right-3.5 rtl:right-auto rtl:left-3.5 top-1/2 -translate-y-1/2 text-text-secondary hover:text-text-primary"
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
                  className="rounded-xl border border-border-color bg-card-bg px-3 py-2 text-xs text-text-primary outline-none cursor-pointer focus:border-cyan-500/40 transition-all"
                >
                  <option value="all">{t('inbox.filter_status_all')}</option>
                  <option value="draft">{t('inbox.filter_status_draft')}</option>
                  <option value="sent">{t('inbox.filter_status_sent')}</option>
                  <option value="viewed">{t('inbox.filter_status_viewed')}</option>
                  <option value="completed">{t('inbox.filter_status_completed')}</option>
                  <option value="declined">{t('inbox.filter_status_declined')}</option>
                </select>
              </div>

              {/* Role Selector */}
              <div className="flex flex-col gap-1">
                <select
                  value={roleFilter}
                  onChange={(e) => setRoleFilter(e.target.value)}
                  className="rounded-xl border border-border-color bg-card-bg px-3 py-2 text-xs text-text-primary outline-none cursor-pointer focus:border-cyan-500/40 transition-all"
                >
                  <option value="all">{t('inbox.filter_role_all')}</option>
                  <option value="signer">{t('inbox.filter_role_signer')}</option>
                  <option value="approver">{t('inbox.filter_role_approver')}</option>
                  <option value="reviewer">{t('inbox.filter_role_reviewer')}</option>
                  <option value="cc">{t('inbox.filter_role_cc')}</option>
                </select>
              </div>

              {/* Sort selector */}
              <div className="flex flex-col gap-1">
                <select
                  value={sortField}
                  onChange={(e) => setSortField(e.target.value)}
                  className="rounded-xl border border-border-color bg-card-bg px-3 py-2 text-xs text-text-primary outline-none cursor-pointer focus:border-cyan-500/40 transition-all"
                >
                  <option value="newest">{t('inbox.sort_newest')}</option>
                  <option value="oldest">{t('inbox.sort_oldest')}</option>
                  <option value="activity">{t('inbox.sort_activity')}</option>
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
                className="flex flex-col items-center justify-center py-32 text-cyan-500 bg-card-bg border border-border-color rounded-3xl"
              >
                <RefreshCw className="h-8 w-8 animate-spin" />
                <span className="mt-4 text-xs font-semibold tracking-widest uppercase animate-pulse">{t('inbox.syncing')}</span>
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
                  <h3 className="font-semibold text-lg text-text-primary">{t('inbox.sync_error_title')}</h3>
                  <p className="text-text-secondary mt-1">{error}</p>
                  <button onClick={loadInboxPackages} className="mt-3 text-xs font-semibold uppercase tracking-wider text-red-400 hover:text-red-300">{t('inbox.retry_fetch')}</button>
                </div>
              </motion.div>
            ) : processedPackages.length > 0 ? (
              <motion.div 
                key="content"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="glass-panel rounded-3xl overflow-hidden"
              >
                <div className="overflow-x-auto">
                  <table className="w-full text-left rtl:text-right border-collapse text-sm">
                    <thead>
                      <tr className="border-b border-border-color text-text-secondary uppercase text-[9px] font-bold tracking-wider bg-bg-primary/10">
                        <th className="px-6 py-4 min-w-[200px]">{t('inbox.col_package')}</th>
                        <th className="px-6 py-4">{t('inbox.col_status')}</th>
                        <th className="px-6 py-4 text-center">{t('inbox.col_progress')}</th>
                        <th className="px-6 py-4">{t('inbox.col_active_participant')}</th>
                        <th className="px-6 py-4">{t('inbox.col_created')}</th>
                        <th className="px-6 py-4">{t('inbox.col_last_activity')}</th>
                        <th className="px-6 py-4 text-right rtl:text-left">{t('inbox.col_actions')}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-color">
                      {processedPackages.map(pkg => {
                        const isCompleted = pkg.status === 'completed'
                        const isSent = pkg.status === 'sent'
                        const isViewed = pkg.status === 'viewed'
                        const isDraft = pkg.status === 'draft'
                        const isDeclined = pkg.status === 'declined'

                        return (
                          <tr 
                            key={pkg.id} 
                            onClick={() => navigate(isDraft ? `/create-request?draftId=${pkg.id}` : `/packages/${pkg.id}`)}
                            className="hover:bg-text-primary/[0.015] transition-colors group/row cursor-pointer"
                          >
                            {/* Title */}
                            <td className="px-6 py-4 font-semibold text-text-primary max-w-[200px] align-middle">
                              <div className="flex items-center gap-2">
                                <FileText className="h-4 w-4 text-text-secondary group-hover:text-cyan-400 transition-colors shrink-0" />
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
                            <td className="px-6 py-4 text-center font-mono font-bold text-text-primary align-middle">
                              <span className="inline-flex items-center justify-center bg-bg-primary/50 px-2.5 py-1 rounded-lg border border-border-color text-[10px]">
                                {t('inbox.step_progress', { current: pkg.current_step, total: pkg.total_steps })}
                              </span>
                            </td>

                            {/* Active Participant */}
                            <td className="px-6 py-4 text-xs font-medium text-text-secondary align-middle">
                              {pkg.active_participant ? (
                                <div className="space-y-0.5">
                                  <span className="text-text-primary font-bold block">{pkg.active_participant.name}</span>
                                  <span className={`inline-flex items-center px-1 rounded text-[8px] font-bold uppercase tracking-wider border ${
                                    pkg.active_participant.role === 'signer' ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20' :
                                    pkg.active_participant.role === 'approver' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                                    pkg.active_participant.role === 'reviewer' ? 'bg-violet-500/10 text-violet-400 border-violet-500/20' :
                                    'bg-bg-primary text-text-secondary border-border-color'
                                  }`}>
                                    {pkg.active_participant.role}
                                  </span>
                                </div>
                              ) : (
                                <span className="text-text-secondary font-mono text-[10px]">--</span>
                              )}
                            </td>

                            {/* Created Date */}
                            <td className="px-6 py-4 text-text-secondary text-xs font-semibold align-middle">
                              <div className="flex items-center gap-1.5">
                                <Calendar className="h-3 w-3 text-text-secondary" />
                                {new Date(pkg.created_at).toLocaleDateString(undefined, {
                                  month: 'short',
                                  day: 'numeric',
                                  year: 'numeric'
                                })}
                              </div>
                            </td>

                            {/* Last Activity */}
                            <td className="px-6 py-4 text-text-secondary text-xs font-medium align-middle">
                              <div className="flex items-center gap-1.5">
                                <Clock className="h-3.5 w-3.5 text-text-secondary" />
                                <span>{formatTimeAgo(pkg.last_activity, t)}</span>
                              </div>
                            </td>

                            {/* Action Links */}
                            <td className="px-6 py-4 text-right rtl:text-left align-middle" onClick={e => e.stopPropagation()}>
                              <div className="flex items-center justify-end rtl:justify-start gap-1.5">
                                {pkg.status === 'completed' && pkg.signed_document ? (
                                  <>
                                    <button 
                                      onClick={() => {
                                        setSelectedPreviewUrl(pkg.signed_document.preview_url)
                                        setSelectedPreviewTitle(pkg.title)
                                        setIsPreviewOpen(true)
                                      }}
                                      className="inline-flex items-center gap-1 rounded-lg bg-emerald-500/10 hover:bg-emerald-500 hover:text-black border border-emerald-500/20 px-2.5 py-1.5 text-[11px] font-bold text-emerald-400 transition-all cursor-pointer shrink-0"
                                      title={t('inbox.btn_view')}
                                    >
                                      <Eye className="h-3.5 w-3.5" />
                                      {t('inbox.btn_view')}
                                    </button>
                                    <a 
                                      href={pkg.signed_document.download_url}
                                      download
                                      className="inline-flex items-center gap-1 rounded-lg bg-bg-primary hover:bg-text-primary/10 border border-border-color px-2.5 py-1.5 text-[11px] font-bold text-text-primary transition-all cursor-pointer shrink-0"
                                      title={t('inbox.btn_download')}
                                    >
                                      <Download className="h-3.5 w-3.5" />
                                      {t('inbox.btn_download')}
                                    </a>
                                  </>
                                ) : null}
                                <Link 
                                  to={isDraft ? `/create-request?draftId=${pkg.id}` : `/packages/${pkg.id}`}
                                  className="inline-flex items-center gap-1 rounded-lg bg-bg-primary hover:bg-cyan-500 hover:text-black border border-border-color hover:border-cyan-400 px-3 py-1.5 text-[11px] font-bold text-text-primary transition-all cursor-pointer shrink-0"
                                >
                                  {isDraft ? t('inbox.btn_resume') : t('inbox.btn_details')}
                                  <ArrowUpRight className="h-3 w-3 rtl:rotate-[-90deg]" />
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
                className="flex flex-col items-center justify-center py-24 text-center space-y-4 bg-card-bg border border-dashed border-border-color rounded-[2rem] px-4 shadow-sm text-text-primary"
              >
                <div className="rounded-full bg-cyan-500/10 border border-cyan-500/20 p-5 text-cyan-400 animate-pulse">
                  <Inbox className="h-10 w-10" />
                </div>
                <div className="space-y-1 max-w-sm">
                  <h3 className="text-base font-semibold text-text-primary">
                    {searchTerm ? t('inbox.no_search_results') : t('inbox.no_requests_found', { category: currentCategoryLabel })}
                  </h3>
                  <p className="text-xs text-text-secondary">
                    {searchTerm 
                      ? t('inbox.no_search_results_desc')
                      : categoryParam === 'completed' 
                        ? t('inbox.empty_completed_desc')
                        : t('inbox.empty_queue_desc', { category: currentCategoryLabel.toLowerCase() })}
                  </p>
                </div>
                
                <div className="flex items-center gap-3 pt-2">
                  <Link 
                    to="/create-request"
                    className="inline-flex items-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black px-5 py-3 text-xs font-bold transition-all shadow-[0_0_15px_rgba(34,211,238,0.2)]"
                  >
                    <Plus className="h-3.5 w-3.5 stroke-[3]" />
                    {t('inbox.btn_create_request')}
                  </Link>
                  <Link 
                    to="/"
                    className="inline-flex items-center gap-2 rounded-xl bg-bg-primary hover:bg-text-primary/10 border border-border-color text-text-primary px-5 py-3 text-xs font-bold transition-all"
                  >
                    {t('inbox.btn_dashboard_home')}
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
