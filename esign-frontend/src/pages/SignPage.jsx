import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import SignatureCanvas from 'react-signature-canvas'
import { motion, AnimatePresence } from 'framer-motion'
import { PenTool, Type, Upload, FileSignature, ShieldCheck, CheckCircle2, AlertCircle, RefreshCw, ChevronRight, Download, X, User } from 'lucide-react'

import { apiClient, completeSigning, getSigningSession, API_URL } from '../services/api.js'

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

// ── Constants ──────────────────────────────────────────────────────────────────

const inputClass =
  'w-full rounded-2xl border border-white/10 bg-white/[0.02] px-4 py-3.5 text-sm text-zinc-100 placeholder:text-zinc-600 outline-none backdrop-blur-xl transition-all duration-300 focus:border-cyan-500/50 focus:bg-cyan-950/10 focus:ring-2 focus:ring-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-60'

const SIGNATURE_METHODS = [
  { id: 'typed', label: 'Keyboard', icon: Type },
  { id: 'upload', label: 'Upload', icon: Upload },
  { id: 'draw', label: 'Draw', icon: PenTool },
]

// ── Component ──────────────────────────────────────────────────────────────────

export default function SignPage() {
  const { token } = useParams()
  const navigate = useNavigate()

  const backendOrigin = useMemo(
    () => backendOriginFromBaseUrl(apiClient?.defaults?.baseURL),
    [],
  )

  // ── Existing state ────────────────────────────────────────────────────────
  const [isLoading, setIsLoading] = useState(true)
  const [isSigning, setIsSigning] = useState(false)
  const [error, setError] = useState('')
  const [session, setSession] = useState(null)
  const [typedSignature, setTypedSignature] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [signedDocumentUrl, setSignedDocumentUrl] = useState('')

  // ── Signature method ──────────────────────────────────────────────────────
  const [signatureMethod, setSignatureMethod] = useState('typed')

  // ── Draw mode state ───────────────────────────────────────────────────────
  const sigPadRef = useRef(null)
  const [isDrawEmpty, setIsDrawEmpty] = useState(true)

  // ── Upload mode state ─────────────────────────────────────────────────────
  // uploadFile: the raw File object; uploadPreview: base64 data-URL for <img>
  const [uploadFile, setUploadFile] = useState(null)
  const [uploadPreview, setUploadPreview] = useState('')

  const documentUrl = useMemo(() => {
    const url = session?.document_url
    return toAbsoluteUrl(url, backendOrigin)
  }, [session, backendOrigin])

  // ── Session loading (unchanged) ───────────────────────────────────────────
  async function loadSession() {
    setError('')
    setSuccessMessage('')
    setSignedDocumentUrl('')

    if (!token) {
      setSession(null)
      setIsLoading(false)
      setError('Missing token.')
      return
    }

    setIsLoading(true)
    try {
      const data = await getSigningSession(token)
      setSession(data)
      if (data?.status === 'completed') {
        setSignedDocumentUrl(toAbsoluteUrl(data?.document_url, backendOrigin))
      }
    } catch (err) {
      const message =
        err?.response?.data?.detail ||
        (typeof err?.response?.data === 'string' ? err.response.data : null) ||
        err?.message ||
        'Unable to load signing session.'
      setSession(null)
      setError(message)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional mount/token sync
    void loadSession()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  // ── Payload builder — validates each method and returns the correct shape ──
  function buildPayload() {
    switch (signatureMethod) {
      case 'typed': {
        if (!typedSignature.trim()) {
          setError('Please type your signature.')
          return null
        }
        return {
          signature_type: 'typed',
          signature_text: typedSignature,
        }
      }

      case 'upload': {
        if (!uploadPreview) {
          setError('Please upload a signature image before signing.')
          return null
        }
        return {
          signature_type: 'upload',
          signature_image: uploadPreview,
        }
      }

      case 'draw': {
        if (!sigPadRef.current || sigPadRef.current.isEmpty()) {
          setError('Please draw your signature before signing.')
          return null
        }
        return {
          signature_type: 'draw',
          // Export trimmed canvas as base64 PNG
          signature_image: sigPadRef.current.toDataURL('image/png'),
        }
      }

      default:
        setError('Unknown signature method.')
        return null
    }
  }

  // ── Unified sign handler ───────────────────────────────────────────────────
  async function handleSign() {
    setError('')
    setSuccessMessage('')
    setSignedDocumentUrl('')

    if (!token) return setError('Missing token.')

    const payload = buildPayload()
    if (!payload) return

    setIsSigning(true)
    try {
      const response = await completeSigning(token, payload)
      console.log(response)
      const signedUrl = response?.signed_document_url
      
      // Navigate with full state so SuccessPage doesn't call API on the used token
      navigate('/success', {
        state: {
          token,
          successType: 'sign',
          session: {
            ...session,
            participant_status: 'completed',
          },
          signedDocumentUrl: signedUrl || toAbsoluteUrl(session?.signed_document_url || session?.document_url, backendOrigin),
          isSuccessDirect: true,
        },
      })
    } catch (err) {
      const data = err?.response?.data
      const message =
        data?.detail ||
        (typeof data === 'string' ? data : null) ||
        err?.message ||
        'Signing failed.'
      setError(message)
      if (data?.status === 'completed' && data?.signed_document_url) {
        setSignedDocumentUrl(toAbsoluteUrl(data.signed_document_url, backendOrigin))
      }
    } finally {
      setIsSigning(false)
    }
  }

  // ── Reviewer / Approver actions ────────────────────────────────────────────
  async function handleAction(actionType) {
    setError('')
    setSuccessMessage('')

    if (!token) return setError('Missing token.')

    setIsSigning(true)
    try {
      const response = await completeSigning(token, { action: actionType })
      console.log(response)

      let newParticipantStatus = 'completed'
      if (actionType === 'return') newParticipantStatus = 'returned'
      if (actionType === 'reject') newParticipantStatus = 'declined'

      navigate('/success', {
        state: {
          token,
          successType: actionType,
          session: {
            ...session,
            participant_status: newParticipantStatus,
          },
          isSuccessDirect: true,
        },
      })
    } catch (err) {
      const data = err?.response?.data
      const message =
        data?.detail ||
        (typeof data === 'string' ? data : null) ||
        err?.message ||
        'Action failed.'
      setError(message)
    } finally {
      setIsSigning(false)
    }
  }

  // ── Draw canvas helpers ───────────────────────────────────────────────────
  function handleClearCanvas() {
    sigPadRef.current?.clear()
    setIsDrawEmpty(true)
  }

  function handleDrawEnd() {
    setIsDrawEmpty(sigPadRef.current?.isEmpty() ?? true)
  }

  // ── Upload helpers ────────────────────────────────────────────────────────
  function handleUploadChange(e) {
    const file = e.target.files?.[0]
    if (!file) return

    // Only accept PNG / JPG
    if (!['image/png', 'image/jpeg'].includes(file.type)) {
      setError('Only PNG and JPG files are accepted.')
      return
    }

    setError('')
    setUploadFile(file)

    const reader = new FileReader()
    reader.onload = (ev) => setUploadPreview(ev.target.result)
    reader.readAsDataURL(file)
  }

  function handleRemoveUpload() {
    setUploadFile(null)
    setUploadPreview('')
  }

  // ── Derived session state (unchanged) ─────────────────────────────────────
  const status = session?.status
  const isEnvelopeCompleted = status === 'completed'
  const isParticipantCompleted = session?.participant_status && ['completed', 'returned', 'declined'].includes(session.participant_status)
  const isCompleted = isEnvelopeCompleted || (session?.participant_role && isParticipantCompleted)
  const isActive = !!session && !isCompleted

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:py-20 relative z-10">
      
      {/* Header */}
      <motion.div 
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-10 text-center max-w-2xl mx-auto"
      >
        <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-medium uppercase tracking-widest text-cyan-400 mb-4 backdrop-blur-md">
          <ShieldCheck className="h-4 w-4" />
          Secure Signing Session
        </div>
        <h1 className="text-3xl sm:text-5xl font-light text-white neon-text-glow tracking-tight">
          Authorize Payload
        </h1>
        <p className="mt-3 text-zinc-400">Review the encrypted document and apply your cryptographic signature.</p>
      </motion.div>

      {/* Loading skeleton */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 text-cyan-500">
          <RefreshCw className="h-10 w-10 animate-spin" />
          <span className="mt-4 text-sm font-medium tracking-widest uppercase animate-pulse">Decrypting Session…</span>
        </div>
      ) : null}

      {/* Top-level error */}
      <AnimatePresence>
        {!isLoading && error ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="mb-8 flex items-center gap-3 rounded-2xl border border-red-500/30 bg-red-500/10 px-6 py-4 text-sm text-red-200 backdrop-blur-md shadow-[0_0_30px_rgba(239,68,68,0.1)]"
            role="alert"
          >
            <AlertCircle className="h-6 w-6 text-red-400 shrink-0" />
            <p className="font-medium text-base">{error}</p>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {/* Main content */}
      {!isLoading && session ? (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_400px] gap-8">
          
          {/* Left Column: Document */}
          <motion.div 
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            className="space-y-6"
          >
            {/* Session Metadata */}
            <div className="glass-panel rounded-3xl p-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
              <div className="flex items-center gap-4">
                <div className="h-12 w-12 rounded-2xl bg-cyan-500/20 flex items-center justify-center border border-cyan-500/30">
                  <span className="text-xl font-light text-cyan-300">
                    {session.signer_name?.charAt(0).toUpperCase() || 'U'}
                  </span>
                </div>
                <div>
                  <p className="text-sm font-medium text-white">{session.signer_name || 'Unknown User'}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-xs text-zinc-400">{session.signer_email || 'No email provided'}</span>
                    {session.participant_role && (
                      <span className="inline-flex px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider bg-zinc-800 text-zinc-300 border border-white/5">
                        {session.participant_role}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex flex-col items-start sm:items-end">
                <span className="text-[10px] uppercase tracking-widest text-zinc-500">Status</span>
                <span className={`text-sm font-medium uppercase tracking-wider ${isCompleted ? 'text-emerald-400' : 'text-cyan-400'}`}>
                  {session.status || 'Active'}
                </span>
              </div>
            </div>

            {/* Document Preview */}
            {documentUrl ? (
              <div className="glass-panel rounded-3xl overflow-hidden relative group">
                <div className="absolute inset-0 bg-gradient-to-b from-cyan-500/5 to-transparent opacity-50 pointer-events-none" />
                <div className="flex items-center justify-between border-b border-white/5 bg-white/[0.02] px-6 py-4">
                  <div className="flex items-center gap-2 text-zinc-300">
                    <FileSignature className="h-5 w-5 text-cyan-400" />
                    <h2 className="text-sm font-semibold tracking-wide">Document Viewport</h2>
                  </div>
                  <a
                    href={documentUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-2 text-xs font-medium text-cyan-400 hover:text-cyan-300 transition-colors bg-cyan-500/10 px-3 py-1.5 rounded-lg hover:bg-cyan-500/20"
                  >
                    External View <ChevronRight className="h-3 w-3" />
                  </a>
                </div>
                <div className="p-2 sm:p-4 bg-black/40">
                  <iframe
                    title="Document Preview"
                    src={documentUrl}
                    className="h-[min(600px,70vh)] w-full rounded-2xl border border-white/5 bg-zinc-950"
                  />
                </div>
              </div>
            ) : (
              <div className="glass-panel rounded-3xl p-8 text-center text-zinc-500">
                No document payload available for this session.
              </div>
            )}
          </motion.div>

          {/* Right Column: Signature Actions */}
          <motion.div 
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            className="space-y-6"
          >
            {isCompleted ? (
              <div className="glass-panel rounded-3xl p-8 text-center relative overflow-hidden group">
                <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/10 to-transparent opacity-50" />
                <CheckCircle2 className="h-16 w-16 text-emerald-400 mx-auto mb-4" />
                <h3 className="text-xl font-light text-emerald-300 mb-2">
                  {session?.participant_role === 'cc' ? 'Document Viewed' : 
                   session?.participant_role === 'reviewer' ? 'Review Completed' :
                   session?.participant_role === 'approver' ? 'Approval Completed' :
                   'Signature Verified'}
                </h3>
                <p className="text-sm text-zinc-400 mb-6">
                  {session?.participant_role === 'cc' ? 'You have successfully viewed this document.' :
                   session?.participant_role === 'reviewer' ? 'Your review action has been registered and advanced.' :
                   session?.participant_role === 'approver' ? 'Your approval action has been registered and advanced.' :
                   'This document has been cryptographically sealed.'}
                </p>
                {signedDocumentUrl && (
                  <a
                    href={signedDocumentUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center justify-center gap-2 w-full rounded-2xl bg-emerald-500/20 border border-emerald-500/30 px-4 py-3 text-sm font-semibold text-emerald-300 transition-all hover:bg-emerald-500/30"
                  >
                    <Download className="h-4 w-4" /> Access Sealed Payload
                  </a>
                )}
              </div>
            ) : session?.participant_role === 'cc' ? (
              <div className="glass-panel rounded-3xl p-8 text-center relative overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/10 to-transparent opacity-30" />
                <User className="h-16 w-16 text-cyan-400 mx-auto mb-4" />
                <h3 className="text-xl font-light text-cyan-300 mb-2">View-Only Access</h3>
                <p className="text-sm text-zinc-400 mb-6">
                  You are a CC recipient on this workflow step. You have view-only authorization, and no further action is required from you.
                </p>
                <button
                  onClick={() => handleAction('acknowledge')}
                  disabled={isSigning}
                  className="flex w-full items-center justify-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 text-black px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] disabled:opacity-50"
                >
                  {isSigning ? <RefreshCw className="h-4 w-4 animate-spin" /> : 'Acknowledge & Finish'}
                </button>
              </div>
            ) : session?.participant_role === 'reviewer' ? (
              <div className="glass-panel rounded-3xl p-6 sm:p-8 sticky top-8 space-y-6">
                <h3 className="text-lg font-light text-white mb-2 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                  Reviewer Decisions
                </h3>
                <p className="text-xs text-zinc-400">
                  Please review the document in the viewport and select an action.
                </p>

                <div className="space-y-4 pt-2">
                  <button
                    onClick={() => handleAction('approve')}
                    disabled={isSigning}
                    className="flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-500 hover:bg-emerald-400 text-black px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 shadow-[0_0_20px_rgba(16,185,129,0.2)] disabled:opacity-50"
                  >
                    {isSigning ? <RefreshCw className="h-4 w-4 animate-spin" /> : 'Approve Document'}
                  </button>
                  
                  <button
                    onClick={() => handleAction('return')}
                    disabled={isSigning}
                    className="flex w-full items-center justify-center gap-2 rounded-2xl border border-amber-500/30 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20 hover:shadow-[0_0_20px_rgba(245,158,11,0.1)] px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 disabled:opacity-50"
                  >
                    {isSigning ? <RefreshCw className="h-4 w-4 animate-spin" /> : 'Return Document'}
                  </button>
                </div>
              </div>
            ) : session?.participant_role === 'approver' ? (
              <div className="glass-panel rounded-3xl p-6 sm:p-8 sticky top-8 space-y-6">
                <h3 className="text-lg font-light text-white mb-2 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                  Approver Decisions
                </h3>
                <p className="text-xs text-zinc-400">
                  Please review the document in the viewport and select an action.
                </p>

                <div className="space-y-4 pt-2">
                  <button
                    onClick={() => handleAction('approve')}
                    disabled={isSigning}
                    className="flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-500 hover:bg-emerald-400 text-black px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 shadow-[0_0_20px_rgba(16,185,129,0.2)] disabled:opacity-50"
                  >
                    {isSigning ? <RefreshCw className="h-4 w-4 animate-spin" /> : 'Approve Document'}
                  </button>
                  
                  <button
                    onClick={() => handleAction('reject')}
                    disabled={isSigning}
                    className="flex w-full items-center justify-center gap-2 rounded-2xl border border-red-500/30 bg-red-500/10 text-red-300 hover:bg-red-500/20 hover:shadow-[0_0_20px_rgba(239,68,68,0.1)] px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 disabled:opacity-50"
                  >
                    {isSigning ? <RefreshCw className="h-4 w-4 animate-spin" /> : 'Reject Document'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="glass-panel rounded-3xl p-6 sm:p-8 sticky top-8">
                
                <h3 className="text-lg font-light text-white mb-6 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                  Input Signature
                </h3>

                {/* Signature Method Tabs */}
                <div className="flex gap-2 p-1 rounded-2xl bg-white/[0.02] border border-white/5 mb-8">
                  {SIGNATURE_METHODS.map(({ id, label, icon: Icon }) => (
                    <button
                      key={id}
                      onClick={() => setSignatureMethod(id)}
                      className={`relative flex-1 flex flex-col items-center justify-center gap-2 py-3 rounded-xl text-xs font-medium transition-all duration-300 ${
                        signatureMethod === id 
                          ? 'text-cyan-300 bg-cyan-500/10 shadow-[0_0_20px_rgba(34,211,238,0.1)]' 
                          : 'text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.02]'
                      }`}
                    >
                      {signatureMethod === id && (
                        <motion.div layoutId="activeTab" className="absolute inset-0 rounded-xl border border-cyan-500/30 pointer-events-none" />
                      )}
                      <Icon className="h-5 w-5" />
                      {label}
                    </button>
                  ))}
                </div>

                <AnimatePresence mode="wait">
                  {/* Typed */}
                  {signatureMethod === 'typed' && (
                    <motion.div 
                      key="typed"
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -10 }}
                      className="space-y-6"
                    >
                      <div>
                        <input
                          type="text"
                          value={typedSignature}
                          onChange={(e) => setTypedSignature(e.target.value)}
                          placeholder="Type your full name"
                          disabled={isSigning}
                          className={inputClass}
                        />
                      </div>
                    </motion.div>
                  )}

                  {/* Upload */}
                  {signatureMethod === 'upload' && (
                    <motion.div 
                      key="upload"
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -10 }}
                      className="space-y-6"
                    >
                      {!uploadPreview ? (
                        <label className="flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-white/10 bg-white/[0.02] p-8 cursor-pointer transition-all hover:border-cyan-500/30 hover:bg-cyan-950/10">
                          <Upload className="h-8 w-8 text-cyan-500/50" />
                          <div className="text-center">
                            <p className="text-sm text-zinc-300">Select Image File</p>
                            <p className="text-xs text-zinc-500 mt-1">PNG or JPG formats supported</p>
                          </div>
                          <input
                            type="file"
                            accept="image/png,image/jpeg"
                            onChange={handleUploadChange}
                            disabled={isSigning}
                            className="hidden"
                          />
                        </label>
                      ) : (
                        <div className="relative rounded-2xl border border-white/10 bg-black/50 p-4">
                          <img src={uploadPreview} alt="Signature preview" className="mx-auto max-h-32 object-contain" />
                          <button
                            onClick={handleRemoveUpload}
                            className="absolute top-2 right-2 p-1.5 rounded-full bg-red-500/20 text-red-400 hover:bg-red-500/40 transition-colors"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      )}
                    </motion.div>
                  )}

                  {/* Draw */}
                  {signatureMethod === 'draw' && (
                    <motion.div 
                      key="draw"
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -10 }}
                      className="space-y-4"
                    >
                      <div className="rounded-2xl border border-white/10 bg-white overflow-hidden shadow-inner relative">
                        <SignatureCanvas
                          ref={sigPadRef}
                          penColor="black"
                          minWidth={2}
                          maxWidth={3}
                          backgroundColor="white"
                          onEnd={handleDrawEnd}
                          canvasProps={{
                            className: 'w-full',
                            style: { height: '200px', display: 'block', touchAction: 'none' },
                          }}
                        />
                      </div>
                      <div className="flex justify-between items-center px-1">
                        <span className="text-xs text-zinc-500">Trace within the bounds</span>
                        <button
                          onClick={handleClearCanvas}
                          disabled={isSigning || isDrawEmpty}
                          className="text-xs font-medium text-zinc-400 hover:text-zinc-200 disabled:opacity-50"
                        >
                          Clear Traces
                        </button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={handleSign}
                  disabled={isSigning}
                  className="group relative mt-8 flex w-full items-center justify-center gap-2 overflow-hidden rounded-2xl bg-cyan-500 px-4 py-4 text-sm font-bold text-black transition-all hover:bg-cyan-400 hover:shadow-[0_0_30px_rgba(34,211,238,0.4)] disabled:cursor-not-allowed disabled:opacity-50 uppercase tracking-widest"
                >
                  <span className="relative z-10 flex items-center gap-2">
                    {isSigning ? (
                      <>
                        <RefreshCw className="h-4 w-4 animate-spin" />
                        Committing...
                      </>
                    ) : (
                      <>
                        Commit Signature
                      </>
                    )}
                  </span>
                  <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/40 to-transparent group-hover:animate-[shimmer_1.5s_infinite]" />
                </motion.button>
                
                {successMessage && (
                  <div className="mt-4 text-center text-sm font-medium text-emerald-400">
                    {successMessage}
                  </div>
                )}
              </div>
            )}
          </motion.div>
        </div>
      ) : null}
    </div>
  )
}
