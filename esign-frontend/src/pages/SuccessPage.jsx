import { useEffect, useState, useMemo } from 'react'
import { useLocation } from 'react-router-dom'
import { getSigningSession } from '../services/api'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle2, FileSignature, ExternalLink, RefreshCw, Download, ShieldCheck, AlertCircle } from 'lucide-react'

export default function SuccessPage() {
  const location = useLocation()

  const token = location.state?.token
  const isSuccessDirect = location.state?.isSuccessDirect
  const stateSession = location.state?.session
  const successType = location.state?.successType
  const stateSignedDocumentUrl = location.state?.signedDocumentUrl

  const [signedDocumentUrl, setSignedDocumentUrl] = useState(stateSignedDocumentUrl || '')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(!isSuccessDirect)
  const [session, setSession] = useState(stateSession || null)

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
        } else if (data?.participant_role && ['completed', 'returned', 'declined', 'viewed'].includes(data.participant_status)) {
          setSignedDocumentUrl('')
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
    <div className="mx-auto flex min-h-dvh max-w-5xl flex-col px-4 py-10 sm:py-20 relative z-10">
      <div className="mx-auto w-full max-w-3xl">
        
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 text-emerald-500">
            <RefreshCw className="h-10 w-10 animate-spin" />
            <span className="mt-4 text-sm font-medium tracking-widest uppercase animate-pulse">Retrieving Sealed Payload…</span>
          </div>
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
                      href={signedDocumentUrl}
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
                      src={signedDocumentUrl}
                      className="h-[min(600px,70vh)] w-full rounded-2xl border border-white/5 bg-zinc-950 shadow-inner"
                    />
                  </div>

                  <div className="border-t border-white/5 px-6 py-5 bg-white/[0.01]">
                    <a
                      href={signedDocumentUrl}
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
    </div>
  )
}