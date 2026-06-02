import { useEffect, useMemo, useRef, useState } from 'react'
import { createEnvelope, sendEnvelope, uploadDocument } from '../services/api.js'
import { Document, Page, pdfjs } from 'react-pdf'
import { motion, AnimatePresence } from 'framer-motion'
import { UploadCloud, User, Mail, FileText, X, ArrowRight, CheckCircle2, Sparkles, Crosshair, Plus, Trash2, Edit3, UserPlus, Check, ChevronDown, Sparkles as SparkleIcon, Bell, Share2, Printer, Settings } from 'lucide-react'
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

const selectClass =
  'w-full rounded-2xl border border-white/10 bg-black/40 px-4 py-3.5 text-sm text-zinc-100 placeholder:text-zinc-600 outline-none backdrop-blur-xl transition-all duration-300 focus:border-cyan-500/50 focus:bg-cyan-950/10 focus:ring-2 focus:ring-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-60'

const cellInputClass =
  'w-full bg-white/[0.01] border border-white/5 rounded-xl px-3 py-2.5 text-sm text-zinc-100 placeholder:text-zinc-600 outline-none transition-all duration-200 focus:border-cyan-500/30 focus:bg-cyan-950/5 focus:ring-1 focus:ring-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-60'

function CustomSelect({ value, onChange, options, disabled }) {
  const [isOpen, setIsOpen] = useState(false)
  const selectRef = useRef(null)

  useEffect(() => {
    function handleClickOutside(event) {
      if (selectRef.current && !selectRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
    }
  }, [])

  const selectedOption = options.find(opt => opt.value === value)

  return (
    <div className={`relative w-full ${isOpen ? 'z-50' : 'z-10'}`} ref={selectRef}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen(!isOpen)}
        className="w-full rounded-2xl border border-white/10 bg-[#050505]/60 px-4 py-3.5 text-sm text-zinc-100 text-left outline-none backdrop-blur-xl transition-all duration-300 focus:border-cyan-500/50 focus:bg-cyan-950/10 focus:ring-2 focus:ring-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-60 flex items-center justify-between cursor-pointer"
      >
        <span className="truncate">{selectedOption ? selectedOption.label : 'Select role'}</span>
        <ChevronDown className={`h-4 w-4 text-zinc-500 transition-transform duration-300 ${isOpen ? 'rotate-180 text-cyan-400' : ''}`} />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="absolute mt-2 w-full z-[100] rounded-2xl border border-white/10 bg-[#0B1220] overflow-hidden shadow-[0_25px_60px_rgba(0,0,0,0.95),0_0_30px_rgba(34,211,238,0.2)] p-2"
          >
            <div className="max-h-60 overflow-y-auto custom-scrollbar space-y-1">
              {options.map((opt) => {
                const isSelected = opt.value === value
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => {
                      onChange(opt.value)
                      setIsOpen(false)
                    }}
                    className={`w-full text-left px-4 py-3 rounded-xl text-sm transition-all duration-200 flex items-center justify-between cursor-pointer ${
                      isSelected 
                        ? 'bg-cyan-500 text-black font-semibold border border-cyan-400 shadow-[0_0_15px_rgba(34,211,238,0.25)]' 
                        : 'text-white hover:bg-cyan-500 hover:text-black border border-transparent'
                    }`}
                  >
                    <span className="font-medium">{opt.label}</span>
                    {isSelected && <Check className="h-4 w-4 text-black shrink-0" />}
                  </button>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function UploadPage() {
  // ── Form / workflow state ─────────────────────────────────────
  const [file, setFile] = useState(null)
  const [steps, setSteps] = useState([
    {
      stepNumber: 1,
      participants: [{ id: '1', name: '', email: '', role: 'signer' }]
    }
  ])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [signingUrl, setSigningUrl] = useState('')
  const [currentTab, setCurrentTab] = useState('documents')
  const [uploadTimestamp, setUploadTimestamp] = useState(null)

  // ── Request settings state ───────────────────────────────────────────
  const [sendReminders, setSendReminders] = useState(false)
  const [sendFinalEmail, setSendFinalEmail] = useState(true)
  const [allowPrinting, setAllowPrinting] = useState(true)
  const [additionalRecipients, setAdditionalRecipients] = useState([])
  const [newRecipientEmail, setNewRecipientEmail] = useState('')
  const [recipientEmailError, setRecipientEmailError] = useState('')

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

  // ── Preflight derived states ──────────────────────────────────────────────
  const isDocumentValid = useMemo(() => {
    return !!file && isPdf
  }, [file, isPdf])

  const isWorkflowValid = useMemo(() => {
    const allParticipants = steps.flatMap(s => s.participants)
    if (steps.length === 0 || allParticipants.length === 0) return false
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    return allParticipants.every(p => p.name?.trim() && p.email?.trim() && emailRegex.test(p.email.trim()))
  }, [steps])

  const hasSignerRole = useMemo(() => {
    return steps.flatMap(s => s.participants).some(p => p.role === 'signer')
  }, [steps])

  const isSignaturePlaced = useMemo(() => {
    return !!sigPosition && !!sigPosition.page && sigPosition.x_ratio != null && sigPosition.y_ratio != null
  }, [sigPosition])

  // ── Participant / Step Actions ───────────────────────────────────────────
  const addStep = () => {
    const nextStepNum = steps.length + 1
    const newStep = {
      stepNumber: nextStepNum,
      participants: [
        { id: crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(), name: '', email: '', role: 'signer' }
      ]
    }
    setSteps(prev => [...prev, newStep])
  }

  const removeStep = (stepNumber) => {
    setSteps(prev => {
      const filtered = prev.filter(s => s.stepNumber !== stepNumber)
      return filtered.map((s, idx) => ({
        ...s,
        stepNumber: idx + 1
      }))
    })
  }

  const addParticipantToStep = (stepNumber) => {
    setSteps(prev =>
      prev.map(s => {
        if (s.stepNumber === stepNumber) {
          return {
            ...s,
            participants: [
              ...s.participants,
              { id: crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(), name: '', email: '', role: 'signer' }
            ]
          }
        }
        return s;
      })
    )
  }

  const removeParticipant = (stepNumber, participantId) => {
    setSteps(prev =>
      prev.map(s => {
        if (s.stepNumber === stepNumber) {
          const filtered = s.participants.filter(p => p.id !== participantId)
          return {
            ...s,
            participants: filtered
          }
        }
        return s;
      }).filter(s => s.participants.length > 0)
    )
  }

  const updateParticipant = (stepNumber, participantId, field, value) => {
    setSteps(prev =>
      prev.map(s => {
        if (s.stepNumber === stepNumber) {
          return {
            ...s,
            participants: s.participants.map(p =>
              p.id === participantId ? { ...p, [field]: value } : p
            )
          }
        }
        return s;
      })
    )
  }

  const moveStep = (stepNumber, direction) => {
    const index = steps.findIndex(s => s.stepNumber === stepNumber)
    if (index === -1) return
    const newIndex = direction === 'up' ? index - 1 : index + 1
    if (newIndex < 0 || newIndex >= steps.length) return

    setSteps(prev => {
      const updated = [...prev]
      const temp = updated[index]
      updated[index] = updated[newIndex]
      updated[newIndex] = temp
      return updated.map((s, idx) => ({
        ...s,
        stepNumber: idx + 1
      }))
    })
  }

  // ── Additional Recipients helpers ───────────────────────────────────────────
  const addRecipientEmail = () => {
    setRecipientEmailError('')
    const email = newRecipientEmail.trim()
    if (!email) return

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(email)) {
      setRecipientEmailError('Please enter a valid email address.')
      return
    }

    if (additionalRecipients.includes(email)) {
      setRecipientEmailError('This email has already been added.')
      return
    }

    setAdditionalRecipients(prev => [...prev, email])
    setNewRecipientEmail('')
  }

  const removeRecipientEmail = (email) => {
    setAdditionalRecipients(prev => prev.filter(e => e !== email))
  }

  // ── Submit handler ────────────────────────────────────────────
  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSigningUrl('')

    if (!file) return setError('Please choose a PDF file.')
    if (!isPdf) return setError('Only PDF files are supported.')

    // VALIDATION
    if (steps.length === 0) {
      return setError('At least one step is required to create a workflow.')
    }
    const allParticipants = steps.flatMap(s => s.participants)
    if (allParticipants.length === 0) {
      return setError('At least one participant is required to create a package.')
    }
    const hasEmptyField = allParticipants.some(p => !p.name.trim() || !p.email.trim())
    if (hasEmptyField) {
      return setError('Please enter a name and email address for all participants.')
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    const hasInvalidEmail = allParticipants.some(p => !emailRegex.test(p.email.trim()))
    if (hasInvalidEmail) {
      return setError('Please enter a valid email address for all participants.')
    }
    const hasSigner = allParticipants.some(p => p.role === 'signer')
    if (!hasSigner) {
      return setError('At least one participant must be assigned the "Signer" role.')
    }

    if (!sigPosition || !sigPosition.page || sigPosition.x_ratio == null || sigPosition.y_ratio == null) {
      return setError('Please select a signature position before generating the signing link.')
    }

    setIsSubmitting(true)
    try {
      const uploadRes = await uploadDocument(file)
      const documentId = uploadRes?.document_id
      if (!documentId) throw new Error('Upload succeeded but no document_id returned.')

      const preparedParticipants = []
      let globalOrder = 1
      steps.forEach(step => {
        step.participants.forEach(p => {
          preparedParticipants.push({
            name: p.name.trim(),
            email: p.email.trim(),
            role: p.role,
            step_number: step.stepNumber,
            order: globalOrder++
          })
        })
      })

      const envelopeRes = await createEnvelope({
        documentId,
        participants: preparedParticipants,
        signaturePosition: sigPosition,
        send_reminders: sendReminders,
        send_final_email: sendFinalEmail,
        allow_printing: allowPrinting,
        additional_recipients: additionalRecipients,
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

          {/* Stepper Header */}
          <div className="relative z-10 mb-12 border-b border-white/5 pb-8">
            <div className="relative flex flex-col md:flex-row items-stretch justify-between w-full gap-4 md:gap-2">
              {[
                { id: 'documents', label: '1. Documents', desc: 'Upload PDF payload' },
                { id: 'workflow', label: '2. Workflow', desc: 'Configure recipients' },
                { id: 'settings', label: '3. Settings', desc: 'Reminders & permissions' },
                { id: 'review', label: '4. Review & Prepare', desc: 'Preflight checklist' }
              ].map((tab, idx) => {
                const isCompleted = 
                  tab.id === 'documents' ? isDocumentValid :
                  tab.id === 'workflow' ? (isWorkflowValid && hasSignerRole) :
                  tab.id === 'settings' ? true : // optional/always completed
                  (isDocumentValid && isWorkflowValid && hasSignerRole && isSignaturePlaced);
                
                const isActive = currentTab === tab.id;
                
                const isClickable = 
                  tab.id === 'documents' ? true :
                  tab.id === 'workflow' ? isDocumentValid :
                  tab.id === 'settings' ? (isDocumentValid && isWorkflowValid && hasSignerRole) :
                  (isDocumentValid && isWorkflowValid && hasSignerRole);

                return (
                  <button
                    key={tab.id}
                    type="button"
                    disabled={!isClickable || isSubmitting}
                    onClick={() => {
                      setCurrentTab(tab.id);
                      setError('');
                    }}
                    className={`flex-1 text-left rounded-2xl p-4 border transition-all duration-300 relative overflow-hidden group ${
                      isActive 
                        ? 'bg-cyan-500/10 border-cyan-500/50 shadow-[0_0_20px_rgba(34,211,238,0.15)]'
                        : isCompleted
                          ? 'bg-emerald-500/5 border-emerald-500/30 hover:border-emerald-500/60'
                          : 'bg-white/[0.01] border-white/5 hover:border-white/10'
                    } disabled:opacity-50 disabled:cursor-not-allowed`}
                  >
                    {/* Tiny side accent color bar */}
                    <div className={`absolute left-0 top-0 bottom-0 w-1 transition-all ${
                      isActive ? 'bg-cyan-400' : isCompleted ? 'bg-emerald-400' : 'bg-transparent'
                    }`} />
                    
                    <div className="flex items-center justify-between mb-1.5 pl-1.5">
                      <span className={`text-xs font-bold uppercase tracking-wider ${
                        isActive ? 'text-cyan-400' : isCompleted ? 'text-emerald-400' : 'text-zinc-400'
                      }`}>
                        {tab.label}
                      </span>
                      {isCompleted ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                      ) : isActive ? (
                        <div className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
                      ) : null}
                    </div>
                    <p className="text-[11px] font-medium text-zinc-500 pl-1.5 truncate group-hover:text-zinc-400 transition-colors">
                      {tab.desc}
                    </p>
                  </button>
                )
              })}
            </div>
          </div>

          <form onSubmit={handleSubmit} className="relative z-10 space-y-6">

            {/* Step 1 Panel: Documents */}
            {currentTab === 'documents' && (
              <div className="space-y-6">
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
                        const selectedFile = e.target.files?.[0] ?? null
                        setFile(selectedFile)
                        if (selectedFile) {
                          setUploadTimestamp(new Date().toLocaleString())
                        } else {
                          setUploadTimestamp(null)
                        }
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

                <div className="flex justify-end pt-4">
                  <button
                    type="button"
                    disabled={!isDocumentValid}
                    onClick={() => setCurrentTab('workflow')}
                    className="inline-flex items-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 disabled:cursor-not-allowed px-6 py-3.5 text-sm font-semibold text-black transition-all cursor-pointer shadow-[0_0_15px_rgba(34,211,238,0.15)]"
                  >
                    Continue to Workflow
                    <ArrowRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}

            {/* Step 2 Panel: Participants & Workflow */}
            {currentTab === 'workflow' && (
              <div className="space-y-6 pt-2">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <h3 className="text-lg font-light text-white flex items-center gap-2">
                      <UserPlus className="h-5 w-5 text-cyan-400" />
                      Workflow Builder
                    </h3>
                    <p className="text-xs text-zinc-500 mt-1">
                      Design a sequential routing workflow. Participants in each step will receive the document in order.
                    </p>
                  </div>
                  
                  <button
                    type="button"
                    onClick={addStep}
                    disabled={isSubmitting}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 hover:bg-cyan-500 hover:text-black hover:border-cyan-400 px-4 py-2.5 text-xs font-semibold text-cyan-400 transition-all duration-300 shadow-[0_0_15px_rgba(34,211,238,0.05)] cursor-pointer shrink-0 self-start sm:self-auto"
                  >
                    <Plus className="h-4 w-4" />
                    Add Workflow Step
                  </button>
                </div>

                <div className="space-y-4">
                  {steps.map((step, stepIdx) => (
                    <div key={step.stepNumber} className="flex flex-col items-center w-full">
                      {/* Step Card */}
                      <div className="w-full glass-panel rounded-3xl overflow-visible border border-white/5 shadow-2xl p-6 relative">
                        {/* Step Header */}
                        <div className="flex items-center justify-between mb-4 pb-3 border-b border-white/5">
                          <div className="flex items-center gap-3">
                            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-cyan-500/20 border border-cyan-500/30 text-xs font-bold text-cyan-400 shadow-[0_0_15px_rgba(34,211,238,0.1)]">
                              {step.stepNumber}
                            </span>
                            <div>
                              <h4 className="text-sm font-semibold text-white uppercase tracking-wider">
                                Step {step.stepNumber} Recipients
                              </h4>
                              <p className="text-[10px] text-zinc-500">Executes in parallel at this sequence number</p>
                            </div>
                          </div>

                          <div className="flex items-center gap-2">
                            {/* Move Up */}
                            <button
                              type="button"
                              disabled={isSubmitting || stepIdx === 0}
                              onClick={() => moveStep(step.stepNumber, 'up')}
                              className="rounded-lg p-1.5 text-zinc-500 hover:text-cyan-400 hover:bg-cyan-500/10 transition-all disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer disabled:cursor-not-allowed animate-none"
                              title="Move Step Up"
                            >
                              <ChevronDown className="h-4 w-4 rotate-180" />
                            </button>

                            {/* Move Down */}
                            <button
                              type="button"
                              disabled={isSubmitting || stepIdx === steps.length - 1}
                              onClick={() => moveStep(step.stepNumber, 'down')}
                              className="rounded-lg p-1.5 text-zinc-500 hover:text-cyan-400 hover:bg-cyan-500/10 transition-all disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer disabled:cursor-not-allowed animate-none"
                              title="Move Step Down"
                            >
                              <ChevronDown className="h-4 w-4" />
                            </button>

                            {/* Delete Step */}
                            <button
                              type="button"
                              disabled={isSubmitting || steps.length <= 1}
                              onClick={() => removeStep(step.stepNumber)}
                              className="rounded-lg p-1.5 text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition-all disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer disabled:cursor-not-allowed animate-none"
                              title="Delete Step"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </div>

                        {/* Step Recipients List/Table */}
                        <div className="overflow-visible">
                          <table className="w-full text-left border-collapse text-sm">
                            <thead>
                              <tr className="text-zinc-500 uppercase text-[9px] font-bold tracking-wider bg-white/[0.002] border-b border-white/5">
                                <th className="px-4 py-2 min-w-[200px]">Name</th>
                                <th className="px-4 py-2 min-w-[220px]">Email Address</th>
                                <th className="px-4 py-2 min-w-[200px]">Role</th>
                                <th className="px-4 py-2 text-center w-[80px]">Actions</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-white/5">
                              {step.participants.length === 0 ? (
                                <tr>
                                  <td colSpan="4" className="px-4 py-8 text-center text-zinc-500">
                                    <div className="flex flex-col items-center justify-center">
                                      <User className="h-6 w-6 text-zinc-700 mb-1 stroke-[1.5]" />
                                      <p className="text-xs font-medium text-zinc-400">No participants in this step.</p>
                                      <button
                                        type="button"
                                        onClick={() => addParticipantToStep(step.stepNumber)}
                                        className="mt-2 text-[10px] text-cyan-400 hover:underline font-semibold"
                                      >
                                        + Add Participant
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              ) : (
                                step.participants.map((p) => (
                                  <tr key={p.id} className="hover:bg-white/[0.005] transition-colors group/row">
                                    <td className="px-3 py-2.5 align-middle">
                                      <div className="relative">
                                        <User className="absolute left-3 h-4 w-4 text-zinc-600 top-1/2 -translate-y-1/2" />
                                        <input
                                          type="text"
                                          value={p.name}
                                          onChange={(e) => updateParticipant(step.stepNumber, p.id, 'name', e.target.value)}
                                          placeholder="Full Name"
                                          disabled={isSubmitting}
                                          className={`${cellInputClass} pl-9`}
                                        />
                                      </div>
                                    </td>
                                    <td className="px-3 py-2.5 align-middle">
                                      <div className="relative">
                                        <Mail className="absolute left-3 h-4 w-4 text-zinc-600 top-1/2 -translate-y-1/2" />
                                        <input
                                          type="email"
                                          value={p.email}
                                          onChange={(e) => updateParticipant(step.stepNumber, p.id, 'email', e.target.value)}
                                          placeholder="Email Address"
                                          disabled={isSubmitting}
                                          className={`${cellInputClass} pl-9 font-mono`}
                                        />
                                      </div>
                                    </td>
                                    <td className="px-3 py-2.5 align-middle">
                                      <CustomSelect
                                        value={p.role}
                                        onChange={(val) => updateParticipant(step.stepNumber, p.id, 'role', val)}
                                        disabled={isSubmitting}
                                        options={[
                                          { value: 'signer', label: 'Signer (Signs)' },
                                          { value: 'approver', label: 'Approver (Approves)' },
                                          { value: 'reviewer', label: 'Reviewer (Reviews)' },
                                          { value: 'cc', label: 'CC (Receives copy)' }
                                        ]}
                                      />
                                    </td>
                                    <td className="px-3 py-2.5 align-middle text-center">
                                      <button
                                        type="button"
                                        onClick={() => removeParticipant(step.stepNumber, p.id)}
                                        disabled={isSubmitting}
                                        className="rounded-lg p-2 text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition-all cursor-pointer inline-flex items-center justify-center cursor-pointer"
                                        title="Remove Recipient"
                                      >
                                        <Trash2 className="h-4 w-4" />
                                      </button>
                                    </td>
                                  </tr>
                                ))
                              )}
                            </tbody>
                          </table>
                        </div>

                        {/* Add Recipient to Step button inside the step card */}
                        {step.participants.length > 0 && (
                          <div className="mt-4 flex justify-end">
                            <button
                              type="button"
                              onClick={() => addParticipantToStep(step.stepNumber)}
                              disabled={isSubmitting}
                              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-lg bg-zinc-800 hover:bg-cyan-500 hover:text-black border border-white/10 hover:border-cyan-400 text-zinc-300 transition-all duration-200 cursor-pointer"
                            >
                              <Plus className="h-3 w-3" />
                              Add Recipient to Step {step.stepNumber}
                            </button>
                          </div>
                        )}
                      </div>

                      {/* Down Arrow separator between steps */}
                      {stepIdx < steps.length - 1 && (
                        <div className="flex flex-col items-center my-3 relative">
                          <div className="h-8 w-[1px] bg-gradient-to-b from-cyan-500/50 to-transparent" />
                          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-cyan-950/40 border border-cyan-500/30 text-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.15)] backdrop-blur-md">
                            <ChevronDown className="h-4 w-4 animate-pulse" />
                          </div>
                          <div className="h-8 w-[1px] bg-gradient-to-t from-cyan-500/50 to-transparent" />
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                {/* Back and Continue Buttons */}
                <div className="flex justify-between pt-6 border-t border-white/5">
                  <button
                    type="button"
                    onClick={() => setCurrentTab('documents')}
                    className="inline-flex items-center gap-2 rounded-2xl bg-zinc-800 hover:bg-zinc-700 border border-white/10 px-6 py-3.5 text-sm font-semibold text-zinc-300 transition-all cursor-pointer"
                  >
                    Back
                  </button>
                  
                  <div className="flex flex-col items-end gap-1">
                    <button
                      type="button"
                      disabled={!isWorkflowValid || !hasSignerRole}
                      onClick={() => setCurrentTab('settings')}
                      className="inline-flex items-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 disabled:cursor-not-allowed px-6 py-3.5 text-sm font-semibold text-black transition-all cursor-pointer shadow-[0_0_15px_rgba(34,211,238,0.15)]"
                    >
                      Continue to Settings
                      <ArrowRight className="h-4 w-4" />
                    </button>
                    {!hasSignerRole && (
                      <p className="text-[10px] text-amber-400 font-semibold mt-1">
                        At least one participant must be assigned the "Signer" role.
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Step 3 Panel: Request Settings */}
            {currentTab === 'settings' && (
              <div className="space-y-6 pt-2">
                <div>
                  <h3 className="text-lg font-light text-white flex items-center gap-2">
                    <Settings className="h-5 w-5 text-cyan-400" />
                    Request Settings
                  </h3>
                  <p className="text-xs text-zinc-500 mt-1">
                    Configure request alerts, document distribution, and delivery settings before dispatching.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {/* Switch 1: Reminders */}
                  <div className="glass-panel rounded-2xl p-5 border border-white/5 bg-white/[0.01] flex flex-col justify-between min-h-[140px] relative transition-all duration-300 hover:border-cyan-500/20">
                    <div className="flex justify-between items-start">
                      <span className="text-[10px] uppercase font-bold tracking-widest text-zinc-500">Alerts</span>
                      <Bell className={`h-5 w-5 ${sendReminders ? 'text-cyan-400' : 'text-zinc-500'}`} />
                    </div>
                    <div className="mt-4 space-y-3">
                      <div>
                        <h4 className="text-sm font-bold text-white">Automatic Reminders</h4>
                        <p className="text-[10px] text-zinc-500 mt-0.5">Send status email alerts to pending signers.</p>
                      </div>
                      <label className="flex items-center gap-2 cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={sendReminders}
                          onChange={(e) => setSendReminders(e.target.checked)}
                          disabled={isSubmitting}
                          className="sr-only peer"
                        />
                        <div className="relative w-10 h-6 bg-white/10 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-zinc-400 after:border-zinc-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-cyan-500 peer-checked:after:bg-black peer-checked:after:border-cyan-400 shadow-[0_0_10px_rgba(0,0,0,0.5)]" />
                        <span className="text-xs text-zinc-400 peer-checked:text-cyan-400 font-medium">
                          {sendReminders ? 'Enabled' : 'Disabled'}
                        </span>
                      </label>
                    </div>
                  </div>

                  {/* Switch 2: Final Document Delivery */}
                  <div className="glass-panel rounded-2xl p-5 border border-white/5 bg-white/[0.01] flex flex-col justify-between min-h-[140px] relative transition-all duration-300 hover:border-cyan-500/20">
                    <div className="flex justify-between items-start">
                      <span className="text-[10px] uppercase font-bold tracking-widest text-zinc-500">Distribution</span>
                      <Share2 className={`h-5 w-5 ${sendFinalEmail ? 'text-cyan-400' : 'text-zinc-500'}`} />
                    </div>
                    <div className="mt-4 space-y-3">
                      <div>
                        <h4 className="text-sm font-bold text-white">Final Delivery</h4>
                        <p className="text-[10px] text-zinc-500 mt-0.5">Deliver completed copy to all participants.</p>
                      </div>
                      <label className="flex items-center gap-2 cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={sendFinalEmail}
                          onChange={(e) => setSendFinalEmail(e.target.checked)}
                          disabled={isSubmitting}
                          className="sr-only peer"
                        />
                        <div className="relative w-10 h-6 bg-white/10 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-zinc-400 after:border-zinc-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-cyan-500 peer-checked:after:bg-black peer-checked:after:border-cyan-400 shadow-[0_0_10px_rgba(0,0,0,0.5)]" />
                        <span className="text-xs text-zinc-400 peer-checked:text-cyan-400 font-medium">
                          {sendFinalEmail ? 'Deliver' : 'Do Not Deliver'}
                        </span>
                      </label>
                    </div>
                  </div>

                  {/* Switch 3: Allow Printing */}
                  <div className="glass-panel rounded-2xl p-5 border border-white/5 bg-white/[0.01] flex flex-col justify-between min-h-[140px] relative transition-all duration-300 hover:border-cyan-500/20">
                    <div className="flex justify-between items-start">
                      <span className="text-[10px] uppercase font-bold tracking-widest text-zinc-500">Permissions</span>
                      <Printer className={`h-5 w-5 ${allowPrinting ? 'text-cyan-400' : 'text-zinc-500'}`} />
                    </div>
                    <div className="mt-4 space-y-3">
                      <div>
                        <h4 className="text-sm font-bold text-white">Allow Printing</h4>
                        <p className="text-[10px] text-zinc-500 mt-0.5">Allow recipients to download or print copies.</p>
                      </div>
                      <label className="flex items-center gap-2 cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={allowPrinting}
                          onChange={(e) => setAllowPrinting(e.target.checked)}
                          disabled={isSubmitting}
                          className="sr-only peer"
                        />
                        <div className="relative w-10 h-6 bg-white/10 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-zinc-400 after:border-zinc-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-cyan-500 peer-checked:after:bg-black peer-checked:after:border-cyan-400 shadow-[0_0_10px_rgba(0,0,0,0.5)]" />
                        <span className="text-xs text-zinc-400 peer-checked:text-cyan-400 font-medium">
                          {allowPrinting ? 'Allowed' : 'Restricted'}
                        </span>
                      </label>
                    </div>
                  </div>
                </div>

                {/* 4. Additional Recipients Input Section */}
                <div className="glass-panel rounded-3xl p-6 border border-white/5 bg-white/[0.005] space-y-4">
                  <div>
                    <h4 className="text-sm font-bold text-white flex items-center gap-2">
                      <Mail className="h-4 w-4 text-cyan-400" />
                      Additional Recipients
                    </h4>
                    <p className="text-[10px] text-zinc-500 mt-0.5">Receive a carbon copy (CC) of the completed transaction record.</p>
                  </div>

                  <div className="flex flex-col sm:flex-row gap-3">
                    <div className="flex-1 relative">
                      <Mail className="absolute left-3 h-4 w-4 text-zinc-600 top-1/2 -translate-y-1/2" />
                      <input
                        type="email"
                        value={newRecipientEmail}
                        onChange={(e) => {
                          setNewRecipientEmail(e.target.value)
                          setRecipientEmailError('')
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.preventDefault()
                            addRecipientEmail()
                          }
                        }}
                        placeholder="Add observer email address (e.g. admin@company.com)"
                        disabled={isSubmitting}
                        className={`${inputClass} pl-10`}
                      />
                    </div>
                    <button
                      type="button"
                      onClick={addRecipientEmail}
                      disabled={isSubmitting || !newRecipientEmail.trim()}
                      className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-zinc-800 hover:bg-cyan-500 hover:text-black border border-white/10 hover:border-cyan-400 px-5 py-3.5 text-xs font-semibold text-zinc-300 transition-all duration-300 cursor-pointer shrink-0"
                    >
                      <Plus className="h-4 w-4" />
                      Add Recipient
                    </button>
                  </div>

                  {recipientEmailError && (
                    <p className="text-xs text-red-400 font-semibold">{recipientEmailError}</p>
                  )}

                  {/* Email Tag chips */}
                  {additionalRecipients.length > 0 && (
                    <div className="flex flex-wrap gap-2 pt-2">
                      {additionalRecipients.map((email) => (
                        <span
                          key={email}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-500/20 bg-cyan-500/10 px-3 py-1.5 text-xs font-medium text-cyan-300 font-mono animate-none"
                        >
                          {email}
                          <button
                            type="button"
                            onClick={() => removeRecipientEmail(email)}
                            disabled={isSubmitting}
                            className="rounded p-0.5 hover:bg-cyan-500/20 text-cyan-400 hover:text-cyan-200 transition-colors cursor-pointer"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Back and Continue Buttons */}
                <div className="flex justify-between pt-6 border-t border-white/5">
                  <button
                    type="button"
                    onClick={() => setCurrentTab('workflow')}
                    className="inline-flex items-center gap-2 rounded-2xl bg-zinc-800 hover:bg-zinc-700 border border-white/10 px-6 py-3.5 text-sm font-semibold text-zinc-300 transition-all cursor-pointer"
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    onClick={() => setCurrentTab('review')}
                    className="inline-flex items-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 px-6 py-3.5 text-sm font-semibold text-black transition-all cursor-pointer shadow-[0_0_15px_rgba(34,211,238,0.15)]"
                  >
                    Continue to Review
                    <ArrowRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}

            {/* Step 4 Panel: Review & Prepare */}
            {currentTab === 'review' && (
              <div className="space-y-6 pt-2">
                <div>
                  <h3 className="text-xl font-light text-white flex items-center gap-2">
                    <Sparkles className="h-5 w-5 text-cyan-400" />
                    Review & Prepare
                  </h3>
                  <p className="text-xs text-zinc-500 mt-1">
                    Preflight checklist validation and configuration summary before dispatch.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Grid Item 1: Document Summary */}
                  <div className="glass-panel rounded-2xl p-6 border border-white/5 bg-white/[0.01] flex flex-col justify-between transition-all duration-300 hover:border-cyan-500/20">
                    <div className="space-y-3">
                      <div className="flex items-center gap-2 border-b border-white/5 pb-2.5">
                        <FileText className="h-4 w-4 text-cyan-400" />
                        <h4 className="text-sm font-semibold text-white">Document Summary</h4>
                      </div>
                      
                      <div className="space-y-2 mt-2">
                        <div className="flex justify-between text-xs">
                          <span className="text-zinc-500">Name</span>
                          <span className="text-zinc-300 font-medium truncate max-w-[200px]" title={file?.name}>{file?.name || 'N/A'}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-zinc-500">File Size</span>
                          <span className="text-zinc-300 font-mono">
                            {file ? (file.size / (1024 * 1024) > 0.1 
                              ? `${(file.size / (1024 * 1024)).toFixed(2)} MB` 
                              : `${(file.size / 1024).toFixed(1)} KB`) 
                              : 'N/A'}
                          </span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-zinc-500">Total Pages</span>
                          <span className="text-zinc-300 font-medium">{numPages ? `${numPages} Page${numPages > 1 ? 's' : ''}` : 'N/A'}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-zinc-500">Uploaded At</span>
                          <span className="text-zinc-300 font-medium">{uploadTimestamp || 'N/A'}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Grid Item 2: Request Settings Summary */}
                  <div className="glass-panel rounded-2xl p-6 border border-white/5 bg-white/[0.01] flex flex-col justify-between transition-all duration-300 hover:border-cyan-500/20">
                    <div className="space-y-3">
                      <div className="flex items-center gap-2 border-b border-white/5 pb-2.5">
                        <Settings className="h-4 w-4 text-cyan-400" />
                        <h4 className="text-sm font-semibold text-white">Request Settings Summary</h4>
                      </div>
                      
                      <div className="space-y-2 mt-2">
                        <div className="flex justify-between text-xs">
                          <span className="text-zinc-500">Automatic Reminders</span>
                          <span className={`px-2 py-0.5 rounded-[6px] text-[10px] font-bold ${
                            sendReminders ? 'bg-cyan-500/10 text-cyan-400' : 'bg-zinc-800 text-zinc-500'
                          }`}>
                            {sendReminders ? 'ENABLED' : 'DISABLED'}
                          </span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-zinc-500">Final Email Delivery</span>
                          <span className={`px-2 py-0.5 rounded-[6px] text-[10px] font-bold ${
                            sendFinalEmail ? 'bg-emerald-500/10 text-emerald-400' : 'bg-zinc-800 text-zinc-500'
                          }`}>
                            {sendFinalEmail ? 'DELIVER' : 'DO NOT DELIVER'}
                          </span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-zinc-500">Printing & Download</span>
                          <span className={`px-2 py-0.5 rounded-[6px] text-[10px] font-bold ${
                            allowPrinting ? 'bg-cyan-500/10 text-cyan-400' : 'bg-red-500/10 text-red-400'
                          }`}>
                            {allowPrinting ? 'ALLOWED' : 'RESTRICTED'}
                          </span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-zinc-500">Additional CC Observers</span>
                          <span className="text-zinc-300 font-medium">
                            {additionalRecipients.length > 0 ? `${additionalRecipients.length} Recipient${additionalRecipients.length > 1 ? 's' : ''}` : 'None'}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Grid Item 3: Workflow Summary */}
                <div className="glass-panel rounded-2xl p-6 border border-white/5 bg-white/[0.01] transition-all duration-300 hover:border-cyan-500/20">
                  <div className="flex items-center gap-2 border-b border-white/5 pb-2.5 mb-4">
                    <UserPlus className="h-4 w-4 text-cyan-400" />
                    <h4 className="text-sm font-semibold text-white">Workflow Routing Path</h4>
                  </div>

                  <div className="space-y-4">
                    {steps.map((step, idx) => (
                      <div key={step.stepNumber} className="relative">
                        <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 bg-black/40 rounded-xl p-3 border border-white/5">
                          <div className="flex items-center gap-3">
                            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-cyan-500/20 border border-cyan-500/30 text-[10px] font-bold text-cyan-400">
                              {step.stepNumber}
                            </span>
                            <span className="text-xs font-bold text-white uppercase tracking-wider">Step {step.stepNumber}</span>
                          </div>
                          
                          <div className="flex flex-wrap gap-2">
                            {step.participants.map(p => (
                              <div key={p.id} className="flex items-center gap-2 bg-white/[0.02] border border-white/10 px-3 py-1 rounded-lg">
                                <span className="text-xs font-medium text-zinc-300">{p.name || 'Unnamed'}</span>
                                <span className="text-[10px] text-zinc-500 font-mono">({p.email || 'No email'})</span>
                                <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${
                                  p.role === 'signer' ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' :
                                  p.role === 'approver' ? 'bg-violet-500/10 text-violet-400 border border-violet-500/20' :
                                  p.role === 'reviewer' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                                  'bg-zinc-500/10 text-zinc-400 border border-white/5'
                                }`}>
                                  {p.role}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                        {idx < steps.length - 1 && (
                          <div className="flex justify-center my-1.5">
                            <ChevronDown className="h-4 w-4 text-cyan-500/40" />
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Grid Item 4: Preflight Validation Checklist */}
                <div className="glass-panel rounded-2xl p-6 border border-white/5 bg-white/[0.01] transition-all duration-300 hover:border-cyan-500/20">
                  <div className="flex items-center gap-2 border-b border-white/5 pb-2.5 mb-4">
                    <CheckCircle2 className="h-4 w-4 text-cyan-400" />
                    <h4 className="text-sm font-semibold text-white">Preflight Validation Checklist</h4>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {[
                      { 
                        label: 'Document Payload Uploaded', 
                        isValid: isDocumentValid, 
                        desc: 'Valid PDF document selected.' 
                      },
                      { 
                        label: 'Workflow Sequence Configured', 
                        isValid: isWorkflowValid, 
                        desc: 'All participants have names and valid email formats.' 
                      },
                      { 
                        label: 'At Least One "Signer" Exists', 
                        isValid: hasSignerRole, 
                        desc: 'At least one participant is assigned the Signer role.' 
                      },
                      { 
                        label: 'Target Signature Zone Placed', 
                        isValid: isSignaturePlaced, 
                        desc: 'Coordinates clicked on PDF preview page below.' 
                      }
                    ].map((item, idx) => (
                      <div 
                        key={idx} 
                        className={`flex items-start gap-3 rounded-xl p-3 border transition-colors ${
                          item.isValid 
                            ? 'bg-emerald-500/5 border-emerald-500/20 text-emerald-300' 
                            : 'bg-red-500/5 border-red-500/20 text-red-300'
                        }`}
                      >
                        <div className="mt-0.5">
                          {item.isValid ? (
                            <Check className="h-4 w-4 text-emerald-400 stroke-[2.5]" />
                          ) : (
                            <X className="h-4 w-4 text-red-400 stroke-[2.5]" />
                          )}
                        </div>
                        <div>
                          <div className={`text-xs font-bold ${item.isValid ? 'text-emerald-400' : 'text-zinc-400'}`}>
                            {item.label}
                          </div>
                          <p className="text-[10px] text-zinc-500 mt-0.5">{item.desc}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Back and Send buttons */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-6 border-t border-white/5">
                  <button
                    type="button"
                    onClick={() => setCurrentTab('settings')}
                    disabled={isSubmitting}
                    className="inline-flex items-center justify-center gap-2 rounded-2xl bg-zinc-800 hover:bg-zinc-700 border border-white/10 px-6 py-3.5 text-sm font-semibold text-zinc-300 transition-all cursor-pointer disabled:opacity-50"
                  >
                    Back
                  </button>

                  <div className="flex flex-col items-end gap-2">
                    <button
                      type="submit"
                      disabled={isSubmitting || !isDocumentValid || !isWorkflowValid || !hasSignerRole || !isSignaturePlaced}
                      className="group relative inline-flex items-center justify-center gap-2 overflow-hidden rounded-2xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 disabled:cursor-not-allowed px-8 py-3.5 text-sm font-semibold text-black transition-all shadow-[0_0_25px_rgba(34,211,238,0.2)] cursor-pointer"
                    >
                      <span className="relative z-10 flex items-center gap-2">
                        {isSubmitting ? 'Initializing Sequence…' : 'Send Package'}
                        {!isSubmitting && <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />}
                      </span>
                      <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/40 to-transparent group-hover:animate-[shimmer_1.5s_infinite]" />
                    </button>
                    
                    {!isSignaturePlaced && (
                      <p className="text-[11px] text-amber-400 font-semibold text-right max-w-sm">
                        Please scroll down to "Target Signature Zone" below and select a signature coordinate on the PDF document to enable sending.
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}
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
