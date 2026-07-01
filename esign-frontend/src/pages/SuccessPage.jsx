import { useEffect, useState, useMemo } from 'react'
import { useLocation, Link } from 'react-router-dom'
import { getSigningSession, apiClient, API_URL, API_BASE } from '../services/api'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle2, FileSignature, ExternalLink, RefreshCw, Download, ShieldCheck, AlertCircle, Eye, X } from 'lucide-react'

// ── Helpers ────────────────────────────────────────────────────────────────────

function backendOriginFromBaseUrl(baseUrl) {
  try {
    const u = new URL(baseUrl)
    return u.origin
  } catch {
    return API_URL
  }
}

function toAbsoluteUrl(maybeRelativeUrl, origin) {
  if (!maybeRelativeUrl) return ''
  if (/^https?:\/\//i.test(maybeRelativeUrl)) return maybeRelativeUrl
  const path = maybeRelativeUrl.startsWith('/') ? maybeRelativeUrl : `/${maybeRelativeUrl}`
  return `${origin}${path}`
}

// ── PdfPreviewModal Component ──────────────────────────────────────────────────

export function PdfPreviewModal({ isOpen, onClose, previewUrl, title }) {
  if (!isOpen) return null

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 sm:p-6"
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          transition={{ duration: 0.3 }}
          className="relative w-full max-w-5xl h-[85vh] bg-[#0b1220]/90 border border-white/10 rounded-[2rem] overflow-hidden shadow-2xl flex flex-col"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-white/5 bg-white/[0.02] px-6 py-4">
            <div className="flex items-center gap-2.5 text-zinc-300">
              <FileSignature className="h-5 w-5 text-cyan-400" />
              <h2 className="text-sm font-semibold tracking-wide text-white truncate max-w-md">
                {title || 'Document Preview'}
              </h2>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-full bg-white/5 text-zinc-400 hover:text-white hover:bg-white/10 transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 bg-black/40 p-2 sm:p-4">
            <iframe
              title="Document Preview Viewport"
              src={previewUrl}
              className="w-full h-full rounded-2xl border border-white/5 bg-zinc-950 shadow-inner"
            />
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}

export default function SuccessPage() {
  const location = useLocation()

  const backendOrigin = useMemo(
    () => backendOriginFromBaseUrl(apiClient?.defaults?.baseURL),
    [],
  )

  const token = location.state?.token
  const isSuccessDirect = location.state?.isSuccessDirect
  const stateSession = location.state?.session
  const successType = location.state?.successType
  const stateSignedDocumentUrl = location.state?.signedDocumentUrl
  const stateDownloadUrl = location.state?.downloadUrl

  const [signedDocumentUrl, setSignedDocumentUrl] = useState(stateSignedDocumentUrl || '')
  const [downloadUrl, setDownloadUrl] = useState(stateDownloadUrl || '')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(!isSuccessDirect)
  const [session, setSession] = useState(stateSession || null)
  const [isPreviewOpen, setIsPreviewOpen] = useState(false)

  const computedDownloadUrl = downloadUrl || (token ? toAbsoluteUrl(`${API_BASE}/sign/${token}/download/`, backendOrigin) : '')
  const computedPreviewUrl = signedDocumentUrl || (token ? toAbsoluteUrl(`${API_BASE}/sign/${token}/signed/`, backendOrigin) : '')

  useEffect(() => {
    if (isSuccessDirect && stateSession) {
      setLoading(false)
      return
    }

    async function loadSignedDocument() {
      if (!token) {
        setError('Missing access token.')
        setLoading(false)
        return
      }

      try {
        const data = await getSigningSession(token)
        setSession(data)

        if (data?.status === 'completed' && data?.signed_document_url) {
          setSignedDocumentUrl(data.signed_document_url)
          setDownloadUrl(data.download_url || '')
        } else if (data?.participant_role && ['completed', 'returned', 'declined', 'viewed'].includes(data.participant_status)) {
          setSignedDocumentUrl('')
          setDownloadUrl('')
        } else {
          setError('Signed document unavailable.')
        }
      } catch (err) {
        setError(
          err?.response?.data?.detail ||
          'Unable to access signed document.'
        )
      } finally {
        setLoading(false)
      }
    }

    loadSignedDocument()
  }, [token, isSuccessDirect, stateSession])

  const role = session?.participant_role || 'signer'

  const pageContent = useMemo(() => {
    if (error) {
      const isTokenUsed = error.toLowerCase().includes('used')
      const isTokenExpired = error.toLowerCase().includes('expired')

      return {
        badge: isTokenUsed ? 'Token Already Used' : isTokenExpired ? 'Token Expired' : 'Access Denied',
        badgeColor: 'border-red-500/30 bg-red-500/10 text-red-400',
        iconColor: 'text-red-400 drop-shadow-[0_0_15px_rgba(239,68,68,0.5)]',
        pingColor: 'bg-red-500',
        isError: true,
        title: isTokenUsed ? 'Token Already Used' : isTokenExpired ? 'Token Expired' : 'Verification Failed',
        description: (
          <div className="space-y-2 mt-4 text-zinc-400">
            <p>{error}</p>
            {isTokenUsed && <p className="text-sm">You have already completed this action. If you need to view the final signed document, please check your email or contact the initiator.</p>}
            <p className="text-zinc-500 text-xs mt-6">This session is no longer active.</p>
          </div>
        ),
      }
    }

    if (role === 'approver') {
      if (successType === 'reject') {
        return {
          badge: 'Document Rejected',
          badgeColor: 'border-red-500/30 bg-red-500/10 text-red-400',
          iconColor: 'text-red-400 drop-shadow-[0_0_15px_rgba(239,68,68,0.5)]',
          pingColor: 'bg-red-500',
          isError: true,
          title: 'Document Rejected',
          description: (
            <div className="space-y-2 mt-4 text-zinc-400">
              <p>Your rejection has been successfully recorded.</p>
              <p>The workflow has been stopped.</p>
              <p className="text-zinc-500 text-xs mt-6">You may close this window.</p>
            </div>
          ),
        }
      }
      return {
        badge: 'Approval Recorded',
        badgeColor: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
        iconColor: 'text-emerald-400 drop-shadow-[0_0_15px_rgba(52,211,153,0.5)]',
        pingColor: 'bg-emerald-500',
        isError: false,
        title: 'Approval Submitted',
        description: (
          <div className="space-y-2 mt-4 text-zinc-400">
            <p>Your approval has been successfully recorded.</p>
            <p>The workflow has advanced to the next participant.</p>
            <p className="text-zinc-500 text-xs mt-6">You may close this window.</p>
          </div>
        ),
      }
    }

    if (role === 'reviewer') {
      if (successType === 'return') {
        return {
          badge: 'Document Returned',
          badgeColor: 'border-amber-500/30 bg-amber-500/10 text-amber-400',
          iconColor: 'text-amber-400 drop-shadow-[0_0_15px_rgba(245,158,11,0.5)]',
          pingColor: 'bg-amber-500',
          isError: false,
          title: 'Document Returned',
          description: (
            <div className="space-y-2 mt-4 text-zinc-400">
              <p>The document has been successfully returned.</p>
              <p>The workflow has been stopped.</p>
              <p className="text-zinc-500 text-xs mt-6">You may close this window.</p>
            </div>
          ),
        }
      }
      return {
        badge: 'Review Recorded',
        badgeColor: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
        iconColor: 'text-emerald-400 drop-shadow-[0_0_15px_rgba(52,211,153,0.5)]',
        pingColor: 'bg-emerald-500',
        isError: false,
        title: 'Review Completed',
        description: (
          <div className="space-y-2 mt-4 text-zinc-400">
            <p>Your review has been successfully submitted.</p>
            <p>The workflow has advanced.</p>
            <p className="text-zinc-500 text-xs mt-6">You may close this window.</p>
          </div>
        ),
      }
    }

    if (role === 'cc') {
      return {
        badge: 'Receipt Acknowledged',
        badgeColor: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
        iconColor: 'text-emerald-400 drop-shadow-[0_0_15px_rgba(52,211,153,0.5)]',
        pingColor: 'bg-emerald-500',
        isError: false,
        title: 'Acknowledgment Logged',
        description: (
          <div className="space-y-2 mt-4 text-zinc-400">
            <p>Your acknowledgment has been successfully recorded.</p>
            <p>The workflow has advanced.</p>
            <p className="text-zinc-500 text-xs mt-6">You may close this window.</p>
          </div>
        ),
      }
    }

    return {
      badge: 'Signature Applied',
      badgeColor: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
      iconColor: 'text-emerald-400 drop-shadow-[0_0_15px_rgba(52,211,153,0.5)]',
      pingColor: 'bg-emerald-500',
      isError: false,
      title: 'Signature Completed',
      description: (
        <div className="space-y-2 mt-4 text-zinc-400">
          <p>Document signed successfully.</p>
          <p>Workflow completed.</p>
          {signedDocumentUrl ? (
            <p className="text-zinc-400 text-sm">Provide access to final document if available.</p>
          ) : (
            <p className="text-zinc-500 text-xs mt-6">You may close this window.</p>
          )}
        </div>
      ),
    }
  }, [role, successType, signedDocumentUrl, error])

  const IconComponent = pageContent.isError ? AlertCircle : CheckCircle2

  return (
    <div className="mx-auto flex min-h-dvh max-w-5xl flex-col px-4 py-10 sm:py-20 relative z-10 font-sans">
      <div className="mx-auto w-full max-w-3xl">

        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 text-emerald-500">
            <RefreshCw className="h-10 w-10 animate-spin" />
            <span className="mt-4 text-sm font-medium tracking-widest uppercase animate-pulse">Retrieving Sealed Payload…</span>
          </div>
        ) : session?.status === 'completed' && !pageContent.isError ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="max-w-2xl mx-auto glass-panel rounded-[2rem] p-8 sm:p-12 text-center relative overflow-hidden group shadow-2xl mt-6"
          >
            {/* Glow */}
            <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/5 via-transparent to-transparent opacity-50 pointer-events-none" />

            {/* Icon */}
            <div className="relative mb-6 flex justify-center">
              <div className="absolute inset-0 rounded-full bg-emerald-500/10 blur-xl animate-pulse w-20 h-20 mx-auto" />
              <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-emerald-500/5 border border-emerald-500/20 text-emerald-400 shadow-[0_0_30px_rgba(16,185,129,0.1)]">
                <CheckCircle2 className="h-10 w-10" />
              </div>
            </div>

            <h1 className="text-3xl sm:text-4xl font-light text-white neon-text-glow tracking-tight">
              Workflow Completed
            </h1>
            <p className="mt-3 text-zinc-400 text-sm leading-relaxed max-w-md mx-auto">
              The document has been successfully approved and signed.
            </p>

            {/* Status Section */}
            <div className="w-full mt-8 p-6 rounded-2xl border border-white/5 bg-black/40 text-left space-y-4">
              <div className="flex items-center justify-between border-b border-white/5 pb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-zinc-500">Routing Status</span>
                <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/20 bg-emerald-500/5 px-2.5 py-0.5 text-[10px] font-bold uppercase text-emerald-400 tracking-wider">
                  Completed
                </span>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500">Package Status</span>
                  <span className="text-xs font-bold text-emerald-400 uppercase tracking-wide">
                    Completed
                  </span>
                </div>
                {session?.signer_name && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-zinc-500">Final Recipient</span>
                    <span className="text-xs font-semibold text-zinc-300">
                      {session.signer_name}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Actions Section */}
            <div className="mt-8 space-y-3">
              <button
                onClick={() => setIsPreviewOpen(true)}
                className="flex w-full items-center justify-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 text-black px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] cursor-pointer"
              >
                <Eye className="h-4 w-4" /> View Signed Document
              </button>

              <a
                href={computedDownloadUrl}
                download
                className="flex w-full items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/[0.02] text-white hover:bg-white/10 px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 cursor-pointer"
              >
                <Download className="h-4 w-4" /> Download Signed Document
              </a>

              {!token && (
                <Link
                  to="/"
                  className="flex w-full items-center justify-center gap-2 rounded-2xl border border-white/5 bg-zinc-950 text-zinc-400 hover:text-white px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300"
                >
                  Return to Workspace
                </Link>
              )}
            </div>
          </motion.div>
        ) : (
          <>
            <motion.div
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-12 text-center"
            >
              <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium uppercase tracking-widest mb-6 backdrop-blur-md ${pageContent.badgeColor}`}>
                <ShieldCheck className="h-4 w-4" />
                {pageContent.badge}
              </div>

              <div className="relative w-24 h-24 mx-auto mb-6">
                <div className={`absolute inset-0 rounded-full animate-ping opacity-20 ${pageContent.pingColor}`} />
                <div className={`absolute inset-0 rounded-full blur-xl opacity-20 ${pageContent.pingColor}`} />
                <IconComponent className={`relative z-10 w-full h-full ${pageContent.iconColor}`} />
              </div>

              <h1 className="text-3xl sm:text-5xl font-light tracking-tight text-white neon-text-glow">
                {pageContent.title}
              </h1>

              <div className="max-w-md mx-auto">
                {pageContent.description}
              </div>
            </motion.div>

            <AnimatePresence mode="wait">
              {error && !isSuccessDirect ? (
                <motion.div
                  key="error"
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="rounded-2xl border border-red-500/30 bg-red-500/10 px-6 py-8 text-center text-red-200 backdrop-blur-md"
                >
                  {error}
                </motion.div>
              ) : signedDocumentUrl && !pageContent.isError ? (
                <motion.div
                  key="content"
                  initial={{ opacity: 0, y: 30 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="glass-panel rounded-[2rem] overflow-hidden relative group"
                >
                  <div className="absolute inset-0 bg-gradient-to-b from-emerald-500/5 to-transparent opacity-50 pointer-events-none" />

                  <div className="flex flex-col sm:flex-row items-center justify-between border-b border-white/5 bg-white/[0.02] px-6 py-4 sm:py-5 gap-4">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400">
                        <FileSignature className="h-5 w-5" />
                      </div>
                      <div>
                        <h2 className="text-sm font-semibold tracking-wide text-white">Sealed Document</h2>
                        <p className="text-xs text-zinc-500 mt-0.5">Read-only verified copy</p>
                      </div>
                    </div>

                    <a
                      href={computedPreviewUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500/10 text-emerald-400 text-sm font-medium hover:bg-emerald-500/20 transition-colors w-full sm:w-auto justify-center"
                    >
                      <ExternalLink className="h-4 w-4" /> Open Externally
                    </a>
                  </div>

                  <div className="p-2 sm:p-6 bg-black/40">
                    <iframe
                      title="Signed Document"
                      src={computedPreviewUrl}
                      className="h-[min(600px,70vh)] w-full rounded-2xl border border-white/5 bg-zinc-950 shadow-inner"
                    />
                  </div>

                  <div className="border-t border-white/5 px-6 py-5 bg-white/[0.01]">
                    <a
                      href={computedDownloadUrl}
                      download
                      className="group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-2xl bg-white px-4 py-3.5 text-sm font-bold text-black transition-all hover:bg-zinc-200 hover:shadow-[0_0_30px_rgba(255,255,255,0.2)] uppercase tracking-widest sm:w-auto sm:mx-auto sm:max-w-xs"
                    >
                      <span className="relative z-10 flex items-center gap-2">
                        <Download className="h-4 w-4" />
                        Download File
                      </span>
                    </a>
                  </div>
                </motion.div>
              ) : session && !pageContent.isError ? (
                <motion.div
                  key="intermediate-content"
                  initial={{ opacity: 0, y: 30 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="glass-panel rounded-[2rem] p-8 text-center relative overflow-hidden group border border-emerald-500/20"
                >
                  <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/10 to-transparent opacity-50 pointer-events-none" />
                  <h3 className="text-xl font-light text-emerald-300 mb-4 uppercase tracking-wider">
                    {session.participant_role === 'cc' ? 'Observation Logged' :
                      session.participant_role === 'reviewer' ? 'Review Completed' :
                        session.participant_role === 'approver' ? 'Approval Completed' :
                          'Step Complete'}
                  </h3>
                  <p className="text-sm text-zinc-400 mb-6 max-w-md mx-auto">
                    {session.participant_role === 'cc' ? 'Your view audit event has been cryptographically recorded.' :
                      session.participant_role === 'reviewer' ? 'Thank you! Your review action has been registered, and the workflow has advanced to the next recipient.' :
                        session.participant_role === 'approver' ? 'Thank you! Your approval decision has been registered, and the workflow has advanced to the next recipient.' :
                          'Thank you! Your action has been registered, and the sequential routing has successfully advanced.'}
                  </p>
                  <div className="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    Action Type: {session.participant_role?.toUpperCase()} Complete
                  </div>
                </motion.div>
              ) : null}
            </AnimatePresence>
          </>
        )}
      </div>

      <PdfPreviewModal
        isOpen={isPreviewOpen}
        onClose={() => setIsPreviewOpen(false)}
        previewUrl={computedPreviewUrl}
        title={session?.title || 'Signed Document'}
      />
    </div>
  )
}