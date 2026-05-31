import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { getSigningSession } from '../services/api'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle2, FileSignature, ExternalLink, RefreshCw, Download, ShieldCheck } from 'lucide-react'

export default function SuccessPage() {
  const location = useLocation()

  const token = location.state?.token

  const [signedDocumentUrl, setSignedDocumentUrl] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function loadSignedDocument() {
      if (!token) {
        setError('Missing access token.')
        setLoading(false)
        return
      }

      try {
        const data = await getSigningSession(token)

        if (data?.status === 'completed' && data?.signed_document_url) {
          setSignedDocumentUrl(data.signed_document_url)
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
  }, [token])

  return (
    <div className="mx-auto flex min-h-dvh max-w-5xl flex-col px-4 py-10 sm:py-20 relative z-10">
      <div className="mx-auto w-full max-w-3xl">
        
        <motion.div 
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-12 text-center"
        >
          <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-medium uppercase tracking-widest text-emerald-400 mb-6 backdrop-blur-md">
            <ShieldCheck className="h-4 w-4" />
            Cryptographic Seal Verified
          </div>

          <div className="relative w-24 h-24 mx-auto mb-6">
            <div className="absolute inset-0 rounded-full bg-emerald-500 animate-ping opacity-20" />
            <div className="absolute inset-0 rounded-full bg-emerald-500/10 blur-xl" />
            <CheckCircle2 className="relative z-10 w-full h-full text-emerald-400 drop-shadow-[0_0_15px_rgba(52,211,153,0.5)]" />
          </div>

          <h1 className="text-3xl sm:text-5xl font-light tracking-tight text-white neon-text-glow">
            Transaction Complete
          </h1>

          <p className="mt-4 text-zinc-400">
            The document payload has been successfully signed and encrypted.
          </p>
        </motion.div>

        <AnimatePresence mode="wait">
          {loading ? (
            <motion.div 
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center justify-center py-10 text-emerald-500"
            >
              <RefreshCw className="h-10 w-10 animate-spin" />
              <span className="mt-4 text-sm font-medium tracking-widest uppercase animate-pulse">Retrieving Sealed Payload…</span>
            </motion.div>
          ) : error ? (
            <motion.div 
              key="error"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="rounded-2xl border border-red-500/30 bg-red-500/10 px-6 py-8 text-center text-red-200 backdrop-blur-md"
            >
              {error}
            </motion.div>
          ) : signedDocumentUrl ? (
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
          ) : null}
        </AnimatePresence>
      </div>
    </div>
  )
}