import { useEffect, useMemo, useRef, useState } from 'react'
import { createEnvelope, sendEnvelope, uploadDocument, createTemplate, getTemplateDetail, getPackageDetail, saveDraft, updateDraft, apiClient, API_URL } from '../services/api.js'
import UserNav from '../components/UserNav.jsx'
import { Document, Page, pdfjs } from 'react-pdf'
import { motion, AnimatePresence } from 'framer-motion'
import { UploadCloud, User, Mail, FileText, X, ArrowRight, CheckCircle2, Sparkles, Crosshair, Plus, Trash2, Edit3, UserPlus, Check, ChevronDown, Sparkles as SparkleIcon, Bell, Share2, Printer, Settings, Activity, Eye, ArrowLeft } from 'lucide-react'
import { useNavigate, Link } from 'react-router-dom'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'

// ── Configure pdf.js worker (must live in the same module as <Document>) ──────
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

// ── Style constants ───────────────────────────────────────────────
const inputClass =
  'w-full rounded-2xl border border-border-color bg-card-bg px-4 py-3.5 pl-11 text-sm text-text-primary placeholder:text-text-secondary/60 outline-none backdrop-blur-xl transition-all duration-300 focus:border-cyan-500/50 focus:bg-cyan-950/10 focus:ring-2 focus:ring-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-60'

const selectClass =
  'w-full rounded-2xl border border-border-color bg-card-bg px-4 py-3.5 text-sm text-text-primary placeholder:text-text-secondary/60 outline-none backdrop-blur-xl transition-all duration-300 focus:border-cyan-500/50 focus:bg-cyan-950/10 focus:ring-2 focus:ring-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-60'

const cellInputClass =
  'w-full bg-card-bg border border-border-color rounded-xl px-3 py-2.5 text-sm text-text-primary placeholder:text-text-secondary/60 outline-none transition-all duration-200 focus:border-cyan-500/30 focus:bg-cyan-950/5 focus:ring-1 focus:ring-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-60'

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
        className="w-full rounded-2xl border border-border-color bg-card-bg px-4 py-3.5 text-sm text-text-primary text-left outline-none backdrop-blur-xl transition-all duration-300 focus:border-cyan-500/50 focus:bg-cyan-950/10 focus:ring-2 focus:ring-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-60 flex items-center justify-between cursor-pointer"
      >
        <span className="truncate">{selectedOption ? selectedOption.label : 'Select role'}</span>
        <ChevronDown className={`h-4 w-4 text-text-secondary transition-transform duration-300 ${isOpen ? 'rotate-180 text-cyan-400' : ''}`} />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="glass-panel absolute mt-2 w-full z-[100] rounded-2xl overflow-hidden p-2"
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
                        : 'text-text-primary hover:bg-cyan-500 hover:text-black border border-transparent'
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

function SuccessScreen({ sentPackageInfo, onTrackProgress, onViewDetails, onReturn }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className="relative z-10 flex flex-col items-center py-6 text-center"
    >
      {/* Icon and Title */}
      <div className="relative mb-6">
        <div className="absolute inset-0 rounded-full bg-emerald-500/20 blur-xl animate-pulse" />
        <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 shadow-[0_0_30px_rgba(16,185,129,0.2)]">
          <CheckCircle2 className="h-10 w-10" />
        </div>
      </div>

      <h2 className="text-3xl font-bold tracking-tight text-text-primary sm:text-4xl">
        Workflow Dispatched
      </h2>
      <p className="mt-2 text-sm text-zinc-400 max-w-md">
        Your document has been sent successfully. The sequential enterprise routing sequence is now active.
      </p>

      {/* Details Receipt Card */}
      <div className="w-full max-w-md mt-8 p-6 rounded-2xl glass-panel text-left space-y-4 shadow-lg">
        <div className="flex items-center justify-between border-b border-border-color pb-3">
          <span className="text-xs font-bold uppercase tracking-wider text-text-secondary">Envelope Details</span>
          <span className="inline-flex items-center gap-1 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-0.5 text-[10px] font-mono font-bold uppercase text-cyan-400 tracking-wider animate-pulse">
            <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-ping mr-1" />
            In Progress
          </span>
        </div>

        <div className="space-y-3">
          <div className="flex items-start justify-between gap-4">
            <span className="text-xs text-text-secondary shrink-0">Document</span>
            <span className="text-xs font-medium text-text-primary truncate flex items-center gap-1.5 max-w-[240px]">
              <FileText className="h-3.5 w-3.5 text-text-secondary shrink-0" />
              <span className="truncate" title={sentPackageInfo.documentName}>{sentPackageInfo.documentName}</span>
            </span>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs text-text-secondary">Active Routing Step</span>
            <span className="inline-flex px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border bg-cyan-500/10 text-cyan-400 border-cyan-500/20">
              Step 1 - {sentPackageInfo.firstStepRole}
            </span>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs text-text-secondary">Total Participants</span>
            <span className="text-xs font-semibold text-text-primary font-mono">
              {sentPackageInfo.totalParticipants} enrolled
            </span>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs text-text-secondary">Dispatched Date</span>
            <span className="text-xs font-semibold text-text-primary font-mono">
              {sentPackageInfo.createdDate}
            </span>
          </div>
        </div>

        <div className="border-t border-border-color pt-3 flex justify-between items-center text-[10px] text-text-secondary">
          <span>Envelope ID</span>
          <span className="font-mono text-text-primary select-all truncate max-w-[200px]" title={sentPackageInfo.id}>
            {sentPackageInfo.id}
          </span>
        </div>
      </div>

      {/* Buttons */}
      <div className="w-full max-w-md mt-8 flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={onTrackProgress}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black px-4 py-3.5 text-xs font-bold transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] hover:shadow-[0_0_30px_rgba(34,211,238,0.45)] uppercase tracking-wider cursor-pointer"
          >
            <Activity className="h-4 w-4" />
            Track Progress
          </button>
          
          <button
            type="button"
            onClick={onViewDetails}
            className="inline-flex items-center justify-center gap-2 rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-primary hover:text-cyan-400 px-4 py-3.5 text-xs font-bold transition-all duration-300 uppercase tracking-wider cursor-pointer"
          >
            <Eye className="h-4 w-4" />
            View Package
          </button>
        </div>

        <button
          type="button"
          onClick={onReturn}
          className="inline-flex items-center justify-center gap-2 rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-secondary hover:text-cyan-400 px-4 py-3 text-xs font-medium transition-all duration-300 cursor-pointer"
        >
          Return to Workspace
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </motion.div>
  )
}

const steps = [
  {
    id: "documents",
    title: "Documents",
    description: "Upload document"
  },
  {
    id: "recipients",
    title: "Recipients",
    description: "Configure signers"
  },
  {
    id: "prepare",
    title: "Prepare",
    description: "Place fields"
  },
  {
    id: "settings",
    title: "Settings",
    description: "Package settings"
  },
  {
    id: "review",
    title: "Review",
    description: "Final review"
  }
];

export default function UploadPage() {
  const navigate = useNavigate()
  const templateId = useMemo(() => new URLSearchParams(window.location.search).get('templateId'), [])
  const [loadedTemplate, setLoadedTemplate] = useState(null)

  const packageId = useMemo(() => {
    const params = new URLSearchParams(window.location.search)
    return params.get('packageId') || params.get('envelopeId')
  }, [])

  // draftId: set from URL on resume, or from API response after first Save Draft
  const draftIdParam = useMemo(() => new URLSearchParams(window.location.search).get('draftId'), [])
  const [draftId, setDraftId] = useState(null)

  const backendOrigin = useMemo(() => {
    try {
      const u = new URL(apiClient?.defaults?.baseURL)
      return u.origin
    } catch {
      return API_URL
    }
  }, [])

  function toAbsoluteUrl(maybeRelativeUrl, origin) {
    if (!maybeRelativeUrl) return ''
    if (/^https?:\/\//i.test(maybeRelativeUrl)) return maybeRelativeUrl
    const path = maybeRelativeUrl.startsWith('/') ? maybeRelativeUrl : `/${maybeRelativeUrl}`
    return `${origin}${path}`
  }

  // ── Form / workflow state ─────────────────────────────────────
  const [file, setFile] = useState(null)
  const [workflowSteps, setWorkflowSteps] = useState([
    {
      stepNumber: 1,
      participants: [{ id: '1', name: '', email: '', role: 'signer' }]
    }
  ])
  const [settingsValid, setSettingsValid] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isSavingDraft, setIsSavingDraft] = useState(false)
  const [draftSaved, setDraftSaved] = useState(false)
  const [error, setError] = useState('')
  const [sentPackageInfo, setSentPackageInfo] = useState(null)
  const [currentTab, setCurrentTab] = useState('documents')
  const [uploadTimestamp, setUploadTimestamp] = useState(null)
  const [uploadError, setUploadError] = useState('')
  const [isValidating, setIsValidating] = useState(false)
  const [placedFields, setPlacedFields] = useState([])
  const [selectedFieldType, setSelectedFieldType] = useState('signature')
  const [activeParticipantEmail, setActiveParticipantEmail] = useState('')
  const [existingDocUrl, setExistingDocUrl] = useState('')
  const [existingDocName, setExistingDocName] = useState('')
  const [existingDocId, setExistingDocId] = useState(null)

  // ── Reusable template states ──────────────────────────────────
  const [isTemplateModalOpen, setIsTemplateModalOpen] = useState(false)
  const [templateName, setTemplateName] = useState('')
  const [templateDescription, setTemplateDescription] = useState('')
  const [templateCategory, setTemplateCategory] = useState('General')
  const [templateVisibility, setTemplateVisibility] = useState('private')
  const [isSavingTemplate, setIsSavingTemplate] = useState(false)
  const [templateModalError, setTemplateModalError] = useState('')

  const openTemplateModal = () => {
    setTemplateName('')
    setTemplateDescription('')
    setTemplateCategory('General')
    setTemplateVisibility('private')
    setTemplateModalError('')
    setIsTemplateModalOpen(true)
  }

  // ── Request settings state ───────────────────────────────────────────
  const [sendReminders, setSendReminders] = useState(false)
  const [sendFinalEmail, setSendFinalEmail] = useState(true)
  const [allowPrinting, setAllowPrinting] = useState(true)
  const [additionalRecipients, setAdditionalRecipients] = useState([])
  const [newRecipientEmail, setNewRecipientEmail] = useState('')
  const [recipientEmailError, setRecipientEmailError] = useState('')
  // Keyed by participant id → error message string
  const [participantErrors, setParticipantErrors] = useState({})

  // ── Signature position — page-aware ──────────────────────────────────────
  const [sigPosition, setSigPosition] = useState(null)

  // ── react-pdf state ───────────────────────────────────────────────────────
  const [numPages, setNumPages] = useState(null)

  // ── Object-URL for the selected PDF ──────────────────────────────────────
  const previewUrl = useMemo(() => {
    if (existingDocUrl) return existingDocUrl
    if (!file || file.type !== 'application/pdf') return null
    return URL.createObjectURL(file)
  }, [file, existingDocUrl])

  const isPdf = useMemo(() => {
    if (existingDocUrl) return true
    if (!file) return true
    const byType = file.type === 'application/pdf'
    const byName = file.name?.toLowerCase().endsWith('.pdf')
    return byType || byName
  }, [file, existingDocUrl])

  // ── Preflight derived states ──────────────────────────────────────────────
  const isDocumentValid = useMemo(() => {
    return (!!file || !!existingDocUrl) && isPdf && !uploadError && !isValidating
  }, [file, existingDocUrl, isPdf, uploadError, isValidating])

  const allParticipants = useMemo(() => {
    return workflowSteps.flatMap(s => s.participants.map(p => ({
      ...p,
      stepNumber: s.stepNumber
    }))).filter(p => p.name?.trim() && p.email?.trim())
  }, [workflowSteps])

  useEffect(() => {
    if (allParticipants.length > 0 && !activeParticipantEmail) {
      setActiveParticipantEmail(allParticipants[0].email)
    }
  }, [allParticipants, activeParticipantEmail])

  const isWorkflowValid = useMemo(() => {
    const allParticipants = workflowSteps.flatMap(s => s.participants)
    if (workflowSteps.length === 0 || allParticipants.length === 0) return false
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    return allParticipants.every(p => p.name?.trim() && p.email?.trim() && emailRegex.test(p.email.trim()))
  }, [workflowSteps])

  const hasSignerRole = useMemo(() => {
    return workflowSteps.flatMap(s => s.participants).some(p => p.role === 'signer')
  }, [workflowSteps])

  const isSignaturePlaced = useMemo(() => {
    return (!!sigPosition && !!sigPosition.page && sigPosition.x_ratio != null && sigPosition.y_ratio != null) || (placedFields.length > 0)
  }, [sigPosition, placedFields])

  const getStepCompletion = (stepId) => {
    switch (stepId) {
      case 'documents':
        return isDocumentValid;
      case 'recipients':
        return isWorkflowValid && hasSignerRole;
      case 'prepare':
        return isSignaturePlaced;
      case 'settings':
        return settingsValid;
      case 'review':
        return isDocumentValid && isWorkflowValid && hasSignerRole && isSignaturePlaced && settingsValid;
      default:
        return false;
    }
  }

  const getStepClickable = (stepId) => {
    if (stepId === 'documents') return true;
    const idx = steps.findIndex(s => s.id === stepId);
    if (idx === -1) return false;
    return steps.slice(0, idx).every(s => getStepCompletion(s.id));
  }

  const progressPercent = useMemo(() => {
    const idx = steps.findIndex(s => s.id === currentTab)
    if (idx === -1) return 0
    return ((idx + 1) / steps.length) * 100
  }, [currentTab])

  const currentStepInfo = useMemo(() => {
    const idx = steps.findIndex(s => s.id === currentTab)
    return {
      num: idx !== -1 ? idx + 1 : 1,
      title: idx !== -1 ? steps[idx].title : ''
    }
  }, [currentTab])

  // ── Participant / Step Actions ───────────────────────────────────────────
  const addStep = () => {
    const nextStepNum = workflowSteps.length + 1
    const newStep = {
      stepNumber: nextStepNum,
      participants: [
        { id: crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(), name: '', email: '', role: 'signer' }
      ]
    }
    setWorkflowSteps(prev => [...prev, newStep])
  }

  const removeStep = (stepNumber) => {
    setWorkflowSteps(prev => {
      const filtered = prev.filter(s => s.stepNumber !== stepNumber)
      return filtered.map((s, idx) => ({
        ...s,
        stepNumber: idx + 1
      }))
    })
  }

  const addParticipantToStep = (stepNumber) => {
    setWorkflowSteps(prev =>
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
    setWorkflowSteps(prev =>
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
    setWorkflowSteps(prev =>
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
    const index = workflowSteps.findIndex(s => s.stepNumber === stepNumber)
    if (index === -1) return
    const newIndex = direction === 'up' ? index - 1 : index + 1
    if (newIndex < 0 || newIndex >= workflowSteps.length) return

    setWorkflowSteps(prev => {
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

  const handleSaveTemplateSubmit = async (e) => {
    e.preventDefault()
    if (!templateName.trim()) {
      setTemplateModalError('Template name is required.')
      return
    }
    setTemplateModalError('')
    setIsSavingTemplate(true)
    try {
      const workflowDef = workflowSteps.flatMap(s => 
        s.participants.map(p => ({
          step: s.stepNumber,
          role: p.role
        }))
      )
      
      const reqSettings = {
        send_reminders: sendReminders,
        send_final_email: sendFinalEmail,
        allow_printing: allowPrinting,
        additional_recipients: additionalRecipients
      }

      await createTemplate({
        name: templateName.trim(),
        description: templateDescription.trim(),
        category: templateCategory,
        visibility: templateVisibility,
        workflow_definition: workflowDef,
        request_settings: reqSettings
      })

      setIsTemplateModalOpen(false)
      navigate('/templates')
    } catch (err) {
      setTemplateModalError(err?.response?.data?.detail || err?.message || 'Failed to create template blueprint.')
    } finally {
      setIsSavingTemplate(false)
    }
  }

  // ── Prepopulate Preset Engine ──
  useEffect(() => {
    if (templateId) {
      async function loadTemplate() {
        try {
          const tpl = await getTemplateDetail(templateId)
          if (tpl) {
            setLoadedTemplate(tpl)
            
            // 1. request_settings
            if (tpl.request_settings) {
              if (tpl.request_settings.send_reminders !== undefined) setSendReminders(tpl.request_settings.send_reminders)
              if (tpl.request_settings.send_final_email !== undefined) setSendFinalEmail(tpl.request_settings.send_final_email)
              if (tpl.request_settings.allow_printing !== undefined) setAllowPrinting(tpl.request_settings.allow_printing)
              if (tpl.request_settings.additional_recipients !== undefined) setAdditionalRecipients(tpl.request_settings.additional_recipients)
            }
            
            // 2. workflow_definition / steps
            if (tpl.workflow_definition && Array.isArray(tpl.workflow_definition) && tpl.workflow_definition.length > 0) {
              const grouped = {}
              tpl.workflow_definition.forEach(item => {
                const stepNum = item.step || 1
                if (!grouped[stepNum]) {
                  grouped[stepNum] = []
                }
                grouped[stepNum].push({
                  id: crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2),
                  name: '',
                  email: '',
                  role: item.role || 'signer'
                })
              })
              
              const sortedSteps = Object.keys(grouped)
                .map(Number)
                .sort((a, b) => a - b)
                .map((stepNum, idx) => ({
                  stepNumber: idx + 1,
                  participants: grouped[stepNum]
                }))
              
              if (sortedSteps.length > 0) {
                setWorkflowSteps(sortedSteps)
              }
            }
          }
        } catch (err) {
          setError(err?.response?.data?.detail || err?.message || 'Failed to load the selected template blueprint.')
        }
      }
      loadTemplate()
    }
  }, [templateId])

  // ── Rehydrate / Load Package Engine ──
  useEffect(() => {
    if (packageId) {
      async function loadPackage() {
        try {
          const res = await getPackageDetail(packageId)
          if (res) {
            // 1. request_settings
            if (res.send_reminders !== undefined) setSendReminders(res.send_reminders)
            if (res.send_final_email !== undefined) setSendFinalEmail(res.send_final_email)
            if (res.allow_printing !== undefined) setAllowPrinting(res.allow_printing)
            if (res.additional_recipients !== undefined) setAdditionalRecipients(res.additional_recipients || [])

            // 2. document info
            if (res.document) {
              setExistingDocId(res.document.id)
              setExistingDocName(res.document.filename || 'document.pdf')
              if (res.document.url) {
                setExistingDocUrl(toAbsoluteUrl(res.document.url, backendOrigin))
              }
            }

            // 3. participants / steps
            if (res.participants && Array.isArray(res.participants) && res.participants.length > 0) {
              const grouped = {}
              res.participants.forEach(p => {
                const stepNum = p.step_number || 1
                if (!grouped[stepNum]) {
                  grouped[stepNum] = []
                }
                grouped[stepNum].push({
                  id: p.id ? p.id.toString() : Math.random().toString(36).substring(2),
                  name: p.name || '',
                  email: p.email || '',
                  role: p.role || 'signer'
                })
              })
              
              const sortedSteps = Object.keys(grouped)
                .map(Number)
                .sort((a, b) => a - b)
                .map((stepNum, idx) => ({
                  stepNumber: idx + 1,
                  participants: grouped[stepNum]
                }))
              
              if (sortedSteps.length > 0) {
                setWorkflowSteps(sortedSteps)
              }
            }

            // 4. placed fields
            if (res.fields && Array.isArray(res.fields)) {
              const mappedFields = res.fields.map(f => ({
                id: f.id ? f.id.toString() : Math.random().toString(36).substring(2) + Math.random().toString(),
                field_type: f.field_type,
                page: f.page,
                x_ratio: f.x_ratio,
                y_ratio: f.y_ratio,
                participant_email: f.participant_email,
                participant_name: f.participant_name,
                required: f.required
              }))
              setPlacedFields(mappedFields)
            }
          }
        } catch (err) {
          setError(err?.response?.data?.detail || err?.message || 'Failed to load the selected package.')
        }
      }
      loadPackage()
    }
  }, [packageId, backendOrigin])

  // ── Load draft from URL param ──────────────────────────────────────────────
  useEffect(() => {
    if (draftIdParam) {
      setDraftId(draftIdParam)
      async function loadDraft() {
        try {
          const res = await getPackageDetail(draftIdParam)
          if (res) {
            if (res.send_reminders !== undefined) setSendReminders(res.send_reminders)
            if (res.send_final_email !== undefined) setSendFinalEmail(res.send_final_email)
            if (res.allow_printing !== undefined) setAllowPrinting(res.allow_printing)
            if (res.additional_recipients !== undefined) setAdditionalRecipients(res.additional_recipients || [])
            if (res.document) {
              setExistingDocId(res.document.id)
              setExistingDocName(res.document.filename || 'document.pdf')
              if (res.document.url) setExistingDocUrl(toAbsoluteUrl(res.document.url, backendOrigin))
            }
            if (res.participants && Array.isArray(res.participants) && res.participants.length > 0) {
              const grouped = {}
              res.participants.forEach(p => {
                const stepNum = p.step_number || 1
                if (!grouped[stepNum]) grouped[stepNum] = []
                grouped[stepNum].push({
                  id: p.id ? p.id.toString() : Math.random().toString(36).substring(2),
                  name: p.name || '', email: p.email || '', role: p.role || 'signer'
                })
              })
              const sortedSteps = Object.keys(grouped).map(Number).sort((a, b) => a - b)
                .map((stepNum, idx) => ({ stepNumber: idx + 1, participants: grouped[stepNum] }))
              if (sortedSteps.length > 0) setWorkflowSteps(sortedSteps)
            }
            if (res.fields && Array.isArray(res.fields)) {
              setPlacedFields(res.fields.map(f => ({
                id: f.id ? f.id.toString() : Math.random().toString(36).substring(2) + Math.random(),
                field_type: f.field_type, page: f.page,
                x_ratio: f.x_ratio, y_ratio: f.y_ratio,
                participant_email: f.participant_email, participant_name: f.participant_name,
                required: f.required
              })))
            }
          }
        } catch (err) {
          setError(err?.response?.data?.detail || err?.message || 'Failed to load draft.')
        }
      }
      loadDraft()
    }
  }, [draftIdParam, backendOrigin])


  // ── Save Draft handler ────────────────────────────────────────────────────
  async function handleSaveDraft() {
    const docAvailable = !!existingDocId || !!file
    if (!docAvailable) {
      setError('Please upload a document before saving as draft.')
      return
    }
    setIsSavingDraft(true)
    setDraftSaved(false)
    setError('')
    try {
      // Upload file if a new one was selected (caches the id for future saves)
      let documentId = existingDocId
      if (file) {
        const uploadRes = await uploadDocument(file)
        documentId = uploadRes?.document_id
        setExistingDocId(documentId)
      }
      if (!documentId) throw new Error('No document ID available.')

      // Only include participants that have valid name + email
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
      const preparedParticipants = []
      let globalOrder = 1
      workflowSteps.forEach(step => {
        step.participants.forEach(p => {
          if (p.name?.trim() && p.email?.trim() && emailRegex.test(p.email.trim())) {
            preparedParticipants.push({
              name: p.name.trim(), email: p.email.trim(),
              role: p.role, step_number: step.stepNumber, order: globalOrder++
            })
          }
        })
      })

      const preparedFields = placedFields.map(f => ({
        field_type: f.field_type, page: f.page,
        x_ratio: f.x_ratio, y_ratio: f.y_ratio,
        participant_email: f.participant_email, required: f.required !== false,
      }))

      const sigPayload = sigPosition ? {
        signature_page: sigPosition.page,
        signature_x_ratio: sigPosition.x_ratio,
        signature_y_ratio: sigPosition.y_ratio,
      } : {}

      if (draftId) {
        // PATCH — update the existing draft
        await updateDraft(draftId, {
          document_id: documentId,
          participants: preparedParticipants,
          fields: preparedFields,
          send_reminders: sendReminders,
          send_final_email: sendFinalEmail,
          allow_printing: allowPrinting,
          additional_recipients: additionalRecipients,
          ...sigPayload,
        })
      } else {
        // POST — create a new draft envelope
        const res = await saveDraft({
          documentId,
          participants: preparedParticipants,
          fields: preparedFields,
          send_reminders: sendReminders,
          send_final_email: sendFinalEmail,
          allow_printing: allowPrinting,
          additional_recipients: additionalRecipients,
          ...sigPayload,
        })
        if (res?.envelope_id) setDraftId(res.envelope_id.toString())
      }

      setDraftSaved(true)
      setTimeout(() => setDraftSaved(false), 3000)
    } catch (err) {
      let message = ''
      if (err?.response?.data) {
        if (typeof err.response.data === 'string') message = err.response.data
        else if (err.response.data.detail) message = err.response.data.detail
        else {
          const firstKey = Object.keys(err.response.data)[0]
          if (firstKey) { const val = err.response.data[firstKey]; message = Array.isArray(val) ? val[0] : val }
        }
      }
      if (!message) message = err?.message || 'Failed to save draft.'
      setError(message)
    } finally {
      setIsSavingDraft(false)
    }
  }

  // ── Send Package (form submit) handler ───────────────────────────────────
  async function handleSubmit(e) {
    e.preventDefault()
    setError('')

    if (!file && !existingDocUrl) return setError('Please choose a PDF file.')
    if (file && !isPdf) return setError('Only PDF files are supported.')

    // VALIDATION
    if (workflowSteps.length === 0) {
      return setError('At least one step is required to create a workflow.')
    }
    const allParticipants = workflowSteps.flatMap(s => s.participants)
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

    if (!isSignaturePlaced) {
      return setError('Please select a signature position before generating the signing link.')
    }

    setIsSubmitting(true)
    try {
      let documentId = existingDocId
      if (file) {
        const uploadRes = await uploadDocument(file)
        documentId = uploadRes?.document_id
      }
      if (!documentId) throw new Error('No document ID available.')

      const preparedParticipants = []
      let globalOrder = 1
      workflowSteps.forEach(step => {
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
        fields: placedFields,
      })
      const envelopeId = envelopeRes?.envelope_id
      if (!envelopeId) throw new Error('Envelope created but no envelope_id returned.')

      await sendEnvelope(envelopeId)

      setSentPackageInfo({
        id: envelopeId,
        documentName: file ? file.name : (existingDocName || 'document.pdf'),
        totalParticipants: preparedParticipants.length,
        firstStepRole: preparedParticipants.find(p => p.step_number === 1)?.role || 'Signer',
        createdDate: new Date().toLocaleDateString(undefined, {
          month: 'long',
          day: 'numeric',
          year: 'numeric'
        })
      })
    } catch (err) {
      let message = ''
      if (err?.response?.data) {
        if (typeof err.response.data === 'string') {
          message = err.response.data
        } else if (err.response.data.detail) {
          message = err.response.data.detail
        } else if (err.response.data.file) {
          message = Array.isArray(err.response.data.file) ? err.response.data.file[0] : err.response.data.file
        } else {
          const firstKey = Object.keys(err.response.data)[0]
          if (firstKey) {
            const val = err.response.data[firstKey]
            message = Array.isArray(val) ? val[0] : val
          }
        }
      }
      if (!message) {
        message = err?.message || 'Something went wrong. Please try again.'
      }
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
    const x_ratio = x / rect.width
    const y_ratio = y / rect.height

    // 1. Maintain backward compatibility for the legacy signature position
    setSigPosition({
      page: pageNumber,
      x,
      y,
      x_ratio,
      y_ratio,
    })

    // 2. Add to placed fields if active participant is selected
    if (!activeParticipantEmail) {
      const firstPart = allParticipants[0]
      if (!firstPart) {
        setError('Please configure at least one participant name and email first.')
        return
      }
      setActiveParticipantEmail(firstPart.email)
    }

    const targetPart = allParticipants.find(p => p.email === activeParticipantEmail) || allParticipants[0]
    if (!targetPart) return

    const newField = {
      id: crypto.randomUUID ? crypto.randomUUID() : Date.now().toString() + Math.random().toString(),
      field_type: selectedFieldType,
      page: pageNumber,
      x,
      y,
      x_ratio,
      y_ratio,
      participant_email: targetPart.email,
      participant_name: targetPart.name,
      required: true
    }

    setPlacedFields(prev => [...prev, newField])
  }

  const removeField = (fieldId) => {
    setPlacedFields(prev => prev.filter(f => f.id !== fieldId))
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-12 sm:py-20 relative z-10">

      {/* Return link & UserNav wrapper */}
      {!sentPackageInfo && (
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-8 flex justify-between items-center w-full">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-400 hover:text-cyan-400 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Dashboard
          </Link>
          <UserNav />
        </motion.div>
      )}

      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
      >
            {/* ── Upload / signer form card ── */}
            <div className="glass-panel rounded-3xl p-8 sm:p-12 relative overflow-hidden">
          {/* Subtle gradient background behind the card content */}
          <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/[0.02] via-transparent to-violet-500/[0.02] opacity-50 pointer-events-none" />

          {sentPackageInfo ? (
            <SuccessScreen
              sentPackageInfo={sentPackageInfo}
              onTrackProgress={() => navigate(`/packages/${sentPackageInfo.id}`)}
              onViewDetails={() => navigate(`/packages/${sentPackageInfo.id}`)}
              onReturn={() => {
                setFile(null)
                setWorkflowSteps([
                  {
                    stepNumber: 1,
                    participants: [{ id: '1', name: '', email: '', role: 'signer' }]
                  }
                ])
                setSigPosition(null)
                setSentPackageInfo(null)
                setCurrentTab('documents')
                navigate('/')
              }}
            />
          ) : (
            <>
              <div className="relative z-10 mb-10 flex flex-col justify-between items-start gap-4 border-b border-border-color pb-6">
                <div className="space-y-3">
                  {loadedTemplate && (
                    <div className="inline-flex items-center gap-2 rounded-full border border-violet-500/30 bg-violet-500/10 px-3 py-1 text-xs font-semibold text-violet-400 backdrop-blur-md mb-2">
                      <SparkleIcon className="h-3 w-3 animate-pulse text-violet-400" />
                      Template: {loadedTemplate.name}
                    </div>
                  )}
                  <h1 className="text-4xl font-bold tracking-tight text-text-primary sm:text-[60px] sm:leading-none">
                    Create Package
                  </h1>
                  <p className="text-sm font-medium text-text-secondary sm:text-base">
                    Upload, configure, and send documents for signature.
                  </p>
                </div>
              </div>


          {/* Progress Bar */}
          <div className="relative w-full bg-border-color/30 rounded-full h-1.5 mb-6 overflow-hidden z-10">
            <div
              className="bg-cyan-500 h-full rounded-full transition-all duration-500 ease-out shadow-[0_0_8px_#22d3ee]"
              style={{ width: `${progressPercent}%` }}
            />
          </div>

          {/* Promoted Step Header */}
          <div className="flex flex-col gap-1 mb-6 z-10 relative">
            <span className="text-[10px] font-bold uppercase tracking-widest text-accent">
              STEP {currentStepInfo.num} OF {steps.length}
            </span>
            <h2 className="text-3xl font-extrabold tracking-tight text-text-primary sm:text-4xl">
              {currentStepInfo.title}
            </h2>
          </div>

          {/* Stepper Header */}
          <div className="relative z-10 mb-8 border-b border-border-color pb-6">
            <div className="relative flex flex-col md:flex-row items-stretch justify-between w-full gap-6 md:gap-6">
              {steps.map((tab, idx) => {
                const currentStepIdx = steps.findIndex(s => s.id === currentTab);
                const isCompleted = idx < currentStepIdx;
                const isActive = idx === currentStepIdx;
                const isClickable = getStepClickable(tab.id);

                return (
                  <button
                    key={tab.id}
                    type="button"
                    disabled={!isClickable || isSubmitting}
                    onClick={() => {
                      setCurrentTab(tab.id);
                      setError('');
                    }}
                    className={`flex-1 text-left glass-panel rounded-2xl py-7 px-6 min-h-[110px] transition-all duration-200 relative overflow-hidden group hover:-translate-y-[2px] ${
                      isActive 
                        ? 'bg-cyan-500/5 border-cyan-500/30 shadow-md'
                        : isCompleted
                          ? 'bg-emerald-500/5 border-emerald-500/25'
                          : 'hover:bg-text-primary/[0.01]'
                    } disabled:opacity-50 disabled:cursor-not-allowed`}
                  >
                    {/* Tiny side accent color bar */}
                    <div className={`absolute left-0 top-0 bottom-0 w-1 transition-all ${
                      isActive ? 'bg-accent' : isCompleted ? 'bg-emerald-400' : 'bg-transparent'
                    }`} />
                    
                    <div className="flex items-center justify-between mb-1.5 pl-1.5">
                      <span className={`text-[10px] font-bold uppercase tracking-widest ${
                        isActive ? 'text-accent' : isCompleted ? 'text-emerald-400' : 'text-text-secondary'
                      }`}>
                        {idx + 1}. {tab.title}
                      </span>
                      {isCompleted ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                      ) : isActive ? (
                        <div className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
                      ) : null}
                    </div>
                    <p className="text-[10px] font-normal text-text-secondary/70 pl-1.5 truncate group-hover:text-accent transition-colors">
                      {tab.description}
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
                  <h3 className="text-base font-semibold text-text-primary flex items-center gap-2 mb-2">
                    <FileText className="h-4.5 w-4.5 text-accent" />
                    Encrypted Payload (PDF)
                  </h3>
                  <div className="relative group/upload">
                    <input
                      id="pdf-upload"
                      type="file"
                      accept="application/pdf,.pdf"
                      onChange={async (e) => {
                        setSigPosition(null)
                        setNumPages(null)
                        setError('')
                        setUploadError('')
                        const selectedFile = e.target.files?.[0] ?? null
                        setFile(selectedFile)
                        if (selectedFile) {
                          setUploadTimestamp(new Date().toLocaleString())
                          
                          const isFilePdf = selectedFile.type === 'application/pdf' || selectedFile.name?.toLowerCase().endsWith('.pdf')
                          if (!isFilePdf) {
                            setUploadError('Only PDF documents are supported.')
                            return
                          }
                          
                          setIsValidating(true)
                          try {
                            await uploadDocument(selectedFile)
                            setUploadError('')
                            if (templateId) {
                              setTimeout(() => {
                                setCurrentTab('recipients')
                              }, 400)
                            }
                          } catch (err) {
                            let msg = '';
                            if (err?.response?.data) {
                              if (typeof err.response.data === 'string') {
                                msg = err.response.data;
                              } else if (err.response.data.detail) {
                                msg = err.response.data.detail;
                              } else if (err.response.data.file) {
                                msg = Array.isArray(err.response.data.file) ? err.response.data.file[0] : err.response.data.file;
                              } else {
                                const firstKey = Object.keys(err.response.data)[0];
                                if (firstKey) {
                                  const val = err.response.data[firstKey];
                                  msg = Array.isArray(val) ? val[0] : val;
                                }
                              }
                            }
                            if (!msg) {
                              msg = err?.message || 'Something went wrong. Please try again.';
                            }
                            setUploadError(msg)
                          } finally {
                            setIsValidating(false)
                          }
                        } else {
                          setUploadTimestamp(null)
                        }
                      }}
                      disabled={isSubmitting || isValidating}
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed z-20"
                    />
                    <div className={`flex flex-col items-center justify-center rounded-2xl border-2 border-dashed transition-all duration-300 p-8 sm:p-10 ${(file || existingDocName) ? 'border-cyan-500/50 bg-cyan-500/10' : 'border-border-color bg-card-bg group-hover/upload:border-cyan-500/30 group-hover/upload:bg-cyan-500/5'}`}>
                      <motion.div
                        animate={(file || existingDocName) ? { y: 0, scale: 1 } : { y: [0, -5, 0] }}
                        transition={(file || existingDocName) ? {} : { repeat: Infinity, duration: 3, ease: "easeInOut" }}
                        className={`mb-4 rounded-full p-4 ${(file || existingDocName) ? 'bg-cyan-500/20 text-accent' : 'bg-border-color text-text-secondary group-hover/upload:text-accent group-hover/upload:bg-cyan-500/10 transition-colors'}`}
                      >
                        {(file || existingDocName) ? <FileText className="h-8 w-8" /> : <UploadCloud className="h-8 w-8" />}
                      </motion.div>
                      {(file || existingDocName) ? (
                        <div className="text-center">
                          <span className="text-[10px] font-bold uppercase tracking-widest text-accent/70 mb-1.5 block">PDF Document • Secure upload</span>
                          <p className="text-sm font-medium text-accent">{file ? file.name : existingDocName}</p>
                          <p className="mt-1 text-xs text-accent/75">Ready for processing</p>
                        </div>
                      ) : (
                        <div className="text-center">
                          <span className="text-[10px] font-bold uppercase tracking-widest text-text-secondary/70 mb-1.5 block">PDF Document • Secure upload</span>
                          <p className="text-sm font-medium text-text-primary">Drag & drop or click to browse</p>
                          <p className="mt-1 text-xs text-text-secondary">Only PDF files are supported</p>
                        </div>
                      )}
                    </div>
                  </div>
                  {isValidating && (
                    <div className="mt-3 flex items-center gap-2 rounded-xl border border-cyan-500/20 bg-cyan-500/5 px-4 py-2.5 text-xs text-accent">
                      <span className="h-3.5 w-3.5 rounded-full border-2 border-accent border-t-transparent animate-spin shrink-0" />
                      <span>Validating document payload...</span>
                    </div>
                  )}
                  {uploadError && (
                    <div className="mt-3 flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/5 px-4 py-2.5 text-xs text-red-400">
                      <span className="font-bold shrink-0">⚠️ Error:</span>
                      <span>{uploadError}</span>
                    </div>
                  )}
                </div>

                <div className="flex justify-between items-center pt-6 border-t border-border-color">
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      disabled={!isDocumentValid || isSavingDraft}
                      onClick={handleSaveDraft}
                      className="inline-flex items-center justify-center gap-2 rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-secondary hover:text-cyan-400 px-5 py-3.5 text-xs font-bold transition-all duration-300 uppercase tracking-wider cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isSavingDraft ? 'Saving…' : draftSaved ? '✓ Saved' : 'Save Draft'}
                    </button>
                    <button
                      type="button"
                      onClick={openTemplateModal}
                      className="inline-flex items-center justify-center gap-2 rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-secondary hover:text-cyan-400 px-5 py-3.5 text-xs font-bold transition-all duration-300 uppercase tracking-wider cursor-pointer"
                    >
                      <SparkleIcon className="h-4 w-4 shrink-0 text-text-secondary" />
                      Save as Template
                    </button>
                  </div>
                  <button
                    type="button"
                    disabled={!isDocumentValid}
                    onClick={() => setCurrentTab('recipients')}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black px-6 py-3.5 text-xs font-bold transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] hover:shadow-[0_0_30px_rgba(34,211,238,0.45)] uppercase tracking-wider cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Continue to Recipients
                    <ArrowRight className="h-4 w-4 stroke-[2.5]" />
                  </button>
                </div>
              </div>
            )}

            {/* Step 2 Panel: Participants & Workflow */}
            {currentTab === 'recipients' && (
              <div className="space-y-6 pt-2">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <h3 className="text-base font-semibold tracking-wide text-text-primary flex items-center gap-2">
                      <UserPlus className="h-5 w-5 text-accent" />
                      Workflow Builder
                    </h3>
                    <p className="text-xs text-text-secondary mt-1">
                      Design a sequential routing workflow. Participants in each step will receive the document in order.
                    </p>
                  </div>
                  
                  <button
                    type="button"
                    onClick={addStep}
                    disabled={isSubmitting}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 hover:bg-cyan-500 hover:text-black hover:border-cyan-400 px-4 py-2.5 text-xs font-semibold text-accent transition-all duration-300 shadow-[0_0_15px_rgba(34,211,238,0.05)] cursor-pointer shrink-0 self-start sm:self-auto"
                  >
                    <Plus className="h-4 w-4" />
                    Add Workflow Step
                  </button>
                </div>

                <div className="space-y-4">
                  {workflowSteps.map((step, stepIdx) => (
                    <div key={step.stepNumber} className="flex flex-col items-center w-full">
                      {/* Step Card */}
                      <div className="w-full glass-panel rounded-2xl overflow-visible p-6 relative hover:-translate-y-1 hover:shadow-lg transition-all duration-200">
                        {/* Step Header */}
                        <div className="flex items-center justify-between mb-4 pb-3 border-b border-border-color">
                          <div className="flex items-center gap-3">
                            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-cyan-500/10 border border-cyan-500/30 text-xs font-bold text-accent">
                              {step.stepNumber}
                            </span>
                            <div>
                              <h4 className="text-sm font-semibold text-text-primary uppercase tracking-wider">
                                Step {step.stepNumber} Recipients
                              </h4>
                              <p className="text-[10px] text-text-secondary">Executes in parallel at this sequence number</p>
                            </div>
                          </div>

                          <div className="flex items-center gap-2">
                            {/* Move Up */}
                            <button
                              type="button"
                              disabled={isSubmitting || stepIdx === 0}
                              onClick={() => moveStep(step.stepNumber, 'up')}
                              className="rounded-lg p-1.5 text-text-secondary hover:text-accent hover:bg-cyan-500/10 transition-all disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer disabled:cursor-not-allowed animate-none"
                              title="Move Step Up"
                            >
                              <ChevronDown className="h-4 w-4 rotate-180" />
                            </button>

                            {/* Move Down */}
                            <button
                              type="button"
                              disabled={isSubmitting || stepIdx === workflowSteps.length - 1}
                              onClick={() => moveStep(step.stepNumber, 'down')}
                              className="rounded-lg p-1.5 text-text-secondary hover:text-accent hover:bg-cyan-500/10 transition-all disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer disabled:cursor-not-allowed animate-none"
                              title="Move Step Down"
                            >
                              <ChevronDown className="h-4 w-4" />
                            </button>

                            {/* Delete Step */}
                            <button
                              type="button"
                              disabled={isSubmitting || workflowSteps.length <= 1}
                              onClick={() => removeStep(step.stepNumber)}
                              className="rounded-lg p-1.5 text-text-secondary hover:text-red-400 hover:bg-red-500/10 transition-all disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer disabled:cursor-not-allowed animate-none"
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
                              <tr className="text-text-secondary uppercase text-[9px] font-bold tracking-wider bg-bg-primary/5 border-b border-border-color">
                                <th className="px-4 py-2 min-w-[200px]">Name</th>
                                <th className="px-4 py-2 min-w-[220px]">Email Address</th>
                                <th className="px-4 py-2 min-w-[200px]">Role</th>
                                <th className="px-4 py-2 text-center w-[80px]">Actions</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-border-color">
                              {step.participants.length === 0 ? (
                                <tr>
                                  <td colSpan="4" className="px-4 py-8 text-center text-text-secondary">
                                    <div className="flex flex-col items-center justify-center">
                                      <User className="h-6 w-6 text-text-secondary/55 mb-1 stroke-[1.5]" />
                                      <p className="text-xs font-medium text-text-secondary">No participants in this step.</p>
                                      <button
                                        type="button"
                                        onClick={() => addParticipantToStep(step.stepNumber)}
                                        className="mt-2 text-[10px] text-accent hover:underline font-semibold"
                                      >
                                        + Add Participant
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              ) : (
                                step.participants.map((p) => (
                                  <tr key={p.id} className="hover:bg-bg-primary/30 transition-colors group/row">
                                    <td className="px-3 py-2.5 align-middle">
                                      <div className="relative">
                                        <User className="absolute left-3 h-4 w-4 text-text-secondary/60 top-1/2 -translate-y-1/2" />
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
                                        <Mail className={`absolute left-3 h-4 w-4 top-1/2 -translate-y-1/2 ${participantErrors[p.id] ? 'text-red-400' : 'text-text-secondary/60'}`} />
                                        <input
                                          type="email"
                                          value={p.email}
                                          onChange={(e) => {
                                            updateParticipant(step.stepNumber, p.id, 'email', e.target.value)
                                            // Clear inline error as user types
                                            if (participantErrors[p.id]) {
                                              setParticipantErrors(prev => {
                                                const next = { ...prev }
                                                delete next[p.id]
                                                return next
                                              })
                                            }
                                          }}
                                          placeholder="Email Address"
                                          disabled={isSubmitting}
                                          className={`${cellInputClass} pl-9 font-mono ${
                                            participantErrors[p.id]
                                              ? 'border-red-500/60 focus:border-red-500/60 focus:ring-red-500/20 bg-red-950/10'
                                              : ''
                                          }`}
                                        />
                                      </div>
                                      {participantErrors[p.id] && (
                                        <p className="mt-1 px-1 text-[10px] text-red-400 font-medium flex items-center gap-1">
                                          <span aria-hidden="true">⚠</span> {participantErrors[p.id]}
                                        </p>
                                      )}
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
                                        className="rounded-lg p-2 text-text-secondary hover:text-red-400 hover:bg-red-500/10 transition-all cursor-pointer inline-flex items-center justify-center cursor-pointer"
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
                              className="inline-flex items-center gap-1.5 rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-primary hover:text-cyan-400 px-3 py-1.5 text-xs font-semibold transition-all duration-200 cursor-pointer"
                            >
                              <Plus className="h-3 w-3" />
                              Add Recipient to Step {step.stepNumber}
                            </button>
                          </div>
                        )}
                      </div>

                      {/* Down Arrow separator between steps */}
                      {stepIdx < workflowSteps.length - 1 && (
                        <div className="flex flex-col items-center my-3 relative">
                          <div className="h-8 w-[1px] bg-gradient-to-b from-cyan-500/50 to-transparent" />
                          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-cyan-500/10 border border-cyan-500/30 text-accent shadow-[0_0_10px_rgba(34,211,238,0.15)] backdrop-blur-md">
                            <ChevronDown className="h-4 w-4 animate-pulse" />
                          </div>
                          <div className="h-8 w-[1px] bg-gradient-to-t from-cyan-500/50 to-transparent" />
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                {/* Back and Continue Buttons */}
                <div className="flex justify-between pt-6 border-t border-border-color">
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={() => setCurrentTab('documents')}
                      className="inline-flex items-center justify-center gap-2 rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-secondary hover:text-cyan-400 px-6 py-3.5 text-xs font-bold transition-all duration-300 uppercase tracking-wider cursor-pointer"
                    >
                      Back
                    </button>
                    <button
                      type="button"
                      disabled={isSavingDraft}
                      onClick={handleSaveDraft}
                      className="inline-flex items-center justify-center gap-2 rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-secondary hover:text-cyan-400 px-5 py-3.5 text-xs font-bold transition-all duration-300 uppercase tracking-wider cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isSavingDraft ? 'Saving…' : draftSaved ? '✓ Saved' : 'Save Draft'}
                    </button>
                    <button
                      type="button"
                      onClick={openTemplateModal}
                      className="inline-flex items-center justify-center gap-2 rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-secondary hover:text-cyan-400 px-5 py-3.5 text-xs font-bold transition-all duration-300 uppercase tracking-wider cursor-pointer"
                    >
                      <SparkleIcon className="h-4 w-4 shrink-0 text-text-secondary" />
                      Save as Template
                    </button>
                  </div>

                  <div className="flex flex-col items-end gap-1">
                    <button
                      type="button"
                      onClick={() => {
                        // Validate all participant emails inline before advancing
                        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
                        const errors = {}
                        workflowSteps.forEach(step => {
                          step.participants.forEach(p => {
                            const email = p.email.trim()
                            if (!email) {
                              errors[p.id] = 'Email address is required.'
                            } else if (!emailRegex.test(email)) {
                              errors[p.id] = 'Enter a valid email address.'
                            }
                          })
                        })
                        if (Object.keys(errors).length > 0) {
                          setParticipantErrors(errors)
                          return
                        }
                        setParticipantErrors({})
                        if (!hasSignerRole) return
                        setCurrentTab('prepare')
                      }}
                      className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black px-6 py-3.5 text-xs font-bold transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] hover:shadow-[0_0_30px_rgba(34,211,238,0.45)] uppercase tracking-wider cursor-pointer"
                    >
                      Continue to Prepare
                      <ArrowRight className="h-4 w-4 stroke-[2.5]" />
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

            {/* Step 3 Panel: Prepare */}
            {currentTab === 'prepare' && (
              <div className="space-y-6 pt-2">
                <div>
                  <h3 className="text-base font-semibold tracking-wide text-text-primary flex items-center gap-2">
                    <Crosshair className="h-5 w-5 text-accent" />
                    Place Fields on Document
                  </h3>
                  <p className="text-xs text-text-secondary mt-1">
                    Select a recipient, choose the field type, and click directly on the PDF pages below to position signature fields.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {/* Summary Card 1: Fields Count */}
                  <div className="glass-panel rounded-2xl p-5 flex flex-col justify-between min-h-[140px] relative hover:-translate-y-1 hover:shadow-lg transition-all duration-200">
                    <div className="flex justify-between items-start">
                      <span className="text-[10px] uppercase font-bold tracking-widest text-text-secondary">Summary</span>
                      <FileText className="h-5 w-5 text-accent" />
                    </div>
                    <div className="mt-4 space-y-1">
                      <h4 className="text-sm font-bold text-text-primary">Total Placed Fields</h4>
                      <p className="text-[10px] text-text-secondary">Signature fields placed on document pages.</p>
                      <div className="text-3xl font-light text-accent font-mono mt-2">
                        {placedFields.length}
                      </div>
                    </div>
                  </div>

                  {/* Summary Card 2: Instructions */}
                  <div className="glass-panel rounded-2xl p-5 flex flex-col justify-between min-h-[140px] md:col-span-2 relative hover:-translate-y-1 hover:shadow-lg transition-all duration-200">
                    <div className="flex justify-between items-start">
                      <span className="text-[10px] uppercase font-bold tracking-widest text-text-secondary">Instructions</span>
                      <SparkleIcon className="h-5 w-5 text-violet-400" />
                    </div>
                    <div className="mt-4 space-y-1">
                      <h4 className="text-sm font-bold text-text-primary">How to position signature zones</h4>
                      <p className="text-xs text-text-secondary leading-relaxed">
                        1. Select a recipient from the dropdown below or in the document editor.<br />
                        2. Scroll down to the document editor below.<br />
                        3. Click on any page where you want the signer to sign.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Placed Fields List / Summary */}
                <div className="glass-panel rounded-2xl p-6 space-y-4 hover:-translate-y-1 hover:shadow-lg transition-all duration-200">
                  <div>
                    <h4 className="text-sm font-bold uppercase tracking-wider text-text-primary flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-accent" />
                      Placed Fields Summary
                    </h4>
                    <p className="text-[10px] text-text-secondary mt-0.5">List of all active signature zones placed on the document.</p>
                  </div>

                  {placedFields.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-border-color bg-card-bg/40 p-8 text-center text-xs text-text-secondary">
                      No fields placed yet. Scroll down to position your first signature zone on the PDF page.
                    </div>
                  ) : (
                    <div className="max-h-60 overflow-y-auto custom-scrollbar divide-y divide-border-color">
                      {placedFields.map((field) => (
                        <div key={field.id} className="py-3 flex items-center justify-between text-xs hover:bg-cyan-500/[0.02] px-2 rounded-xl transition-all">
                          <div className="flex items-center gap-4">
                            <span className="flex h-5 w-5 items-center justify-center rounded bg-cyan-500/10 text-[10px] font-bold text-accent">
                              P{field.page}
                            </span>
                            <div>
                              <span className="font-semibold text-text-primary">{field.participant_name || 'Signer'}</span>
                              <span className="text-[10px] text-text-secondary font-mono ml-2">({field.participant_email})</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-4">
                            <span className="text-[10px] font-mono text-text-secondary">
                              X: {field.x_ratio.toFixed(2)} Y: {field.y_ratio.toFixed(2)}
                            </span>
                            <button
                              type="button"
                              onClick={() => removeField(field.id)}
                              className="rounded-lg p-1 text-text-secondary hover:text-red-400 hover:bg-red-500/10 transition-all cursor-pointer"
                              title="Delete Field"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Back and Continue Buttons */}
                <div className="flex justify-between pt-6 border-t border-border-color">
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={() => setCurrentTab('recipients')}
                      className="inline-flex items-center justify-center gap-2 rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-secondary hover:text-cyan-400 px-6 py-3.5 text-xs font-bold transition-all duration-300 uppercase tracking-wider cursor-pointer"
                    >
                      Back
                    </button>
                    <button
                      type="button"
                      disabled={isSavingDraft}
                      onClick={handleSaveDraft}
                      className="inline-flex items-center justify-center gap-2 rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-secondary hover:text-cyan-400 px-5 py-3.5 text-xs font-bold transition-all duration-300 uppercase tracking-wider cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isSavingDraft ? 'Saving…' : draftSaved ? '✓ Saved' : 'Save Draft'}
                    </button>
                    <button
                      type="button"
                      onClick={openTemplateModal}
                      className="inline-flex items-center justify-center gap-2 rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-secondary hover:text-cyan-400 px-5 py-3.5 text-xs font-bold transition-all duration-300 uppercase tracking-wider cursor-pointer"
                    >
                      <SparkleIcon className="h-4 w-4 shrink-0 text-text-secondary" />
                      Save as Template
                    </button>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <button
                      type="button"
                      disabled={!isSignaturePlaced}
                      onClick={() => setCurrentTab('settings')}
                      className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black px-6 py-3.5 text-xs font-bold transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] hover:shadow-[0_0_30px_rgba(34,211,238,0.45)] uppercase tracking-wider cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Continue to Settings
                      <ArrowRight className="h-4 w-4 stroke-[2.5]" />
                    </button>
                    {!isSignaturePlaced && (
                      <p className="text-[10px] text-amber-400 font-semibold mt-1">
                        Please scroll down and place at least one signature zone.
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Step 4 Panel: Request Settings */}
            {currentTab === 'settings' && (
              <div className="space-y-6 pt-2">
                <div>
                  <h3 className="text-base font-semibold tracking-wide text-text-primary flex items-center gap-2">
                    <Settings className="h-5 w-5 text-accent" />
                    Request Settings
                  </h3>
                  <p className="text-xs text-text-secondary mt-1">
                    Configure request alerts, document distribution, and delivery settings before dispatching.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {/* Switch 1: Reminders */}
                  <div className="glass-panel rounded-2xl p-5 flex flex-col justify-between min-h-[140px] relative hover:-translate-y-1 hover:shadow-lg transition-all duration-200">
                    <div className="flex justify-between items-start">
                      <span className="text-[10px] uppercase font-bold tracking-widest text-text-secondary">Alerts</span>
                      <Bell className={`h-5 w-5 ${sendReminders ? 'text-accent' : 'text-text-secondary'}`} />
                    </div>
                    <div className="mt-4 space-y-3">
                      <div>
                        <h4 className="text-sm font-bold text-text-primary">Automatic Reminders</h4>
                        <p className="text-[10px] text-text-secondary mt-0.5">Send status email alerts to pending signers.</p>
                      </div>
                      <label className="flex items-center gap-2 cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={sendReminders}
                          onChange={(e) => setSendReminders(e.target.checked)}
                          disabled={isSubmitting}
                          className="sr-only peer"
                        />
                        <div className="relative w-10 h-6 bg-text-secondary/20 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-text-secondary after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-cyan-500 peer-checked:after:bg-white peer-checked:after:border-cyan-400" />
                        <span className="text-xs text-text-secondary peer-checked:text-accent font-medium">
                          {sendReminders ? 'Enabled' : 'Disabled'}
                        </span>
                      </label>
                    </div>
                  </div>

                  {/* Switch 2: Final Document Delivery */}
                  <div className="glass-panel rounded-2xl p-5 flex flex-col justify-between min-h-[140px] relative hover:-translate-y-1 hover:shadow-lg transition-all duration-200">
                    <div className="flex justify-between items-start">
                      <span className="text-[10px] uppercase font-bold tracking-widest text-text-secondary">Distribution</span>
                      <Share2 className={`h-5 w-5 ${sendFinalEmail ? 'text-accent' : 'text-text-secondary'}`} />
                    </div>
                    <div className="mt-4 space-y-3">
                      <div>
                        <h4 className="text-sm font-bold text-text-primary">Final Delivery</h4>
                        <p className="text-[10px] text-text-secondary mt-0.5">Deliver completed copy to all participants.</p>
                      </div>
                      <label className="flex items-center gap-2 cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={sendFinalEmail}
                          onChange={(e) => setSendFinalEmail(e.target.checked)}
                          disabled={isSubmitting}
                          className="sr-only peer"
                        />
                        <div className="relative w-10 h-6 bg-text-secondary/20 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-text-secondary after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-cyan-500 peer-checked:after:bg-white peer-checked:after:border-cyan-400" />
                        <span className="text-xs text-text-secondary peer-checked:text-accent font-medium">
                          {sendFinalEmail ? 'Deliver' : 'Do Not Deliver'}
                        </span>
                      </label>
                    </div>
                  </div>

                  {/* Switch 3: Allow Printing */}
                  <div className="glass-panel rounded-2xl p-5 flex flex-col justify-between min-h-[140px] relative hover:-translate-y-1 hover:shadow-lg transition-all duration-200">
                    <div className="flex justify-between items-start">
                      <span className="text-[10px] uppercase font-bold tracking-widest text-text-secondary">Permissions</span>
                      <Printer className={`h-5 w-5 ${allowPrinting ? 'text-accent' : 'text-text-secondary'}`} />
                    </div>
                    <div className="mt-4 space-y-3">
                      <div>
                        <h4 className="text-sm font-bold text-text-primary">Allow Printing</h4>
                        <p className="text-[10px] text-text-secondary mt-0.5">Allow recipients to download or print copies.</p>
                      </div>
                      <label className="flex items-center gap-2 cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={allowPrinting}
                          onChange={(e) => setAllowPrinting(e.target.checked)}
                          disabled={isSubmitting}
                          className="sr-only peer"
                        />
                        <div className="relative w-10 h-6 bg-text-secondary/20 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-text-secondary after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-cyan-500 peer-checked:after:bg-white peer-checked:after:border-cyan-400" />
                        <span className="text-xs text-text-secondary peer-checked:text-accent font-medium">
                          {allowPrinting ? 'Allowed' : 'Restricted'}
                        </span>
                      </label>
                    </div>
                  </div>
                </div>

                {/* 4. Additional Recipients Input Section */}
                <div className="glass-panel rounded-2xl p-6 space-y-4 hover:-translate-y-1 hover:shadow-lg transition-all duration-200">
                  <div>
                    <h4 className="text-base font-semibold text-text-primary flex items-center gap-2">
                      <Mail className="h-4 w-4 text-accent" />
                      Additional Recipients
                    </h4>
                    <p className="text-[10px] text-text-secondary mt-0.5">Receive a carbon copy (CC) of the completed transaction record.</p>
                  </div>

                  <div className="flex flex-col sm:flex-row gap-3">
                    <div className="flex-1 relative">
                      <Mail className="absolute left-3 h-4 w-4 text-text-secondary/60 top-1/2 -translate-y-1/2" />
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
                      className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-card-bg hover:bg-cyan-500 hover:text-black border border-border-color hover:border-cyan-400 px-5 py-3.5 text-xs font-semibold text-text-primary transition-all duration-300 cursor-pointer shrink-0"
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
                <div className="flex justify-between pt-6 border-t border-border-color">
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={() => setCurrentTab('prepare')}
                      className="inline-flex items-center justify-center gap-2 rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-secondary hover:text-cyan-400 px-6 py-3.5 text-xs font-bold transition-all duration-300 uppercase tracking-wider cursor-pointer"
                    >
                      Back
                    </button>
                    <button
                      type="button"
                      disabled={isSavingDraft}
                      onClick={handleSaveDraft}
                      className="inline-flex items-center justify-center gap-2 rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-secondary hover:text-cyan-400 px-5 py-3.5 text-xs font-bold transition-all duration-300 uppercase tracking-wider cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isSavingDraft ? 'Saving…' : draftSaved ? '✓ Saved' : 'Save Draft'}
                    </button>
                    <button
                      type="button"
                      onClick={openTemplateModal}
                      className="inline-flex items-center justify-center gap-2 rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-secondary hover:text-cyan-400 px-5 py-3.5 text-xs font-bold transition-all duration-300 uppercase tracking-wider cursor-pointer"
                    >
                      <SparkleIcon className="h-4 w-4 shrink-0 text-text-secondary" />
                      Save as Template
                    </button>
                  </div>
                  <button
                    type="button"
                    onClick={() => setCurrentTab('review')}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black px-6 py-3.5 text-xs font-bold transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] hover:shadow-[0_0_30px_rgba(34,211,238,0.45)] uppercase tracking-wider cursor-pointer"
                  >
                    Continue to Review
                    <ArrowRight className="h-4 w-4 stroke-[2.5]" />
                  </button>
                </div>
              </div>
            )}

            {/* Step 4 Panel: Review & Prepare */}
            {currentTab === 'review' && (
              <div className="space-y-6 pt-2">
                <div>
                  <h3 className="text-base font-semibold tracking-wide text-text-primary flex items-center gap-2">
                    <Sparkles className="h-5 w-5 text-accent" />
                    Review & Prepare
                  </h3>
                  <p className="text-xs text-text-secondary mt-1">
                    Preflight checklist validation and configuration summary before dispatch.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Grid Item 1: Workflow Ready Summary */}
                  <div className="glass-panel rounded-2xl p-6 flex flex-col justify-between hover:-translate-y-1 transition-all duration-200 hover:shadow-lg">
                    <div className="space-y-4">
                      <div className="flex items-center justify-between border-b border-border-color pb-3">
                        <h4 className="text-sm font-bold uppercase tracking-wider text-text-primary flex items-center gap-2">
                          <Sparkles className="h-4 w-4 text-violet-400" />
                          Workflow Ready
                        </h4>
                        <span className="text-[10px] text-text-secondary font-mono uppercase">Routing Overview</span>
                      </div>
                      
                      <div className="flex items-center justify-between bg-card-bg border border-border-color rounded-2xl p-4 shadow-sm hover:-translate-y-0.5 hover:shadow-md transition-all duration-200">
                        <div className="space-y-0.5">
                          <span className="text-[10px] text-text-secondary uppercase tracking-widest font-bold">Participants Enrolled</span>
                          <h4 className="text-xs font-bold text-text-primary">Enrolled routing sequence</h4>
                        </div>
                        <span className="text-2xl font-light text-violet-400 font-mono">
                          {workflowSteps.flatMap(s => s.participants).length}
                        </span>
                      </div>

                      {/* Step-by-step visual routing timeline */}
                      <div className="space-y-3 pt-2">
                        {workflowSteps.map((step, stepIdx) => {
                          const isFirst = step.stepNumber === 1;
                          return (
                            <div key={step.stepNumber} className="relative pl-6 border-l border-border-color space-y-1">
                              {/* Indicator dot */}
                              <div className={`absolute -left-[5.5px] top-1.5 h-2.5 w-2.5 rounded-full border border-bg-primary ${
                                isFirst ? 'bg-violet-400 shadow-[0_0_8px_rgba(167,139,250,0.5)]' : 'bg-zinc-700'
                              }`} />
                              
                              <div className="flex items-center justify-between text-xs">
                                <span className="font-semibold text-text-primary">Step {step.stepNumber}</span>
                                <span className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-bold uppercase ${
                                  isFirst ? 'bg-violet-500/10 text-violet-400 border border-violet-500/20' : 'bg-card-bg text-text-secondary border border-border-color'
                                }`}>
                                  {isFirst ? 'Active on launch' : 'Pending'}
                                </span>
                              </div>
                              <div className="flex flex-wrap gap-1.5 pt-0.5">
                                {step.participants.map(p => (
                                  <span key={p.id} className={`inline-flex px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider border ${
                                    p.role === 'signer' ? 'bg-cyan-500/10 text-accent border-cyan-500/20' :
                                    p.role === 'approver' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                                    p.role === 'reviewer' ? 'bg-violet-500/10 text-violet-400 border-violet-500/20' :
                                    'bg-card-bg text-text-primary border-border-color'
                                  }`}>
                                    {p.name || 'Unnamed'} ({p.role})
                                  </span>
                                ))}
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      <div className="flex justify-between items-center bg-violet-500/10 border border-violet-500/20 rounded-xl px-4 py-3 text-xs mt-4">
                        <span className="text-text-secondary font-semibold">Launch Status</span>
                        <span className="text-violet-400 font-bold uppercase tracking-wider animate-pulse">
                          Ready To Launch
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Grid Item 2: Launch Checklist */}
                  <div className="glass-panel rounded-2xl p-6 hover:-translate-y-1 transition-all duration-200 hover:shadow-lg">
                    <div className="flex items-center justify-between border-b border-border-color pb-3 mb-4">
                      <h4 className="text-sm font-bold uppercase tracking-wider text-text-primary flex items-center gap-2">
                        <CheckCircle2 className="h-4 w-4 text-accent" />
                        Launch Checklist
                      </h4>
                      <span className="text-[10px] text-text-secondary font-mono uppercase">Preflight Check</span>
                    </div>

                    <div className="space-y-3">
                      {[
                        { 
                          label: 'Document Ready', 
                          isValid: isDocumentValid, 
                          desc: 'Valid PDF payload is uploaded and parsed.' 
                        },
                        { 
                          label: 'Participants Configured', 
                          isValid: isWorkflowValid, 
                          desc: 'All recipient names and email addresses are valid.' 
                        },
                        { 
                          label: 'Workflow Configured', 
                          isValid: isWorkflowValid && hasSignerRole, 
                          desc: 'Sequential routing steps and signer roles are configured.' 
                        },
                        { 
                          label: 'Request Settings Configured', 
                          isValid: settingsValid, 
                          desc: 'Delivery settings and notifications set to default.' 
                        },
                        { 
                          label: 'Signature Zone Placed', 
                          isValid: isSignaturePlaced, 
                          desc: 'Signature placement coordinates selected on document.' 
                        },
                        { 
                          label: 'Ready To Send', 
                          isValid: isDocumentValid && isWorkflowValid && hasSignerRole && isSignaturePlaced && settingsValid, 
                          desc: 'Workflow is verified and ready for dispatch.' 
                        }
                      ].map((item, idx) => (
                        <div 
                          key={idx} 
                          className={`flex items-start gap-3 rounded-xl p-3 border transition-all duration-200 hover:-translate-y-0.5 ${
                            item.isValid 
                              ? 'bg-emerald-500/[0.02] border-emerald-500/10 text-emerald-400 hover:border-emerald-500/20' 
                              : 'bg-red-500/[0.02] border-red-500/10 text-red-400 hover:border-red-500/20'
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
                            <div className={`text-xs font-semibold ${item.isValid ? 'text-emerald-400' : 'text-text-secondary'}`}>
                              {item.label}
                            </div>
                            <p className="text-[10px] text-text-secondary mt-0.5">{item.desc}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Back and Send buttons */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-6 border-t border-border-color">
                  <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
                    <button
                      type="button"
                      onClick={() => setCurrentTab('settings')}
                      disabled={isSubmitting}
                      className="inline-flex items-center justify-center gap-2 rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-secondary hover:text-cyan-400 px-6 py-3.5 text-xs font-bold transition-all duration-300 uppercase tracking-wider cursor-pointer disabled:opacity-50"
                    >
                      Back
                    </button>
                    <button
                      type="button"
                      disabled={isSavingDraft}
                      onClick={handleSaveDraft}
                      className="inline-flex items-center justify-center gap-2 rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-secondary hover:text-cyan-400 px-5 py-3.5 text-xs font-bold transition-all duration-300 uppercase tracking-wider cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isSavingDraft ? 'Saving…' : draftSaved ? '✓ Saved' : 'Save Draft'}
                    </button>
                    <button
                      type="button"
                      onClick={openTemplateModal}
                      className="inline-flex items-center justify-center gap-2 rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-secondary hover:text-cyan-400 px-5 py-3.5 text-xs font-bold transition-all duration-300 uppercase tracking-wider cursor-pointer"
                    >
                      <SparkleIcon className="h-4 w-4 shrink-0 text-text-secondary" />
                      Save as Template
                    </button>
                  </div>

                  <div className="flex flex-col items-end gap-2">
                    <button
                      type="submit"
                      disabled={isSubmitting || !isDocumentValid || !isWorkflowValid || !hasSignerRole || !isSignaturePlaced || !settingsValid}
                      className="group relative inline-flex items-center justify-center gap-2 overflow-hidden rounded-xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 disabled:cursor-not-allowed px-8 py-3.5 text-xs font-bold text-black transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] hover:shadow-[0_0_30px_rgba(34,211,238,0.45)] uppercase tracking-wider cursor-pointer"
                    >
                      <span className="relative z-10 flex items-center gap-2">
                        {isSubmitting ? 'Launching Workflow…' : 'Send Package'}
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
          </AnimatePresence>
          </>
          )}
        </div>
      </motion.div>

      {/* ── Signature position selector ── */}
      <AnimatePresence>
        {!sentPackageInfo && previewUrl && currentTab === 'prepare' && (
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 40 }}
            transition={{ duration: 0.6, delay: 0.1, ease: "easeOut" }}
            className="mt-8 glass-panel rounded-3xl p-8 sm:p-12"
          >
            <div className="mb-8 grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-6 items-end">
              <div>
                <div className="inline-flex items-center gap-2 rounded-full border border-violet-500/30 bg-violet-500/10 px-3 py-1 text-xs font-medium uppercase tracking-widest text-violet-400 mb-3">
                  <Crosshair className="h-3.5 w-3.5" />
                  Spatial Placement
                </div>
                <h2 className="text-base font-semibold tracking-wide text-text-primary font-sans">Place Fields on Document</h2>
                <p className="mt-1 text-xs text-text-secondary">Select recipient and field type, then click on the PDF to place fields.</p>
              </div>

              {/* Selectors and Toolbar */}
              <div className="flex flex-wrap gap-4 lg:justify-end items-stretch sm:items-center">
                {/* Coordinate readout */}
                {sigPosition && (
                  <div className="flex items-center gap-3 rounded-2xl border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 backdrop-blur-md self-end lg:self-center">
                    <div className="flex gap-3 text-[10px] font-mono text-accent">
                      <div><span className="text-cyan-600">P:</span>{sigPosition.page}</div>
                      <div><span className="text-cyan-600">X:</span>{sigPosition.x_ratio.toFixed(2)}</div>
                      <div><span className="text-cyan-600">Y:</span>{sigPosition.y_ratio.toFixed(2)}</div>
                    </div>
                  </div>
                )}

                {/* Participant Selector */}
                <div className="flex flex-col gap-1">
                  <span className="text-[9px] uppercase font-bold tracking-widest text-text-secondary">Recipient</span>
                  <select
                    value={activeParticipantEmail}
                    onChange={(e) => setActiveParticipantEmail(e.target.value)}
                    className="rounded-xl border border-border-color bg-card-bg text-xs text-text-primary px-3 py-2 outline-none focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/20 max-w-[200px] cursor-pointer"
                  >
                    <option value="">-- Choose Recipient --</option>
                    {allParticipants.map((p) => (
                      <option key={p.email} value={p.email}>
                        {p.name} ({p.role})
                      </option>
                    ))}
                  </select>
                </div>

                {/* Field Type Toolbar */}
                <div className="flex flex-col gap-1">
                  <span className="text-[9px] uppercase font-bold tracking-widest text-text-secondary">Field Type</span>
                  <div className="flex rounded-xl bg-bg-primary/5 border border-border-color p-0.5">
                    {/* Note: Current MVP supports only signature placement.
                        Future planned field types:
                        - date
                        - text
                        - checkbox
                        These remain supported in the data model for future enterprise workflow expansion. */}
                    {[
                      { id: 'signature', label: 'Signature' },
                    ].map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => setSelectedFieldType(t.id)}
                        className={`px-2.5 py-1.5 rounded-lg text-[9px] font-bold uppercase tracking-wider transition-all ${
                          selectedFieldType === t.id
                            ? 'text-accent bg-cyan-500/10 border border-cyan-500/20'
                            : 'text-text-secondary hover:text-text-primary'
                        }`}
                      >
                        {t.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div className="relative overflow-auto rounded-2xl border border-border-color bg-bg-primary py-8 custom-scrollbar shadow-inner max-h-[700px]">
              <Document
                file={previewUrl}
                onLoadSuccess={({ numPages: n }) => setNumPages(n)}
                loading={
                  <div className="flex h-64 flex-col items-center justify-center gap-4 text-accent">
                    <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
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
                        className="relative mx-auto mb-8 w-fit cursor-crosshair shadow-lg border border-border-color last:mb-0 transition-transform hover:scale-[1.01] duration-500"
                        style={{ userSelect: 'none' }}
                        onClick={(e) => handlePageClick(pageNumber, e)}
                      >
                        {/* Glowing border if selected */}
                        {isSelected && (
                          <div className="absolute inset-0 border-2 border-cyan-500 shadow-[0_0_30px_rgba(34,211,238,0.3)] z-0 pointer-events-none" />
                        )}

                        <div className="absolute left-4 top-4 z-10 rounded-lg border border-border-color bg-card-bg/85 px-3 py-1.5 text-xs font-mono text-text-primary backdrop-blur-md">
                          {pageNumber} / {numPages}
                        </div>

                        <Page
                          pageNumber={pageNumber}
                          renderTextLayer={true}
                          renderAnnotationLayer={true}
                          className="block relative z-0"
                        />

                        {/* Render all placed fields */}
                        <AnimatePresence>
                          {placedFields.filter(f => f.page === pageNumber).map((f) => (
                            <motion.div
                              key={f.id}
                              initial={{ scale: 0, opacity: 0 }}
                              animate={{ scale: 1, opacity: 1 }}
                              style={{
                                position: 'absolute',
                                left: f.x !== undefined ? f.x : `${f.x_ratio * 100}%`,
                                top: f.y !== undefined ? f.y : `${f.y_ratio * 100}%`,
                                zIndex: 20,
                              }}
                            >
                              <div className="absolute left-0 top-0 -translate-x-1/2 -translate-y-1/2 flex items-center justify-center group/field">
                                <div className="relative flex h-5 w-5 items-center justify-center">
                                  <div className="absolute inset-0 rounded-full bg-cyan-500 animate-ping opacity-30" />
                                  <div className="relative h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_10px_#22d3ee]" />
                                </div>
                                <div className="absolute left-0 top-3 -translate-x-1/2 pt-1 flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-cyan-500/50 bg-card-bg/95 px-2.5 py-1 text-[9px] font-bold tracking-wider text-accent shadow-[0_0_20px_rgba(34,211,238,0.25)] backdrop-blur-md uppercase">
                                  <span>{f.field_type}</span>
                                  <span className="text-zinc-500">|</span>
                                  <span className="text-text-primary max-w-[80px] truncate" title={f.participant_name}>{f.participant_name}</span>
                                  <button
                                    type="button"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      removeField(f.id);
                                    }}
                                    className="ml-1 rounded-full p-0.5 hover:bg-white/10 text-text-secondary hover:text-red-400 transition-colors pointer-events-auto cursor-pointer"
                                  >
                                    <X className="h-2.5 w-2.5" />
                                  </button>
                                </div>
                              </div>
                            </motion.div>
                          ))}

                          {/* Fallback to legacy single signature marker if no fields are placed */}
                          {placedFields.length === 0 && isSelected && (
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
                              <div className="absolute left-0 top-0 -translate-x-1/2 -translate-y-1/2 flex items-center justify-center">
                                <div className="relative flex h-5 w-5 items-center justify-center">
                                  <div className="absolute inset-0 rounded-full bg-cyan-500 animate-ping opacity-50" />
                                  <div className="relative h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_10px_#22d3ee]" />
                                </div>
                              </div>
                              <div className="absolute left-0 top-3 -translate-x-1/2 pt-1">
                                <div className="whitespace-nowrap rounded-lg border border-cyan-500/50 bg-card-bg/95 px-3 py-1 text-[10px] font-bold tracking-widest text-accent shadow-[0_0_20px_rgba(34,211,238,0.25)] backdrop-blur-md uppercase">
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

      {/* ── Save as Template Modal ── */}
      <AnimatePresence>
        {isTemplateModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            {/* Backdrop blur */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsTemplateModalOpen(false)}
              className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            />

            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 15 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 15 }}
              className="relative w-full max-w-lg overflow-hidden rounded-3xl glass-panel p-6 sm:p-8 z-10"
            >
              <button
                type="button"
                onClick={() => setIsTemplateModalOpen(false)}
                className="absolute right-6 top-6 rounded-full bg-border-color p-1 text-text-secondary hover:bg-bg-primary/20 hover:text-text-primary transition-colors cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>

              <div className="mb-6 space-y-1">
                <div className="inline-flex items-center gap-1.5 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-accent animate-none">
                  <SparkleIcon className="h-3 w-3" />
                  Save Workflow Blueprint
                </div>
                <h3 className="text-xl font-light text-text-primary sm:text-2xl">Save as Reusable Template</h3>
                <p className="text-xs text-text-secondary">Persist the current workflow steps, roles, and settings configuration as a blueprint template.</p>
              </div>

              <form onSubmit={handleSaveTemplateSubmit} className="space-y-4">
                <div className="space-y-1.5">
                  <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wide">Template Name</label>
                  <input
                    type="text"
                    value={templateName}
                    onChange={(e) => setTemplateName(e.target.value)}
                    placeholder="Standard NDA, Employment Offer, etc."
                    className="w-full rounded-xl border border-border-color bg-card-bg px-4 py-3 text-xs text-text-primary outline-none transition-all focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/20"
                    required
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wide">Description</label>
                  <textarea
                    rows="3"
                    value={templateDescription}
                    onChange={(e) => setTemplateDescription(e.target.value)}
                    placeholder="Describe this reusable business workflow template..."
                    className="w-full rounded-xl border border-border-color bg-card-bg px-4 py-3 text-xs text-text-primary outline-none transition-all focus:border-cyan-500/40 resize-none focus:ring-1 focus:ring-cyan-500/20"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wide">Category</label>
                    <select
                      value={templateCategory}
                      onChange={(e) => setTemplateCategory(e.target.value)}
                      className="w-full rounded-xl border border-border-color bg-card-bg px-4 py-3 text-xs text-text-primary outline-none cursor-pointer focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/20"
                    >
                      {['General', 'Legal', 'HR', 'Finance', 'Operations'].map(c => (
                        <option key={c} value={c} className="bg-card-bg text-text-primary">{c}</option>
                      ))}
                    </select>
                  </div>

                  <div className="space-y-1.5">
                    <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wide">Visibility</label>
                    <select
                      value={templateVisibility}
                      onChange={(e) => setTemplateVisibility(e.target.value)}
                      className="w-full rounded-xl border border-border-color bg-card-bg px-4 py-3 text-xs text-text-primary outline-none cursor-pointer focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/20"
                    >
                      <option value="private" className="bg-card-bg text-text-primary">Private (Self)</option>
                      <option value="public" className="bg-card-bg text-text-primary">Public / Shared</option>
                    </select>
                  </div>
                </div>

                {templateModalError && (
                  <p className="text-xs font-semibold text-red-400 mt-2">{templateModalError}</p>
                )}

                <div className="flex justify-end gap-3 pt-4 border-t border-border-color">
                  <button
                    type="button"
                    onClick={() => setIsTemplateModalOpen(false)}
                    disabled={isSavingTemplate}
                    className="rounded-xl glass-panel hover:bg-cyan-500/10 hover:border-cyan-500/30 text-text-secondary hover:text-cyan-400 px-4 py-2.5 text-xs font-semibold transition-all cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSavingTemplate}
                    className="inline-flex items-center justify-center rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black px-5 py-2.5 text-xs font-bold transition-all shadow-[0_0_15px_rgba(34,211,238,0.15)] cursor-pointer"
                  >
                    {isSavingTemplate ? 'Saving Template...' : 'Save Template'}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

    </div>
  )
}
