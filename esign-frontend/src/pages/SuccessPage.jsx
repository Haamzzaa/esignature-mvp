import { useEffect, useState, useMemo } from 'react'
import { useLocation, Link } from 'react-router-dom'
import { useLocale } from '../context/LocaleContext'
import { getSigningSession, apiClient, API_URL, API_BASE } from '../services/api'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle2, FileSignature, ExternalLink, RefreshCw, Download, ShieldCheck, AlertCircle, Eye, X, Home, Clock, Check } from 'lucide-react'

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

// ── BlobPdfViewer Component ──────────────────────────────────────────────────

export function BlobPdfViewer({ url, title, className = '' }) {
  const { t } = useLocale()
  const [blobUrl, setBlobUrl] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!url) {
      setBlobUrl(null)
      setIsLoading(false)
      setError(null)
      return
    }

    let isSubscribed = true
    let objectUrl = null
    setIsLoading(true)
    setError(null)

    async function loadPdfBlob() {
      try {
        const response = await apiClient.get(url, {
          responseType: 'blob',
        })
        if (!isSubscribed) return

        const blob = new Blob([response.data], { type: 'application/pdf' })
        objectUrl = URL.createObjectURL(blob)
        setBlobUrl(objectUrl)
        setIsLoading(false)
      } catch (err) {
        if (!isSubscribed) return
        console.error('Failed to load PDF preview:', err)
        setError(
          err?.response?.data?.detail ||
          err?.message ||
          t('errors.network_error')
        )
        setIsLoading(false)
      }
    }

    loadPdfBlob()

    return () => {
      isSubscribed = false
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl)
      }
    }
  }, [url, t])

  if (isLoading) {
    return (
      <div className={`flex flex-col items-center justify-center gap-3 text-cyan-400 p-8 ${className}`}>
        <RefreshCw className="h-8 w-8 animate-spin" />
        <p className="text-xs font-medium tracking-wide text-zinc-300">{t('common.loading')}</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className={`flex flex-col items-center justify-center gap-3 text-red-400 p-6 text-center ${className}`}>
        <AlertCircle className="h-8 w-8 text-red-400" />
        <p className="text-sm font-medium text-red-200">{error}</p>
      </div>
    )
  }

  if (!blobUrl) return null

  return (
    <iframe
      title={title || t('success.doc_preview_title')}
      src={blobUrl}
      className={className}
    />
  )
}

// ── PdfPreviewModal Component ──────────────────────────────────────────────────

export function PdfPreviewModal({ isOpen, onClose, previewUrl, title }) {
  const { t } = useLocale()
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
                {title || t('success.doc_preview_title')}
              </h2>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-full bg-white/5 text-zinc-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 bg-black/40 p-2 sm:p-4 flex items-center justify-center">
            <BlobPdfViewer
              url={previewUrl}
              title={title}
              className="w-full h-full rounded-2xl border border-white/5 bg-zinc-950 shadow-inner"
            />
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}

export default function SuccessPage() {
  const { t } = useLocale()
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
  const timestamp = useMemo(() => new Date().toLocaleString(), [])

  useEffect(() => {
    if (isSuccessDirect && stateSession) {
      setLoading(false)
      return
    }

    async function loadSignedDocument() {
      if (!token) {
        setError(t('errors.unauthorized'))
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
          setError(t('success.verification_failed'))
        }
      } catch (err) {
        setError(
          err?.response?.data?.detail ||
          t('errors.network_error')
        )
      } finally {
        setLoading(false)
      }
    }

    loadSignedDocument()
  }, [token, isSuccessDirect, stateSession, t])

  const role = session?.participant_role || 'signer'

  const pageContent = useMemo(() => {
    if (error) {
      const isTokenUsed = error.toLowerCase().includes('used')
      const isTokenExpired = error.toLowerCase().includes('expired')

      return {
        badge: isTokenUsed ? t('success.token_already_used') : isTokenExpired ? t('success.token_expired') : t('success.access_denied'),
        badgeColor: 'border-red-500/30 bg-red-500/10 text-red-400',
        iconColor: 'text-red-400 drop-shadow-[0_0_15px_rgba(239,68,68,0.5)]',
        pingColor: 'bg-red-500',
        isError: true,
        title: isTokenUsed ? t('success.token_already_used') : isTokenExpired ? t('success.token_expired') : t('success.verification_failed'),
        description: (
          <div className="space-y-2 mt-4 text-zinc-400">
            <p>{error}</p>
            {isTokenUsed && <p className="text-sm">{t('success.token_used_desc')}</p>}
            <p className="text-zinc-500 text-xs mt-6">{t('success.session_inactive')}</p>
          </div>
        ),
      }
    }

    if (role === 'approver') {
      if (successType === 'reject') {
        return {
          badge: t('success.document_rejected'),
          badgeColor: 'border-red-500/30 bg-red-500/10 text-red-400',
          iconColor: 'text-red-400 drop-shadow-[0_0_15px_rgba(239,68,68,0.5)]',
          pingColor: 'bg-red-500',
          isError: true,
          title: t('success.document_rejected'),
          description: (
            <div className="space-y-2 mt-4 text-zinc-400">
              <p>{t('success.document_rejected')}</p>
              <p>{t('success.workflow_stopped')}</p>
              <p className="text-zinc-500 text-xs mt-6">{t('success.may_close_window')}</p>
            </div>
          ),
        }
      }
      return {
        badge: t('success.approval_recorded'),
        badgeColor: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
        iconColor: 'text-emerald-400 drop-shadow-[0_0_15px_rgba(52,211,153,0.5)]',
        pingColor: 'bg-emerald-500',
        isError: false,
        title: t('success.approval_submitted'),
        description: (
          <div className="space-y-2 mt-4 text-zinc-400">
            <p>{t('success.approval_recorded')}</p>
            <p>{t('success.workflow_advanced')}</p>
            <p className="text-zinc-500 text-xs mt-6">{t('success.may_close_window')}</p>
          </div>
        ),
      }
    }

    if (role === 'reviewer') {
      if (successType === 'return') {
        return {
          badge: t('success.document_returned'),
          badgeColor: 'border-amber-500/30 bg-amber-500/10 text-amber-400',
          iconColor: 'text-amber-400 drop-shadow-[0_0_15px_rgba(245,158,11,0.5)]',
          pingColor: 'bg-amber-500',
          isError: false,
          title: t('success.document_returned'),
          description: (
            <div className="space-y-2 mt-4 text-zinc-400">
              <p>{t('success.document_returned')}</p>
              <p>{t('success.workflow_stopped')}</p>
              <p className="text-zinc-500 text-xs mt-6">{t('success.may_close_window')}</p>
            </div>
          ),
        }
      }
      return {
        badge: t('success.review_recorded'),
        badgeColor: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
        iconColor: 'text-emerald-400 drop-shadow-[0_0_15px_rgba(52,211,153,0.5)]',
        pingColor: 'bg-emerald-500',
        isError: false,
        title: t('success.review_completed'),
        description: (
          <div className="space-y-2 mt-4 text-zinc-400">
            <p>{t('success.review_recorded')}</p>
            <p>{t('success.workflow_advanced')}</p>
            <p className="text-zinc-500 text-xs mt-6">{t('success.may_close_window')}</p>
          </div>
        ),
      }
    }

    if (role === 'cc') {
      return {
        badge: t('success.receipt_acknowledged'),
        badgeColor: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
        iconColor: 'text-emerald-400 drop-shadow-[0_0_15px_rgba(52,211,153,0.5)]',
        pingColor: 'bg-emerald-500',
        isError: false,
        title: t('success.acknowledgment_logged'),
        description: (
          <div className="space-y-2 mt-4 text-zinc-400">
            <p>{t('success.receipt_acknowledged')}</p>
            <p>{t('success.workflow_advanced')}</p>
            <p className="text-zinc-500 text-xs mt-6">{t('success.may_close_window')}</p>
          </div>
        ),
      }
    }

    return {
      badge: t('success.document_signed'),
      badgeColor: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
      iconColor: 'text-emerald-400 drop-shadow-[0_0_15px_rgba(52,211,153,0.5)]',
      pingColor: 'bg-emerald-500',
      isError: false,
      title: t('success.document_signed'),
      description: (
        <div className="space-y-2 mt-4 text-zinc-400">
          <p>{t('success.signed_desc')}</p>
          <p className="text-zinc-500 text-xs mt-6">{t('success.download_hint')}</p>
        </div>
      ),
    }
  }, [role, successType, error, t])

  const IconComponent = pageContent.isError ? AlertCircle : CheckCircle2

  return (
    <div className="mx-auto flex min-h-dvh max-w-5xl flex-col px-4 py-10 sm:py-20 relative z-10 font-sans">
      <div className="mx-auto w-full max-w-3xl">

        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 text-emerald-500">
            <RefreshCw className="h-10 w-10 animate-spin" />
            <span className="mt-4 text-sm font-medium tracking-widest uppercase animate-pulse">{t('success.loading_signed_doc')}</span>
          </div>
        ) : session?.status === 'completed' && !pageContent.isError ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="max-w-2xl mx-auto glass-panel rounded-[2rem] p-8 sm:p-12 text-center relative overflow-hidden group shadow-2xl mt-6 border-emerald-500/30"
          >
            {/* Glow */}
            <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/10 via-transparent to-transparent opacity-60 pointer-events-none" />

            {/* Icon */}
            <div className="relative mb-6 flex justify-center">
              <div className="absolute inset-0 rounded-full bg-emerald-500/20 blur-xl animate-pulse w-20 h-20 mx-auto" />
              <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 shadow-[0_0_30px_rgba(16,185,129,0.2)]">
                <CheckCircle2 className="h-10 w-10" />
              </div>
            </div>

            <h1 className="text-3xl sm:text-4xl font-light text-white neon-text-glow tracking-tight">
              {t('success.document_signed')}
            </h1>
            <p className="mt-3 text-zinc-400 text-sm leading-relaxed max-w-md mx-auto">
              {t('success.signed_desc')}
            </p>

            {/* Verification Summary */}
            <div className="w-full mt-8 p-6 rounded-2xl border border-emerald-500/20 bg-emerald-500/5 text-left rtl:text-right space-y-4">
              <div className="flex items-center justify-between border-b border-emerald-500/20 pb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                  <ShieldCheck className="h-4 w-4" /> {t('success.summary_title')}
                </span>
                <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-[10px] font-bold uppercase text-emerald-400 tracking-wider">
                  {t('success.completed_badge')}
                </span>
              </div>

              <div className="space-y-3 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-zinc-400">{t('verification.email_verification')}</span>
                  <span className="font-semibold text-emerald-400">{t('success.status_verified')}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-zinc-400">{t('verification.national_id')}</span>
                  <span className="font-semibold text-emerald-400">{t('success.status_verified')}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-zinc-400">{t('verification.liveness_facial')}</span>
                  <span className="font-semibold text-emerald-400">{t('success.status_matched')}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-zinc-400">{t('verification.rep_auth')}</span>
                  <span className="font-semibold text-emerald-400">{t('success.status_authorized')}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-zinc-400">{t('verification.elec_sig')}</span>
                  <span className="font-semibold text-emerald-400">{t('success.status_applied')}</span>
                </div>
                {session?.signer_name && (
                  <div className="flex items-center justify-between">
                    <span className="text-zinc-400">{t('success.signer_name')}</span>
                    <span className="font-semibold text-white">
                      {session.signer_name}
                    </span>
                  </div>
                )}
                <div className="flex items-center justify-between pt-2 border-t border-emerald-500/20">
                  <span className="text-zinc-400 flex items-center gap-1">
                    <Clock className="h-3.5 w-3.5 text-accent" /> {t('success.completion_timestamp')}
                  </span>
                  <span className="font-mono text-zinc-300" dir="ltr">
                    {timestamp}
                  </span>
                </div>
              </div>
            </div>

            {/* Actions Section */}
            <div className="mt-8 space-y-3">
              <button
                onClick={() => setIsPreviewOpen(true)}
                className="flex w-full items-center justify-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 text-black px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] cursor-pointer"
              >
                <Eye className="h-4 w-4" /> {t('success.btn_view_signed')}
              </button>

              <a
                href={computedDownloadUrl}
                download
                className="flex w-full items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/[0.02] text-white hover:bg-white/10 px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 cursor-pointer"
              >
                <Download className="h-4 w-4" /> {t('success.btn_download_signed')}
              </a>

              <Link
                to="/"
                className="flex w-full items-center justify-center gap-2 rounded-2xl border border-white/5 bg-zinc-950 text-zinc-400 hover:text-white px-4 py-3.5 text-xs font-bold uppercase tracking-widest transition-all duration-300"
              >
                <Home className="h-4 w-4" /> {t('success.btn_return_dashboard')}
              </Link>
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
                      <div className="text-left rtl:text-right">
                        <h2 className="text-sm font-semibold tracking-wide text-white">{t('success.btn_view_signed')}</h2>
                        <p className="text-xs text-zinc-500 mt-0.5">{t('success.read_only_copy')}</p>
                      </div>
                    </div>

                    <a
                      href={computedPreviewUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500/10 text-emerald-400 text-sm font-medium hover:bg-emerald-500/20 transition-colors w-full sm:w-auto justify-center"
                    >
                      <ExternalLink className="h-4 w-4" /> {t('success.open_externally')}
                    </a>
                  </div>

                  <div className="p-2 sm:p-6 bg-black/40 flex items-center justify-center">
                    <BlobPdfViewer
                      title={t('success.btn_view_signed')}
                      url={computedPreviewUrl}
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
                        {t('success.download_file')}
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
                    {session.participant_role === 'cc' ? t('success.acknowledgment_logged') :
                      session.participant_role === 'reviewer' ? t('success.review_completed') :
                        session.participant_role === 'approver' ? t('success.approval_submitted') :
                          t('success.step_complete')}
                  </h3>
                  <p className="text-sm text-zinc-400 mb-6 max-w-md mx-auto">
                    {session.participant_role === 'cc' ? t('success.receipt_acknowledged') :
                      session.participant_role === 'reviewer' ? t('success.workflow_advanced') :
                        session.participant_role === 'approver' ? t('success.workflow_advanced') :
                          t('success.workflow_advanced')}
                  </p>
                  <div className="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    {t('common.role')}: {session.participant_role?.toUpperCase()}
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
        title={session?.title || t('success.doc_preview_title')}
      />
    </div>
  )
}