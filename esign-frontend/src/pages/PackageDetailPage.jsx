import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getPackageDetail } from '../services/api.js'
import UserNav from '../components/UserNav.jsx'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  ArrowLeft, 
  FileText, 
  User, 
  Mail, 
  Clock, 
  CheckCircle2, 
  AlertCircle, 
  RefreshCw, 
  Download, 
  GitCommit, 
  GitBranch, 
  Layers, 
  Activity,
  ChevronDown,
  Bell,
  Share2,
  Printer,
  Settings,
  Eye,
  X
} from 'lucide-react'
import { PdfPreviewModal } from './SuccessPage.jsx'

export default function PackageDetailPage() {
  const { id } = useParams()
  const [data, setData] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [copiedId, setCopiedId] = useState(null)
  const [isPreviewOpen, setIsPreviewOpen] = useState(false)

  const handleCopy = (id, url) => {
    navigator.clipboard.writeText(url)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  async function loadPackage() {
    setIsLoading(true)
    setError('')
    try {
      const res = await getPackageDetail(id)
      setData(res)
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
        err?.message ||
        'Unable to load package details.'
      )
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadPackage()
  }, [id])

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

  const stepsMap = {}
  if (data && data.participants) {
    data.participants.forEach(p => {
      const stepNum = p.step_number || 1
      if (!stepsMap[stepNum]) stepsMap[stepNum] = []
      stepsMap[stepNum].push(p)
    })
  }
  const sortedStepNumbers = Object.keys(stepsMap).map(Number).sort((a, b) => a - b)

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:py-16 relative z-10 font-sans">
      
      {/* ── Return Link & UserNav ── */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8 flex justify-between items-center"
      >
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-400 hover:text-cyan-400 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Dashboard
        </Link>
        <UserNav />
      </motion.div>

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
              Loading Package Metrics…
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
                onClick={loadPackage} 
                className="mt-3 text-xs font-semibold uppercase tracking-wider text-red-400 hover:text-red-300 transition-colors"
              >
                Try Again
              </button>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="details"
            variants={containerVariants}
            initial="hidden"
            animate="show"
            className="space-y-8"
          >
            
            {/* ── 1. PACKAGE HEADER ── */}
            <motion.div 
              variants={itemVariants} 
              className="glass-panel rounded-3xl p-6 sm:p-8 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6"
            >
              <div>
                <div className="flex flex-wrap items-center gap-3 mb-2">
                  <span className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold tracking-wide capitalize ${
                    data.status === 'completed' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                    data.status === 'sent' ? 'bg-violet-500/10 text-violet-400 border border-violet-500/20' :
                    data.status === 'viewed' ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' :
                    data.status === 'draft' ? 'bg-zinc-500/10 text-zinc-400 border border-zinc-500/20' :
                    'bg-red-500/10 text-red-400 border border-red-500/20'
                  }`}>
                    {data.status}
                  </span>
                  <span className="text-[10px] text-zinc-500 font-mono font-bold tracking-wider">ID: {data.id}</span>
                </div>
                <h1 className="text-2xl sm:text-4xl font-light text-white tracking-tight leading-tight">
                  {data.title}
                </h1>
                {data.description && (
                  <p className="mt-2 text-zinc-400 text-sm max-w-2xl">{data.description}</p>
                )}
              </div>

              <div className="flex flex-col items-start sm:items-end">
                <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">Created Date</span>
                <span className="text-sm font-semibold text-zinc-300 mt-1 font-mono">
                  {new Date(data.created_at).toLocaleDateString(undefined, {
                    month: 'long',
                    day: 'numeric',
                    year: 'numeric'
                  })}
                </span>
              </div>
            </motion.div>

            {/* ── Two Columns Workspace ── */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              
              {/* Left Column (2/3 width) */}
              <div className="lg:col-span-2 space-y-8">
                
                {/* ── 2. PARTICIPANTS (STEP-BASED) ── */}
                <motion.div variants={itemVariants} className="space-y-6">
                  {/* Section Title */}
                  <div className="flex items-center justify-between pb-2 border-b border-white/5">
                    <h2 className="text-lg font-light text-white flex items-center gap-2">
                      <User className="h-5 w-5 text-cyan-400" />
                      Participant Link Management
                    </h2>
                    <span className="text-xs text-zinc-500 font-mono font-medium">
                      {sortedStepNumbers.length} Step{sortedStepNumbers.length > 1 ? 's' : ''} Configured
                    </span>
                  </div>

                  <div className="space-y-4">
                    {sortedStepNumbers.map((stepNum, idx) => {
                      const stepParticipants = stepsMap[stepNum] || []
                      
                      // Calculate Step State dynamically based on participant statuses
                      let stepState = 'pending'
                      if (stepParticipants.every(p => p.status === 'completed')) {
                        stepState = 'completed'
                      } else if (stepParticipants.some(p => p.status === 'active' || p.status === 'viewed')) {
                        stepState = 'active'
                      }
                      
                      return (
                        <div key={stepNum} className="flex flex-col items-center w-full">
                          {/* Step Panel Card */}
                          <div className={`w-full glass-panel rounded-3xl border transition-all duration-300 overflow-hidden shadow-2xl p-6 ${
                            stepState === 'completed'
                              ? 'border-emerald-500/20 bg-emerald-950/[0.02] shadow-[0_0_20px_rgba(16,185,129,0.02)]' 
                              : stepState === 'active'
                              ? 'border-cyan-500/30 bg-cyan-950/[0.01] shadow-[0_0_25px_rgba(34,211,238,0.04)]'
                              : 'border-white/5 bg-white/[0.002] opacity-60'
                          }`}>
                            {/* Step Panel Header */}
                            <div className="flex items-center justify-between mb-4 pb-3 border-b border-white/5">
                              <div className="flex items-center gap-3">
                                <span className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold border transition-all duration-300 ${
                                  stepState === 'completed'
                                    ? 'bg-emerald-500/20 border-emerald-500/30 text-emerald-400' 
                                    : stepState === 'active'
                                    ? 'bg-cyan-500/20 border-cyan-500/30 text-cyan-400 shadow-[0_0_15px_rgba(34,211,238,0.15)]'
                                    : 'bg-zinc-800/40 border-white/5 text-zinc-500'
                                }`}>
                                  {stepNum}
                                </span>
                                <div>
                                  <h3 className="text-sm font-semibold text-white uppercase tracking-wider">
                                    Step {stepNum} Recipients
                                  </h3>
                                  <p className="text-[10px] text-zinc-500">Executes concurrently at this step level</p>
                                </div>
                              </div>

                              <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold tracking-wide capitalize border transition-all duration-300 ${
                                stepState === 'completed'
                                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
                                  : stepState === 'active'
                                  ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20 animate-pulse'
                                  : 'bg-zinc-800/40 text-zinc-500 border-white/5'
                              }`}>
                                {stepState}
                              </span>
                            </div>

                            {/* Recipients Grid of Cards */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
                              {stepParticipants.map((participant) => {
                                const isCopied = copiedId === participant.id;
                                return (
                                  <div
                                    key={participant.id}
                                    className={`relative rounded-2xl border p-5 transition-all duration-300 ${
                                      participant.status === 'completed'
                                        ? 'border-emerald-500/20 bg-emerald-950/[0.02] shadow-[0_0_20px_rgba(16,185,129,0.02)]'
                                        : participant.status === 'active' || participant.status === 'viewed'
                                        ? 'border-cyan-500/30 bg-cyan-950/[0.01] shadow-[0_0_25px_rgba(34,211,238,0.04)]'
                                        : 'border-white/5 bg-white/[0.002]'
                                    }`}
                                  >
                                    <div className="flex flex-col h-full justify-between gap-4">
                                      <div className="space-y-2">
                                        <div className="flex items-center justify-between gap-2">
                                          <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 font-mono">
                                            Step {participant.step_number}
                                          </span>
                                          <span className={`inline-flex px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider border ${
                                            participant.role === 'signer' ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20' :
                                            participant.role === 'approver' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                                            participant.role === 'reviewer' ? 'bg-violet-500/10 text-violet-400 border-violet-500/20' :
                                            'bg-zinc-500/10 text-zinc-300 border-white/5'
                                          }`}>
                                            {participant.role}
                                          </span>
                                        </div>
                                        <div>
                                          <h4 className="text-base font-semibold text-white truncate">
                                            {participant.name}
                                          </h4>
                                          <p className="text-xs text-zinc-400 font-mono flex items-center gap-1.5 mt-0.5 truncate">
                                            <Mail className="h-3.5 w-3.5 text-zinc-500 shrink-0" />
                                            {participant.email}
                                          </p>
                                        </div>
                                        <div className="flex items-center gap-2 pt-1">
                                          <span className="text-xs text-zinc-500">Status:</span>
                                          <span className={`inline-flex px-2.5 py-0.5 rounded-full text-[10px] font-bold tracking-wide capitalize border ${
                                            participant.status === 'completed' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                                            participant.status === 'active' ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20 shadow-[0_0_10px_rgba(34,211,238,0.05)] animate-pulse' :
                                            participant.status === 'viewed' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                                            participant.status === 'declined' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                                            participant.status === 'returned' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                                            'bg-zinc-800 text-zinc-500 border-white/5'
                                          }`}>
                                            {participant.status || 'pending'}
                                          </span>
                                        </div>
                                      </div>

                                      <div className="pt-3 border-t border-white/5 flex items-center gap-2">
                                        {participant.action_url ? (
                                          <>
                                            <button
                                              onClick={() => handleCopy(participant.id, participant.action_url)}
                                              className={`inline-flex items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-xs font-bold border transition-all duration-300 w-full cursor-pointer ${
                                                isCopied
                                                  ? 'bg-emerald-500 text-black border-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.2)]'
                                                  : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white border-white/5'
                                              }`}
                                            >
                                              {isCopied ? (
                                                <>
                                                  <CheckCircle2 className="h-3.5 w-3.5 stroke-[2.5]" />
                                                  Copied Link!
                                                </>
                                              ) : (
                                                <>
                                                  <Share2 className="h-3.5 w-3.5" />
                                                  Copy Link
                                                </>
                                              )}
                                            </button>
                                            <a
                                              href={participant.action_url}
                                              target="_blank"
                                              rel="noreferrer"
                                              className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 px-3.5 py-2 text-xs font-bold border border-cyan-500/20 transition-all duration-300 shrink-0"
                                              title="Test sign / review / approve session"
                                            >
                                              Act
                                              <ArrowLeft className="h-3.5 w-3.5 rotate-180" />
                                            </a>
                                          </>
                                        ) : (
                                          <span className="text-xs text-zinc-600 font-mono">—</span>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>

                          {/* Downstream progression arrow */}
                          {idx < sortedStepNumbers.length - 1 && (
                            <div className="flex flex-col items-center my-3 relative">
                              <div className="h-8 w-[1px] bg-gradient-to-b from-cyan-500/50 to-transparent" />
                              <div className={`flex h-7 w-7 items-center justify-center rounded-full border transition-all duration-300 ${
                                stepState === 'completed'
                                  ? 'bg-emerald-950/40 border-emerald-500/30 text-emerald-400'
                                  : 'bg-cyan-950/40 border-cyan-500/30 text-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.15)] backdrop-blur-md'
                              }`}>
                                <ChevronDown className={`h-4 w-4 ${stepState === 'active' ? 'animate-pulse' : ''}`} />
                              </div>
                              <div className="h-8 w-[1px] bg-gradient-to-t from-cyan-500/50 to-transparent" />
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </motion.div>

                {/* ── 4. DOCUMENT SECTION ── */}
                <motion.div variants={itemVariants} className="glass-panel rounded-3xl p-6 sm:p-8 space-y-6 border border-white/5">
                  <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6">
                    <div className="flex items-center gap-4">
                      <div className="h-12 w-12 rounded-2xl bg-cyan-500/20 flex items-center justify-center border border-cyan-500/30">
                        <FileText className="h-6 w-6 text-cyan-400" />
                      </div>
                      <div>
                        <h2 className="text-base font-semibold text-white">Original Document</h2>
                        <p className="text-xs text-zinc-500 mt-0.5 font-mono">{data.document.filename}</p>
                      </div>
                    </div>
                  </div>
                </motion.div>

                {/* ── 4b. SIGNED DOCUMENT SECTION (COMPLETED) ── */}
                {data.status === 'completed' && data.signed_document?.available && (
                  <motion.div variants={itemVariants} className="glass-panel rounded-3xl p-6 sm:p-8 space-y-6 border border-emerald-500/20 bg-emerald-950/[0.01] shadow-[0_0_30px_rgba(16,185,129,0.02)]">
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6">
                      <div className="flex items-center gap-4">
                        <div className="h-12 w-12 rounded-2xl bg-emerald-500/20 flex items-center justify-center border border-emerald-500/30 text-emerald-400">
                          <CheckCircle2 className="h-6 w-6" />
                        </div>
                        <div>
                          <h2 className="text-base font-semibold text-white">Signed Document</h2>
                          <p className="text-xs text-zinc-300 mt-0.5 font-mono">
                            {data.signed_document.filename ? data.signed_document.filename.replace(/(\.pdf)$/i, '_signed$1') : 'signed_document.pdf'}
                          </p>
                          {data.signed_document.created_at && (
                            <p className="text-[10px] text-zinc-500 mt-1">
                              Created: {new Date(data.signed_document.created_at).toLocaleString()}
                            </p>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-3 w-full sm:w-auto">
                        <button
                          onClick={() => setIsPreviewOpen(true)}
                          className="flex-1 sm:flex-none inline-flex items-center justify-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 text-black px-5 py-3 text-xs font-bold transition-all duration-300 hover:shadow-[0_0_20px_rgba(34,211,238,0.2)] tracking-wider cursor-pointer"
                        >
                          <Eye className="h-4 w-4" />
                          Preview
                        </button>
                        <a
                          href={data.signed_document.download_url}
                          download
                          className="flex-1 sm:flex-none inline-flex items-center justify-center gap-2 rounded-2xl bg-emerald-500/20 border border-emerald-500/30 hover:bg-emerald-500/30 text-emerald-300 px-5 py-3 text-xs font-bold transition-all duration-300 tracking-wider"
                        >
                          <Download className="h-4 w-4" />
                          Download
                        </a>
                      </div>
                    </div>
                  </motion.div>
                )}

                {/* ── 5. WORKFLOW SECTION ── */}
                <motion.div variants={itemVariants} className="glass-panel rounded-3xl p-6 sm:p-8 space-y-6 border border-white/5">
                  <div>
                    <h2 className="text-base font-semibold text-white flex items-center gap-2">
                      <GitCommit className="h-4 w-4 text-cyan-400" />
                      Workflow Routing
                    </h2>
                    <p className="text-xs text-zinc-500 mt-1">Configured participant traversal pipeline.</p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    
                    {/* Active: Single Signer */}
                    <div className={`rounded-2xl border p-5 flex flex-col justify-between min-h-[140px] relative transition-all duration-300 ${
                      data.participants.length === 1
                        ? 'border-cyan-500/30 bg-cyan-500/10 shadow-[0_0_20px_rgba(34,211,238,0.05)]'
                        : 'border-white/5 bg-white/[0.01] opacity-40'
                    }`}>
                      <div className="flex justify-between items-start">
                        <span className="text-[10px] uppercase font-bold tracking-widest text-zinc-400">
                          {data.participants.length === 1 ? 'Active' : 'Pipeline Option'}
                        </span>
                        <Layers className="h-5 w-5 text-zinc-400" />
                      </div>
                      <div className="mt-4">
                        <h3 className="text-sm font-bold text-white">Single Signer</h3>
                        <p className="text-[10px] text-zinc-400/70 mt-0.5">Generates secure signing link for a single target recipient.</p>
                      </div>
                    </div>

                    {/* Placeholder: Sequential Workflow */}
                    <div className={`rounded-2xl border p-5 flex flex-col justify-between min-h-[140px] relative transition-all duration-300 ${
                      sortedStepNumbers.length > 1
                        ? 'border-cyan-500/30 bg-cyan-500/10 shadow-[0_0_20px_rgba(34,211,238,0.05)]'
                        : 'border-white/5 bg-white/[0.01] opacity-40'
                    }`}>
                      <div className="flex justify-between items-start">
                        <span className="text-[10px] uppercase font-bold tracking-widest text-zinc-400">
                          {sortedStepNumbers.length > 1 ? 'Active' : 'Pipeline Option'}
                        </span>
                        <GitCommit className="h-5 w-5 text-zinc-400" />
                      </div>
                      <div className="mt-4">
                        <h3 className="text-sm font-bold text-white">Sequential Workflow</h3>
                        <p className="text-[10px] text-zinc-400/70 mt-0.5">Route documents in sequence (e.g. Step 1 → Step 2 → Step 3).</p>
                      </div>
                    </div>

                    {/* Placeholder: Parallel Workflow */}
                    <div className={`rounded-2xl border p-5 flex flex-col justify-between min-h-[140px] relative transition-all duration-300 ${
                      sortedStepNumbers.length === 1 && data.participants.length > 1
                        ? 'border-cyan-500/30 bg-cyan-500/10 shadow-[0_0_20px_rgba(34,211,238,0.05)]'
                        : 'border-white/5 bg-white/[0.01] opacity-40'
                    }`}>
                      <div className="flex justify-between items-start">
                        <span className="text-[10px] uppercase font-bold tracking-widest text-zinc-400">
                          {sortedStepNumbers.length === 1 && data.participants.length > 1 ? 'Active' : 'Pipeline Option'}
                        </span>
                        <GitBranch className="h-5 w-5 text-zinc-400" />
                      </div>
                      <div className="mt-4">
                        <h3 className="text-sm font-bold text-white">Parallel Workflow</h3>
                        <p className="text-[10px] text-zinc-400/70 mt-0.5">Deliver signing sessions concurrently to all participants at once.</p>
                      </div>
                    </div>

                  </div>
                </motion.div>

              </div>

              {/* Right Column: Timeline (1/3 width) */}
              {/* ── 3. AUDIT TIMELINE ── */}
              <div className="lg:col-span-1">
                {/* ── Request Settings Card ── */}
                <motion.div variants={itemVariants} className="glass-panel rounded-3xl overflow-hidden border border-white/5 mb-8">
                  <div className="border-b border-white/5 bg-white/[0.01] px-6 py-5">
                    <h2 className="text-base font-semibold tracking-wide text-white flex items-center gap-2">
                      <Settings className="h-4 w-4 text-cyan-400" />
                      Request Settings
                    </h2>
                  </div>

                  <div className="p-6 space-y-4 text-sm">
                    {/* Automatic Reminders */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5 text-zinc-400">
                        <Bell className="h-4 w-4 text-zinc-500" />
                        <span>Automatic Reminders</span>
                      </div>
                      <span className={`px-2.5 py-0.5 rounded text-xs font-semibold ${data.send_reminders ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' : 'bg-zinc-800 text-zinc-500 border border-white/5'}`}>
                        {data.send_reminders ? 'Enabled' : 'Disabled'}
                      </span>
                    </div>

                    {/* Final Document Delivery */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5 text-zinc-400">
                        <Share2 className="h-4 w-4 text-zinc-500" />
                        <span>Final Delivery</span>
                      </div>
                      <span className={`px-2.5 py-0.5 rounded text-xs font-semibold ${data.send_final_email ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-zinc-800 text-zinc-500 border border-white/5'}`}>
                        {data.send_final_email ? 'Enabled' : 'Disabled'}
                      </span>
                    </div>

                    {/* Allow Printing */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5 text-zinc-400">
                        <Printer className="h-4 w-4 text-zinc-500" />
                        <span>Allow Printing</span>
                      </div>
                      <span className={`px-2.5 py-0.5 rounded text-xs font-semibold ${data.allow_printing ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-zinc-800 text-zinc-500 border border-white/5'}`}>
                        {data.allow_printing ? 'Allowed' : 'Restricted'}
                      </span>
                    </div>

                    {/* Additional Recipients */}
                    <div className="pt-3 border-t border-white/5 space-y-2">
                      <div className="text-zinc-400 flex items-center gap-2.5">
                        <Mail className="h-4 w-4 text-zinc-500" />
                        <span>Additional Observers</span>
                      </div>
                      {data.additional_recipients && data.additional_recipients.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {data.additional_recipients.map((email) => (
                            <span key={email} className="inline-flex rounded bg-zinc-800/80 px-2.5 py-1 text-[11px] font-mono text-cyan-300 border border-white/5">
                              {email}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-zinc-600 pl-6.5">No additional recipients.</p>
                      )}
                    </div>

                  </div>
                </motion.div>

                <motion.div variants={itemVariants} className="glass-panel rounded-3xl overflow-hidden border border-white/5">
                  <div className="border-b border-white/5 bg-white/[0.01] px-6 py-5">
                    <h2 className="text-base font-semibold tracking-wide text-white flex items-center gap-2">
                      <Clock className="h-4 w-4 text-cyan-400" />
                      Audit History
                    </h2>
                  </div>

                  <div className="p-6 overflow-y-auto max-h-[500px] custom-scrollbar">
                    {data.audit_trail.length > 0 ? (
                      <div className="relative pl-6 border-l border-white/10 space-y-8">
                        {data.audit_trail.map((activity, idx) => (
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
                        <Clock className="h-8 w-8 mb-2 opacity-30" />
                        <p className="text-xs">No activity records mapped.</p>
                      </div>
                    )}
                  </div>
                </motion.div>
              </div>

            </div>

          </motion.div>
        )}
      </AnimatePresence>
      <PdfPreviewModal
        isOpen={isPreviewOpen}
        onClose={() => setIsPreviewOpen(false)}
        previewUrl={data?.signed_document?.preview_url || ''}
        title={data?.title || 'Signed Document'}
      />
    </div>
  )
}
