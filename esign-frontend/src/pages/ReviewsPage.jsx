import React, { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ShieldCheck,
  Search,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  RotateCcw,
  Clock,
  User,
  FileText,
  ChevronRight,
  ArrowLeft,
  Filter
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { getReviewQueue } from '../services/api'
import UserNav from '../components/UserNav'
import ReviewDossierModal from '../components/reviews/ReviewDossierModal'

export default function ReviewsPage() {
  const [cases, setCases] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Filters
  const [statusFilter, setStatusFilter] = useState('under_review')
  const [searchQuery, setSearchQuery] = useState('')

  // Selected review case modal
  const [selectedParticipantId, setSelectedParticipantId] = useState(null)
  const [toastMessage, setToastMessage] = useState(null)

  const loadQueue = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getReviewQueue({
        status: statusFilter,
        q: searchQuery
      })
      setCases(data.cases || [])
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load review queue.')
    } finally {
      setLoading(false)
    }
  }, [statusFilter, searchQuery])

  useEffect(() => {
    loadQueue()
  }, [loadQueue])

  const handleDecisionMade = (participantId, action) => {
    setToastMessage({
      type: action === 'approve' ? 'success' : action === 'resubmit' ? 'warning' : 'danger',
      text: `Case #${participantId} successfully marked as ${action}d.`
    })
    setTimeout(() => setToastMessage(null), 4000)
    loadQueue()
  }

  const formatAge = (seconds) => {
    if (!seconds || seconds < 60) return 'Just now'
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}m ago`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours}h ago`
    const days = Math.floor(hours / 24)
    return `${days}d ago`
  }

  return (
    <div className="min-h-dvh max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col gap-8">
      {/* Top Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            to="/"
            className="p-2 rounded-xl glass-panel text-text-secondary hover:text-cyan-400 hover:border-cyan-500/30 transition-all cursor-pointer"
            title="Return to Workspace"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-6 w-6 text-cyan-400" />
              <h1 className="text-2xl font-black tracking-tight text-text-primary">
                Authorization Review Queue
              </h1>
            </div>
            <p className="text-xs text-text-secondary mt-0.5">
              Authorized staff console for evaluating identity and verification discrepancies.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
          <UserNav />
        </div>
      </div>

      {/* Toast Notification */}
      <AnimatePresence>
        {toastMessage && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className={`p-3 rounded-xl border text-xs font-semibold flex items-center gap-2 ${
              toastMessage.type === 'success'
                ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                : toastMessage.type === 'warning'
                ? 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                : 'bg-red-500/10 text-red-300 border-red-500/30'
            }`}
          >
            <CheckCircle2 className="h-4 w-4" />
            <span>{toastMessage.text}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Filters and Search Bar */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 p-4 rounded-2xl glass-panel bg-bg-surface/50 border border-border-color">
        {/* Status Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0">
          {[
            { id: 'under_review', label: 'Under Review', icon: AlertTriangle },
            { id: 'resubmission_required', label: 'Resubmission', icon: RotateCcw },
            { id: 'approved', label: 'Approved', icon: CheckCircle2 },
            { id: 'rejected', label: 'Rejected', icon: XCircle },
            { id: 'all', label: 'All Cases', icon: Filter }
          ].map((tab) => {
            const Icon = tab.icon
            const active = statusFilter === tab.id
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setStatusFilter(tab.id)}
                className={`px-3 py-2 rounded-xl text-xs font-semibold transition-all flex items-center gap-1.5 whitespace-nowrap cursor-pointer ${
                  active
                    ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 shadow-sm shadow-cyan-500/10'
                    : 'text-text-secondary hover:text-text-primary hover:bg-bg-primary/40'
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                <span>{tab.label}</span>
              </button>
            )
          })}
        </div>

        {/* Search & Refresh */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1 sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-text-secondary" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search signer or package..."
              className="w-full pl-9 pr-3 py-2 text-xs rounded-xl bg-bg-primary/80 border border-border-color text-text-primary placeholder:text-text-secondary/50 focus:outline-none focus:border-cyan-500"
            />
          </div>
          <button
            type="button"
            onClick={loadQueue}
            disabled={loading}
            className="p-2 rounded-xl glass-panel text-text-secondary hover:text-cyan-400 transition-colors cursor-pointer"
            title="Refresh review queue"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* Case List Table */}
      <div className="rounded-2xl glass-panel bg-bg-surface/40 border border-border-color overflow-hidden">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-24 text-cyan-400">
            <RefreshCw className="h-8 w-8 animate-spin mb-3" />
            <span className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
              Querying Review Cases...
            </span>
          </div>
        ) : error ? (
          <div className="p-8 text-center text-red-400 text-xs">{error}</div>
        ) : cases.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-text-secondary space-y-3">
            <div className="p-4 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
              <CheckCircle2 className="h-8 w-8" />
            </div>
            <div className="text-sm font-bold text-text-primary">No cases found</div>
            <p className="text-xs max-w-sm text-center">
              There are currently no verification cases matching this status filter.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-border-color/60 bg-bg-surface/60 text-[11px] font-bold text-text-secondary uppercase tracking-wider">
                  <th className="py-3 px-4">Signer / Participant</th>
                  <th className="py-3 px-4">Envelope / Package</th>
                  <th className="py-3 px-4">Review Trigger</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Submitted</th>
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-color/40 text-xs">
                {cases.map((item) => (
                  <tr
                    key={item.participant_id}
                    className="hover:bg-cyan-500/5 transition-colors group cursor-pointer"
                    onClick={() => setSelectedParticipantId(item.participant_id)}
                  >
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-2.5">
                        <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 shrink-0">
                          <User className="h-4 w-4" />
                        </div>
                        <div>
                          <div className="font-semibold text-text-primary">{item.participant_name}</div>
                          <div className="text-[11px] text-text-secondary">{item.participant_email}</div>
                        </div>
                      </div>
                    </td>

                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-1.5 font-medium text-text-primary">
                        <FileText className="h-3.5 w-3.5 text-text-secondary shrink-0" />
                        <span className="truncate max-w-[200px]">{item.envelope_title}</span>
                      </div>
                      <div className="text-[10px] text-text-secondary mt-0.5">ID: #{item.envelope_id}</div>
                    </td>

                    <td className="py-3.5 px-4 max-w-xs">
                      <div className="text-amber-400/90 font-medium truncate" title={item.review_reason}>
                        {item.review_reason}
                      </div>
                    </td>

                    <td className="py-3.5 px-4">
                      <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${
                        item.review_status === 'under_review'
                          ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                          : item.review_status === 'approved'
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                          : item.review_status === 'rejected'
                          ? 'bg-red-500/10 text-red-400 border-red-500/30'
                          : 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30'
                      }`}>
                        {item.review_status?.replace('_', ' ') || 'UNDER REVIEW'}
                      </span>
                    </td>

                    <td className="py-3.5 px-4 text-text-secondary whitespace-nowrap">
                      <div className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        <span>{formatAge(item.review_age_seconds)}</span>
                      </div>
                    </td>

                    <td className="py-3.5 px-4 text-right">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          setSelectedParticipantId(item.participant_id)
                        }}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 text-xs font-bold transition-all cursor-pointer"
                      >
                        <span>Inspect</span>
                        <ChevronRight className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Review Dossier Modal */}
      {selectedParticipantId && (
        <ReviewDossierModal
          participantId={selectedParticipantId}
          isOpen={Boolean(selectedParticipantId)}
          onClose={() => setSelectedParticipantId(null)}
          onDecisionMade={handleDecisionMade}
        />
      )}
    </div>
  )
}
