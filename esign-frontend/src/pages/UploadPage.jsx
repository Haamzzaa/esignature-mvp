import { useMemo, useState } from 'react'
import { createEnvelope, sendEnvelope, uploadDocument } from '../services/api.js'
import { Document, Page, pdfjs } from 'react-pdf'
import { motion, AnimatePresence } from 'framer-motion'
import { UploadCloud, User, Mail, FileText, X, ArrowRight, CheckCircle2, Sparkles, Crosshair } from 'lucide-react'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'

// ── Configure pdf.js worker (must live in the same module as <Document>) ──────
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

// ── Style constants ───────────────────────────────────────────────
const inputClass =
  'w-full rounded-2xl border border-white/10 bg-white/[0.02] px-4 py-3.5 pl-11 text-sm text-zinc-100 placeholder:text-zinc-600 outline-none backdrop-blur-xl transition-all duration-300 focus:border-cyan-500/50 focus:bg-cyan-950/10 focus:ring-2 focus:ring-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-60'

export default function UploadPage() {
  // ── Form / workflow state (unchanged) ─────────────────────────────────────
  const [file, setFile] = useState(null)
  const [signerName, setSignerName] = useState('')
  const [signerEmail, setSignerEmail] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [signingUrl, setSigningUrl] = useState('')

  // ── Signature position — page-aware ──────────────────────────────────────
  const [sigPosition, setSigPosition] = useState(null)

  // ── react-pdf state ───────────────────────────────────────────────────────
  const [numPages, setNumPages] = useState(null)

  // ── Object-URL for the selected PDF ──────────────────────────────────────
  const previewUrl = useMemo(() => {
    if (!file || file.type !== 'application/pdf') return null
    return URL.createObjectURL(file)
  }, [file])

  const isPdf = useMemo(() => {
    if (!file) return true
    const byType = file.type === 'application/pdf'
    const byName = file.name?.toLowerCase().endsWith('.pdf')
    return byType || byName
  }, [file])

  // ── Submit handler (unchanged) ────────────────────────────────────────────
  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSigningUrl('')

    if (!file) return setError('Please choose a PDF file.')
    if (!isPdf) return setError('Only PDF files are supported.')
    if (!signerName.trim()) return setError('Signer name is required.')
    if (!signerEmail.trim()) return setError('Signer email is required.')
    if (!sigPosition || !sigPosition.page || sigPosition.x_ratio == null || sigPosition.y_ratio == null) {
      return setError('Please select a signature position before generating the signing link.')
    }

    setIsSubmitting(true)
    try {
      const uploadRes = await uploadDocument(file)
      const documentId = uploadRes?.document_id
      if (!documentId) throw new Error('Upload succeeded but no document_id returned.')

      const envelopeRes = await createEnvelope({
        documentId,
        signer: { name: signerName.trim(), email: signerEmail.trim() },
        signaturePosition: sigPosition,
      })
      const envelopeId = envelopeRes?.envelope_id
      if (!envelopeId) throw new Error('Envelope created but no envelope_id returned.')

      const sendRes = await sendEnvelope(envelopeId)
      const url = sendRes?.signing_url
      if (!url) throw new Error('Envelope sent but no signing_url returned.')

      setSigningUrl(url)
    } catch (err) {
      const message =
        err?.response?.data?.detail ||
        (typeof err?.response?.data === 'string' ? err.response.data : null) ||
        err?.message ||
        'Something went wrong. Please try again.'
      setError(message)
    } finally {
      setIsSubmitting(false)
    }
  }

  // ── Per-page click handler ────────────────────────────────────────────────
  function handlePageClick(pageNumber, e) {
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    setSigPosition({
      page: pageNumber,
      x,
      y,
      x_ratio: x / rect.width,
      y_ratio: y / rect.height,
    })
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-12 sm:py-20 relative z-10">

      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
      >
        {/* ── Upload / signer form card ── */}
        <div className="glass-panel rounded-[2rem] p-8 sm:p-12 relative overflow-hidden group">
          {/* Subtle gradient glow behind the card content */}
          <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/5 via-transparent to-violet-500/5 opacity-50 pointer-events-none group-hover:opacity-100 transition-opacity duration-700" />

          <div className="relative z-10 mb-10 space-y-3">
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-medium uppercase tracking-widest text-cyan-400 backdrop-blur-md">
              <Sparkles className="h-3.5 w-3.5" />
              E-Sign Demo
            </div>
            <h1 className="text-3xl font-light tracking-tight text-white sm:text-5xl neon-text-glow">
              Initialize Document
            </h1>
            <p className="text-sm font-medium text-zinc-400 sm:text-base">
              Securely upload a PDF to generate an encrypted signing link.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="relative z-10 space-y-6">

            {/* Custom File Upload Area */}
            <div className="space-y-2">
              <label className="block text-sm font-medium text-zinc-300">
                Encrypted Payload (PDF)
              </label>
              <div className="relative group/upload">
                <input
                  id="pdf-upload"
                  type="file"
                  accept="application/pdf,.pdf"
                  onChange={(e) => {
                    setSigPosition(null)
                    setNumPages(null)
                    setFile(e.target.files?.[0] ?? null)
                  }}
                  disabled={isSubmitting}
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed z-20"
                />
                <div className={`flex flex-col items-center justify-center rounded-2xl border-2 border-dashed transition-all duration-300 p-8 sm:p-10 ${file ? 'border-cyan-500/50 bg-cyan-950/10' : 'border-white/10 bg-white/[0.02] group-hover/upload:border-cyan-500/30 group-hover/upload:bg-white/[0.04]'}`}>
                  <motion.div
                    animate={file ? { y: 0, scale: 1 } : { y: [0, -5, 0] }}
                    transition={file ? {} : { repeat: Infinity, duration: 3, ease: "easeInOut" }}
                    className={`mb-4 rounded-full p-4 ${file ? 'bg-cyan-500/20 text-cyan-400' : 'bg-white/5 text-zinc-400 group-hover/upload:text-cyan-400 group-hover/upload:bg-cyan-500/10 transition-colors'}`}
                  >
                    {file ? <FileText className="h-8 w-8" /> : <UploadCloud className="h-8 w-8" />}
                  </motion.div>
                  {file ? (
                    <div className="text-center">
                      <p className="text-sm font-medium text-cyan-300">{file.name}</p>
                      <p className="mt-1 text-xs text-cyan-500/70">Ready for processing</p>
                    </div>
                  ) : (
                    <div className="text-center">
                      <p className="text-sm font-medium text-zinc-300">Drag & drop or click to browse</p>
                      <p className="mt-1 text-xs text-zinc-500">Only PDF files are supported</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <div className="space-y-2 relative">
                <label className="block text-sm font-medium text-zinc-300" htmlFor="signer-name">
                  Signer Identity
                </label>
                <div className="relative">
                  <User className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
                  <input
                    id="signer-name"
                    type="text"
                    value={signerName}
                    onChange={(e) => setSignerName(e.target.value)}
                    placeholder="Enter full name"
                    autoComplete="name"
                    disabled={isSubmitting}
                    className={inputClass}
                  />
                </div>
              </div>

              <div className="space-y-2 relative">
                <label className="block text-sm font-medium text-zinc-300" htmlFor="signer-email">
                  Signer Address
                </label>
                <div className="relative">
                  <Mail className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
                  <input
                    id="signer-email"
                    type="email"
                    value={signerEmail}
                    onChange={(e) => setSignerEmail(e.target.value)}
                    placeholder="Enter email address"
                    autoComplete="email"
                    disabled={isSubmitting}
                    className={inputClass}
                  />
                </div>
              </div>
            </div>

            <motion.button
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
              type="submit"
              disabled={isSubmitting}
              className="group relative mt-4 flex w-full items-center justify-center gap-2 overflow-hidden rounded-2xl bg-cyan-500 px-4 py-3.5 text-sm font-semibold text-black transition-all hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className="relative z-10 flex items-center gap-2">
                {isSubmitting ? 'Initializing Sequence…' : 'Generate Secure Link'}
                {!isSubmitting && <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />}
              </span>
              <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/40 to-transparent group-hover:animate-[shimmer_1.5s_infinite]" />
            </motion.button>
          </form>

          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, height: 0, marginTop: 0 }}
                animate={{ opacity: 1, height: 'auto', marginTop: 24 }}
                exit={{ opacity: 0, height: 0, marginTop: 0 }}
                className="overflow-hidden"
              >
                <div className="flex items-center gap-3 rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200 backdrop-blur-md" role="alert">
                  <X className="h-5 w-5 shrink-0 text-red-400" />
                  <p>{error}</p>
                </div>
              </motion.div>
            )}

            {signingUrl && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="mt-8 rounded-2xl border border-cyan-500/30 bg-cyan-950/20 p-5 backdrop-blur-xl"
              >
                <div className="flex items-center gap-2 mb-3">
                  <CheckCircle2 className="h-5 w-5 text-cyan-400" />
                  <span className="text-xs font-semibold uppercase tracking-wider text-cyan-400">Secure Link Generated</span>
                </div>
                <div className="flex items-center gap-3 rounded-xl bg-black/40 px-4 py-3">
                  <a
                    href={signingUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="flex-1 truncate text-sm font-medium text-white transition-colors hover:text-cyan-300"
                  >
                    {signingUrl}
                  </a>
                  <a
                    href={signingUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded-lg bg-cyan-500/20 p-2 text-cyan-400 transition-colors hover:bg-cyan-500/40"
                  >
                    <ArrowRight className="h-4 w-4" />
                  </a>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>

      {/* ── Signature position selector ── */}
      <AnimatePresence>
        {previewUrl && (
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 40 }}
            transition={{ duration: 0.6, delay: 0.1, ease: "easeOut" }}
            className="mt-8 glass-panel rounded-[2rem] p-8 sm:p-12"
          >
            <div className="mb-8 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <div className="inline-flex items-center gap-2 rounded-full border border-violet-500/30 bg-violet-500/10 px-3 py-1 text-xs font-medium uppercase tracking-widest text-violet-400 mb-3">
                  <Crosshair className="h-3.5 w-3.5" />
                  Spatial Placement
                </div>
                <h2 className="text-2xl font-light text-white">Target Signature Zone</h2>
                <p className="mt-1 text-sm text-zinc-400">Scan document and click to set spatial coordinates.</p>
              </div>

              {/* Coordinate readout */}
              {sigPosition && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="flex items-center gap-3 rounded-2xl border border-cyan-500/30 bg-cyan-950/20 px-4 py-2 backdrop-blur-md"
                >
                  <div className="flex gap-4 text-xs font-mono text-cyan-300">
                    <div><span className="text-cyan-600">P:</span>{sigPosition.page}</div>
                    <div><span className="text-cyan-600">X:</span>{sigPosition.x_ratio.toFixed(2)}</div>
                    <div><span className="text-cyan-600">Y:</span>{sigPosition.y_ratio.toFixed(2)}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSigPosition(null)}
                    className="ml-2 rounded-full bg-cyan-500/20 p-1 text-cyan-400 hover:bg-cyan-500/40 transition-colors"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </motion.div>
              )}
            </div>

            <div className="relative overflow-auto rounded-2xl border border-white/10 bg-black/50 py-8 custom-scrollbar shadow-inner max-h-[700px]">
              <Document
                file={previewUrl}
                onLoadSuccess={({ numPages: n }) => setNumPages(n)}
                loading={
                  <div className="flex h-64 flex-col items-center justify-center gap-4 text-cyan-500">
                    <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-500 border-t-transparent" />
                    <span className="text-sm font-medium animate-pulse tracking-widest uppercase">Rendering Data…</span>
                  </div>
                }
                error={
                  <div className="flex h-64 items-center justify-center text-sm text-red-400">
                    Failed to decode document.
                  </div>
                }
              >
                {numPages
                  ? Array.from({ length: numPages }, (_, i) => {
                    const pageNumber = i + 1
                    const isSelected = sigPosition?.page === pageNumber

                    return (
                      <div
                        key={pageNumber}
                        className="relative mx-auto mb-8 w-fit cursor-crosshair shadow-[0_0_50px_rgba(0,0,0,0.8)] last:mb-0 transition-transform hover:scale-[1.01] duration-500"
                        style={{ userSelect: 'none' }}
                        onClick={(e) => handlePageClick(pageNumber, e)}
                      >
                        {/* Glowing border if selected */}
                        {isSelected && (
                          <div className="absolute inset-0 border-2 border-cyan-500 shadow-[0_0_30px_rgba(34,211,238,0.3)] z-0 pointer-events-none" />
                        )}

                        <div className="absolute left-4 top-4 z-10 rounded-lg border border-white/10 bg-black/60 px-3 py-1.5 text-xs font-mono text-zinc-400 backdrop-blur-md">
                          {pageNumber} / {numPages}
                        </div>

                        <Page
                          pageNumber={pageNumber}
                          renderTextLayer={true}
                          renderAnnotationLayer={true}
                          className="block relative z-0"
                        />

                        {/* "Sign Here" marker */}
                        <AnimatePresence>
                          {isSelected && (
                            <motion.div
                              initial={{ scale: 0, opacity: 0 }}
                              animate={{ scale: 1, opacity: 1 }}
                              exit={{ scale: 0, opacity: 0 }}
                              id="sig-position-marker"
                              style={{
                                position: 'absolute',
                                left: sigPosition.x,
                                top: sigPosition.y,
                                pointerEvents: 'none',
                                zIndex: 20,
                              }}
                            >
                              {/* The glowing point is the center anchor */}
                              <div className="absolute left-0 top-0 -translate-x-1/2 -translate-y-1/2 flex items-center justify-center">
                                <div className="relative flex h-5 w-5 items-center justify-center">
                                  <div className="absolute inset-0 rounded-full bg-cyan-500 animate-ping opacity-50" />
                                  <div className="relative h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_10px_#22d3ee]" />
                                </div>
                              </div>

                              {/* Label sits cleanly below the point */}
                              <div className="absolute left-0 top-3 -translate-x-1/2 pt-1">
                                <div className="whitespace-nowrap rounded-lg border border-cyan-500/50 bg-cyan-950/80 px-3 py-1 text-[10px] font-bold tracking-widest text-cyan-300 shadow-[0_0_20px_rgba(34,211,238,0.4)] backdrop-blur-md uppercase">
                                  Sign Here
                                </div>
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    )
                  })
                  : null}
              </Document>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
