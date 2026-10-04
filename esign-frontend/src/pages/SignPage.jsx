import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useLocale } from '../context/LocaleContext'
import SignatureCanvas from 'react-signature-canvas'
import { motion, AnimatePresence } from 'framer-motion'
import { PenTool, Type, Upload, FileSignature, ShieldCheck, CheckCircle2, AlertCircle, RefreshCw, ChevronRight, Download, X, User, Clock, Camera, Video, FileText, Mail, CreditCard, UserCheck, Check, AlertTriangle, ArrowRight, Info, Lock, FileText as FileIcon, UserCheck as UserCheckIcon } from 'lucide-react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'

import {
  apiClient,
  completeSigning,
  getSigningSession,
  API_URL,
  API_BASE,
  getAuthorizationStatus,
  acceptTerms,
  sendEmailOTP,
  verifyEmailOTP,
  submitFaceVerification,
  submitIdentityVerification
} from '../services/api.js'

import VerificationStepper, { VERIFICATION_STAGES } from '../components/verification/VerificationStepper.jsx'
import VerificationLayout from '../components/verification/VerificationLayout.jsx'
import VerificationCard from '../components/verification/VerificationCard.jsx'
import VerificationStatus from '../components/verification/VerificationStatus.jsx'
import VerificationSuccess from '../components/verification/VerificationSuccess.jsx'
import VerificationLoading from '../components/verification/VerificationLoading.jsx'
import VerificationSummary from '../components/verification/VerificationSummary.jsx'
import VerificationError from '../components/verification/VerificationError.jsx'
import VerificationQualityError from '../components/verification/VerificationQualityError.jsx'
import LockedSigningNotice from '../components/verification/LockedSigningNotice.jsx'
import VerificationDetailsDrawer from '../components/verification/VerificationDetailsDrawer.jsx'

// ── Configure pdf.js worker ──────────────────────────────────────────────────
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

// ── Helpers ────────────────────────────────────────────────────────────────────

function maskEmail(email) {
  if (!email) return '';
  const parts = email.split('@');
  if (parts.length !== 2) return email;
  const [localPart, domain] = parts;
  let maskedLocal;
  if (localPart.length <= 1) {
    maskedLocal = localPart + '***';
  } else if (localPart.length === 2) {
    maskedLocal = localPart[0] + '***' + localPart[1];
  } else if (localPart.length === 3) {
    maskedLocal = localPart[0] + '***' + localPart.slice(-2);
  } else {
    maskedLocal = localPart[0] + '*'.repeat(localPart.length - 2) + localPart.slice(-2);
  }
  return `${maskedLocal}@${domain}`;
}

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
  'w-full rounded-2xl border border-border-color bg-card-bg px-4 py-3.5 text-sm text-text-primary placeholder:text-text-secondary/60 outline-none backdrop-blur-xl transition-all duration-300 focus:border-cyan-500/50 focus:bg-cyan-950/10 focus:ring-2 focus:ring-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-60'

const SIGNATURE_METHODS = [
  { id: 'typed', label: 'Keyboard', icon: Type },
  { id: 'upload', label: 'Upload', icon: Upload },
  { id: 'draw', label: 'Draw', icon: PenTool },
]

function WorkflowPendingScreen({ session }) {
  const roleLabels = {
    signer: 'Signer',
    approver: 'Approver',
    reviewer: 'Reviewer',
    cc: 'CC Recipient'
  }

  const roleName = roleLabels[session.participant_role] || session.participant_role || 'Participant'

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeInOut" }}
      className="max-w-xl mx-auto glass-panel rounded-[2rem] p-8 sm:p-12 text-center relative overflow-hidden group mt-10 font-sans"
    >
      <div className="absolute inset-0 bg-gradient-to-br from-amber-500/5 via-transparent to-transparent opacity-50 pointer-events-none" />

      <div className="relative mb-6 flex justify-center">
        <div className="absolute inset-0 rounded-full bg-amber-500/10 blur-xl animate-pulse w-20 h-20 mx-auto" />
        <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-amber-500/5 border border-amber-500/20 text-amber-500 shadow-[0_0_30px_rgba(245,158,11,0.1)]">
          <Clock className="h-10 w-10" />
        </div>
      </div>

      <h2 className="text-2xl sm:text-3xl font-light tracking-tight text-text-primary neon-text-glow">
        Workflow Not Yet Available
      </h2>
      <p className="mt-3 text-sm text-text-secondary leading-relaxed">
        This document is currently waiting for a previous workflow participant to complete their action.
      </p>

      <div className="w-full mt-8 p-6 rounded-2xl border border-border-color bg-bg-primary/5 text-left space-y-4">
        <div className="flex items-center justify-between border-b border-border-color pb-3">
          <span className="text-xs font-bold uppercase tracking-wider text-text-secondary">Your Action Details</span>
          <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/20 bg-amber-500/5 px-2.5 py-0.5 text-[10px] font-bold uppercase text-amber-500 tracking-wider">
            Pending
          </span>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-text-secondary">Your Role</span>
            <span className="text-xs font-semibold text-text-primary capitalize">
              {roleName}
            </span>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs text-text-secondary">Your Step</span>
            <span className="text-xs font-semibold text-text-primary font-mono">
              {session.participant_step} of {session.total_steps}
            </span>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs text-text-secondary">Current Workflow Status</span>
            <span className="text-xs font-semibold text-amber-400">
              Waiting For Previous Step
            </span>
          </div>
        </div>
      </div>

      <p className="mt-8 text-xs text-text-secondary max-w-sm mx-auto leading-normal">
        You will be able to review and complete actions on this document once the workflow reaches your assigned step.
      </p>
    </motion.div>
  )
}

export default function SignPage() {
  const { t } = useLocale()
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
  const [numPages, setNumPages] = useState(null)
  const [viewTracked, setViewTracked] = useState(false)

  // ── Signature method ──────────────────────────────────────────────────────
  const [signatureMethod, setSignatureMethod] = useState('typed')

  // ── Draw mode state ───────────────────────────────────────────────────────
  const sigPadRef = useRef(null)
  const [isDrawEmpty, setIsDrawEmpty] = useState(true)

  // ── Upload mode state ─────────────────────────────────────────────────────
  const [uploadFile, setUploadFile] = useState(null)
  const [uploadPreview, setUploadPreview] = useState('')

  // ── Authorization & Verification State ──────────────────────────────────────
  const [authStatus, setAuthStatus] = useState(null)
  const [isVerifying, setIsVerifying] = useState(false)
  const [emailOtpSent, setEmailOtpSent] = useState(false)
  const [emailOtpCode, setEmailOtpCode] = useState('')
  const [selfieFile, setSelfieFile] = useState(null)
  const [selfiePreview, setSelfiePreview] = useState('')
  const [cameraActive, setCameraActive] = useState(false)
  const [cameraError, setCameraError] = useState(false)
  const [useUploadFallback, setUseUploadFallback] = useState(false)
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const [idFile, setIdFile] = useState(null)
  const [idPreview, setIdPreview] = useState('')
  const [verifyingError, setVerifyingError] = useState('')
  const [verificationRequiresManualReview, setVerificationRequiresManualReview] = useState(false)
  const [userAcknowledgedIdentity, setUserAcknowledgedIdentity] = useState(false)
  const [acknowledgedUnlock, setAcknowledgedUnlock] = useState(false)

  // ── Access Gate & Auto-Transition State ─────────────────────────────────────
  const [isTransitioningToAccess, setIsTransitioningToAccess] = useState(false)
  const prevAuthRef = useRef(false)

  // ── Derived Identity Authentication State (Independent of Representative Authorization) ──
  const authenticationRequirementsSatisfied = useMemo(() => {
    if (!authStatus) return false
    const missingAuth = (authStatus.missing_requirements || []).filter(
      (code) => code !== 'representative_match'
    )
    return missingAuth.length === 0
  }, [authStatus])

  // ── Guided Wizard Step Derivation ──────────────────────────────────────────
  const [autoSuccessStage, setAutoSuccessStage] = useState(null)

  const completedStages = useMemo(() => {
    if (!authStatus) return []
    const stages = []
    const reqs = authStatus.requirements || {}
    if (!reqs.terms_acceptance?.required || reqs.terms_acceptance?.satisfied) stages.push('terms')
    if (!reqs.email_otp?.required || reqs.email_otp?.satisfied) stages.push('email')
    if (!reqs.national_id?.required || reqs.national_id?.satisfied) stages.push('national_id')
    if (!reqs.face_biometric?.required || reqs.face_biometric?.satisfied) stages.push('face')
    if (!reqs.representative_match?.required || reqs.representative_match?.satisfied) stages.push('authorization')
    if (authStatus.authorized) stages.push('authorization')
    return stages
  }, [authStatus])

  const missingRequirements = authStatus?.missing_requirements || []
  let currentStep = 'terms'

  if (authStatus) {
    if (!authStatus.authorized) {
      if (missingRequirements.includes('terms_acceptance') || missingRequirements.includes('terms')) {
        currentStep = 'terms'
      } else if (missingRequirements.includes('email_otp')) {
        currentStep = 'email'
      } else if (authStatus.requirements?.national_id?.required && !authStatus.requirements?.national_id?.satisfied) {
        currentStep = 'national_id'
      } else if (authStatus.requirements?.national_id?.required && authStatus.requirements?.national_id?.satisfied && !userAcknowledgedIdentity) {
        currentStep = 'identity_summary_preview'
      } else if (missingRequirements.includes('face_biometric')) {
        currentStep = 'face'
      } else if (!authStatus.requirements?.representative_match?.satisfied) {
        currentStep = 'authorization'
      }
    } else {
      currentStep = 'sign'
    }
  }

  // Monitor identity authentication requirement completion to trigger short transition card (~1 sec)
  useEffect(() => {
    if (authStatus) {
      if (authenticationRequirementsSatisfied && !prevAuthRef.current && session?.status !== 'completed') {
        setIsTransitioningToAccess(true)
        const timer = setTimeout(() => {
          setIsTransitioningToAccess(false)
        }, 1200)
        prevAuthRef.current = true
        return () => clearTimeout(timer)
      }
      if (authenticationRequirementsSatisfied) {
        prevAuthRef.current = true
      }
    }
  }, [authStatus, authenticationRequirementsSatisfied, session?.status])

  const documentUrl = useMemo(() => {
    const url = session?.document_url
    return toAbsoluteUrl(url, backendOrigin)
  }, [session, backendOrigin])

  // Representative Identified Name
  const identifiedRepresentative = authStatus?.identity_summary?.full_name_en || authStatus?.identity_summary?.full_name_ar || null

  // ── Session loading ──────────────────────────────────────────────────────────
  async function loadSession() {
    setError('')
    setSuccessMessage('')
    setSignedDocumentUrl('')
    setVerifyingError('')
    setUserAcknowledgedIdentity(false)
    setAcknowledgedUnlock(false)

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
      } else if (data) {
        const authData = await getAuthorizationStatus(data.participant_id, token)
        setAuthStatus(authData)
        const isAuthSatisfied = (authData?.missing_requirements || []).filter(c => c !== 'representative_match').length === 0
        if (isAuthSatisfied) {
          prevAuthRef.current = true
        }
        const isManualReview = localStorage.getItem(`manual_review_${data.participant_id}`) === 'true'
        if (isManualReview || authData.status === 'requires_manual_review') {
          setVerificationRequiresManualReview(true)
        }
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

  async function refreshAuthStatus() {
    if (!session?.participant_id) return
    setVerifyingError('')
    try {
      const authData = await getAuthorizationStatus(session.participant_id, token)
      setAuthStatus(authData)
      const isManualReview = localStorage.getItem(`manual_review_${session.participant_id}`) === 'true'
      if (isManualReview || authData.status === 'requires_manual_review') {
        setVerificationRequiresManualReview(true)
      }
      return authData
    } catch (err) {
      setVerifyingError('Failed to refresh authorization status.')
    }
  }

  // ── Auto-transition helper ─────────────────────────────────────────────────
  function triggerStageSuccess(stageId, callback) {
    setAutoSuccessStage(stageId)
    setTimeout(() => {
      setAutoSuccessStage(null)
      if (callback) callback()
    }, 1200)
  }

  // ── Verification actions ───────────────────────────────────────────────────
  async function handleAcceptTerms() {
    setVerifyingError('')
    setIsVerifying(true)
    try {
      await acceptTerms(session.participant_id, token)
      await refreshAuthStatus()
      triggerStageSuccess('terms')
    } catch (err) {
      setVerifyingError(err?.response?.data?.detail || 'Failed to accept terms. Please try again.')
    } finally {
      setIsVerifying(false)
    }
  }

  async function handleSendEmailOTP() {
    setVerifyingError('')
    setIsVerifying(true)
    try {
      await sendEmailOTP(session.participant_id, token)
      setEmailOtpSent(true)
    } catch (err) {
      setVerifyingError(err?.response?.data?.detail || 'Failed to send OTP code. Please retry.')
    } finally {
      setIsVerifying(false)
    }
  }

  async function handleVerifyEmailOTP() {
    if (!emailOtpCode.trim()) {
      setVerifyingError('Please enter the 6-digit OTP code.')
      return
    }
    setVerifyingError('')
    setIsVerifying(true)
    try {
      const res = await verifyEmailOTP(session.participant_id, emailOtpCode, token)
      if (res.verified) {
        await refreshAuthStatus()
        triggerStageSuccess('email')
      } else {
        setVerifyingError(res.error || 'Invalid OTP code entered. Please check your inbox and try again.')
      }
    } catch (err) {
      setVerifyingError(err?.response?.data?.detail || 'Failed to verify OTP code.')
    } finally {
      setIsVerifying(false)
    }
  }

  async function handleIdChange(e) {
    const file = e.target.files?.[0]
    if (!file) return

    if (!['image/png', 'image/jpeg'].includes(file.type)) {
      setVerifyingError('Only PNG and JPG files are accepted.')
      return
    }

    setVerifyingError('')
    setIdFile(file)

    const reader = new FileReader()
    reader.onload = (ev) => setIdPreview(ev.target.result)
    reader.readAsDataURL(file)
  }

  async function handleRemoveId() {
    setIdFile(null)
    setIdPreview('')
  }

  async function handleVerifyId() {
    if (!idFile) {
      setVerifyingError('Please select a clear National ID photo.')
      return
    }
    setVerifyingError('')
    setIsVerifying(true)
    try {
      const res = await submitIdentityVerification(session.participant_id, idFile, token)
      if (res.status === 'verified') {
        await refreshAuthStatus()
        triggerStageSuccess('national_id')
      } else if (res.status === 'requires_manual_review') {
        localStorage.setItem(`manual_review_${session.participant_id}`, 'true')
        setVerificationRequiresManualReview(true)
        await refreshAuthStatus()
      } else {
        setVerifyingError(res.failure_reason || 'Identity verification failed.')
      }
    } catch (err) {
      if (err?.response?.data?.failure_code === 'image_quality_check_failed') {
        setVerifyingError(err.response.data)
      } else {
        setVerifyingError(err?.response?.data?.detail || 'Failed during identity verification.')
      }
    } finally {
      setIsVerifying(false)
    }
  }

  async function handleSelfieChange(e) {
    const file = e.target.files?.[0]
    if (!file) return

    if (!['image/png', 'image/jpeg'].includes(file.type)) {
      setVerifyingError('Only PNG and JPG files are accepted.')
      return
    }

    setVerifyingError('')
    setSelfieFile(file)

    const reader = new FileReader()
    reader.onload = (ev) => setSelfiePreview(ev.target.result)
    reader.readAsDataURL(file)
  }

  async function handleRemoveSelfie() {
    setSelfieFile(null)
    setSelfiePreview('')
    stopCamera()
  }

  async function handleVerifyFace() {
    if (!selfieFile) {
      setVerifyingError('Please capture or upload a selfie photo.')
      return
    }
    setVerifyingError('')
    setIsVerifying(true)
    try {
      const res = await submitFaceVerification(session.participant_id, selfieFile, token)
      if (res.matched) {
        await refreshAuthStatus()
        triggerStageSuccess('face')
      } else if (res.status === 'requires_manual_review') {
        localStorage.setItem(`manual_review_${session.participant_id}`, 'true')
        setVerificationRequiresManualReview(true)
        await refreshAuthStatus()
      } else {
        setVerifyingError('Face biometric matching failed. Face feature similarity was below threshold.')
      }
    } catch (err) {
      if (err?.response?.data?.failure_code === 'image_quality_check_failed') {
        setVerifyingError(err.response.data)
      } else {
        setVerifyingError(err?.response?.data?.detail || 'Failed during face verification.')
      }
    } finally {
      setIsVerifying(false)
    }
  }

  // Camera Live Capture functions
  async function startCamera() {
    setVerifyingError('')
    setCameraError(false)
    setUseUploadFallback(false)
    try {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop())
      }

      const constraints = {
        video: {
          facingMode: 'user',
          width: { ideal: 640 },
          height: { ideal: 640 }
        },
        audio: false
      }

      const stream = await navigator.mediaDevices.getUserMedia(constraints)
      streamRef.current = stream
      setCameraActive(true)

      if (videoRef.current) {
        if (videoRef.current.srcObject !== stream) {
          videoRef.current.srcObject = stream
        }
        videoRef.current.play().catch(() => {})
      }
    } catch (err) {
      setCameraError(true)
      setCameraActive(false)
    }
  }

  function stopCamera() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
    setCameraActive(false)
  }

  function capturePhoto() {
    if (!videoRef.current) return

    const video = videoRef.current
    const videoWidth = video.videoWidth || 640
    const videoHeight = video.videoHeight || 640
    const size = Math.min(videoWidth, videoHeight)

    const sx = (videoWidth - size) / 2
    const sy = (videoHeight - size) / 2

    const canvas = document.createElement('canvas')
    canvas.width = size
    canvas.height = size

    const ctx = canvas.getContext('2d')
    if (ctx) {
      ctx.translate(canvas.width, 0)
      ctx.scale(-1, 1)
      ctx.drawImage(video, sx, sy, size, size, 0, 0, canvas.width, canvas.height)

      canvas.toBlob((blob) => {
        if (blob) {
          const file = new File([blob], 'selfie.jpg', { type: 'image/jpeg' })
          setSelfieFile(file)
          const previewUrl = URL.createObjectURL(blob)
          setSelfiePreview(previewUrl)
          stopCamera()
        }
      }, 'image/jpeg', 0.95)
    }
  }

  function handleRetake() {
    stopCamera()
    setSelfieFile(null)
    setSelfiePreview('')
    void startCamera()
  }

  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop())
      }
    }
  }, [])

  useEffect(() => {
    if (currentStep !== 'face') {
      stopCamera()
    }
  }, [currentStep])

  useEffect(() => {
    setViewTracked(false)
    void loadSession()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  useEffect(() => {
    if (token && session && !viewTracked && session?.status !== 'completed') {
      setViewTracked(true)
      completeSigning(token, { action: 'view' }).catch(() => { })
    }
  }, [token, session, viewTracked])

  // ── Payload builder ──
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
      const signedUrl = response?.signed_document_url

      navigate('/success', {
        state: {
          token,
          successType: 'sign',
          session: {
            ...session,
            status: response?.status || 'completed',
            participant_status: 'completed',
          },
          signedDocumentUrl: signedUrl || toAbsoluteUrl(session?.signed_document_url || session?.document_url, backendOrigin),
          downloadUrl: response?.download_url || toAbsoluteUrl(`${API_BASE}/sign/${token}/download/`, backendOrigin),
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

  // ── Derived session & access state ───────────────────────────
  const status = session?.status
  const isEnvelopeCompleted = status === 'completed'
  const isParticipantCompleted = session?.participant_status && ['completed', 'returned', 'declined'].includes(session.participant_status)
  const isCompleted = isEnvelopeCompleted || (session?.participant_role && isParticipantCompleted)
  const isPending = session?.participant_status === 'pending'

  // Access Gate Condition (Depends solely on satisfied identity authentication requirements)
  const isAccessGranted = isCompleted || authenticationRequirementsSatisfied

  // Document Title
  const documentTitle = session?.document_title || session?.title || 'Contract Agreement'

  // ── Render Left Column (Document Viewport & Summaries) ────────────────────
  const leftColumnContent = (
    <>
      {!isAccessGranted ? (
        /* Phase 5 — Secure Access Placeholder (Locked State) */
        <motion.div
          key="locked_placeholder"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: 'easeInOut' }}
          className="glass-panel rounded-3xl p-8 sm:p-12 text-center relative overflow-hidden group"
        >
          <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/5 via-transparent to-transparent opacity-50 pointer-events-none" />
          <div className="relative mb-6 flex justify-center">
            <div className="absolute inset-0 rounded-full bg-cyan-500/10 blur-xl animate-pulse w-20 h-20 mx-auto" />
            <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-cyan-500/5 border border-cyan-500/20 text-accent shadow-[0_0_30px_rgba(34,211,238,0.1)]">
              <Lock className="h-10 w-10 text-cyan-400" />
            </div>
          </div>
          <h2 className="text-2xl sm:text-3xl font-light tracking-tight text-text-primary neon-text-glow">
            Secure Document
          </h2>
          <p className="mt-3 text-sm text-text-secondary leading-relaxed max-w-md mx-auto">
            This document is protected. Complete the required authentication steps to access and review the document.
          </p>
        </motion.div>
      ) : isTransitioningToAccess ? (
        /* Phase 4 — Authentication Complete Transition Card */
        <motion.div
          key="transition_card"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.25, ease: 'easeInOut' }}
          className="glass-panel rounded-3xl p-8 sm:p-12 text-center relative overflow-hidden group border-emerald-500/40"
        >
          <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/10 via-transparent to-transparent opacity-60 pointer-events-none" />
          <div className="relative mb-6 flex justify-center">
            <div className="absolute inset-0 rounded-full bg-emerald-500/20 blur-xl animate-pulse w-20 h-20 mx-auto" />
            <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 shadow-[0_0_30px_rgba(16,185,129,0.2)]">
              <ShieldCheck className="h-10 w-10 text-emerald-400" />
            </div>
          </div>
          <h3 className="text-2xl font-light text-emerald-400 tracking-tight neon-text-glow mb-2">
            Authentication Complete
          </h3>
          <p className="text-sm text-text-secondary leading-relaxed mb-6 max-w-md mx-auto">
            Your identity has been successfully verified.
          </p>
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 text-cyan-400 text-xs font-mono font-semibold animate-pulse">
            <RefreshCw className="h-3.5 w-3.5 animate-spin" /> Loading document...
          </div>
        </motion.div>
      ) : (
        /* Phase 2 & 3 — Lazy Document Viewer & Metadata Panel */
        <>
          {/* Session Metadata Panel */}
          <div className="glass-panel rounded-3xl p-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-2xl bg-cyan-500/10 flex items-center justify-center border border-cyan-500/30">
                <span className="text-xl font-light text-accent">
                  {session?.signer_name?.charAt(0).toUpperCase() || 'U'}
                </span>
              </div>
              <div>
                <p className="text-sm font-medium text-text-primary">{session?.signer_name || 'Unknown User'}</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-xs text-text-secondary">{session?.signer_email || 'No email provided'}</span>
                  {session?.participant_role && (
                    <span className="inline-flex px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider bg-card-bg text-text-primary border border-border-color">
                      {session.participant_role}
                    </span>
                  )}
                </div>
              </div>
            </div>
            <div className="flex flex-col items-start sm:items-end">
              <span className="text-[10px] uppercase tracking-widest text-text-secondary">Status</span>
              <span className={`text-sm font-medium uppercase tracking-wider ${isCompleted ? 'text-emerald-500' : 'text-accent'}`}>
                {session?.status || 'Active'}
              </span>
            </div>
          </div>

          {/* Document Viewport with Context Awareness */}
          {documentUrl ? (
            <div className="glass-panel rounded-3xl overflow-hidden relative group">
              <div className="absolute inset-0 bg-gradient-to-b from-cyan-500/5 to-transparent opacity-50 pointer-events-none" />
              
              {/* Viewport Header Bar */}
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between border-b border-border-color bg-bg-primary/5 px-6 py-4 gap-2">
                <div className="flex items-center gap-2.5 text-text-primary">
                  <FileSignature className="h-5 w-5 text-accent shrink-0" />
                  <div>
                    <h2 className="text-sm font-semibold tracking-wide truncate max-w-xs sm:max-w-md">{documentTitle}</h2>
                    <div className="flex items-center gap-3 text-[11px] text-text-secondary mt-0.5">
                      <span>Page count: <strong className="text-text-primary">{numPages ? `${numPages} pages` : 'Loading...'}</strong></span>
                    </div>
                  </div>
                </div>

                <a
                  href={documentUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-2 text-xs font-medium text-accent hover:text-accent/80 transition-colors bg-cyan-500/10 px-3 py-1.5 rounded-lg hover:bg-cyan-500/20 shrink-0"
                >
                  External View <ChevronRight className="h-3 w-3" />
                </a>
              </div>

              {/* Authorized Representative Context Banner */}
              {identifiedRepresentative && (
                <div className="px-6 py-2.5 bg-emerald-500/10 border-b border-emerald-500/20 text-xs text-emerald-400 flex items-center gap-2">
                  <UserCheckIcon className="h-4 w-4 shrink-0 text-emerald-400" />
                  <span>
                    Authorized Representative: <strong className="font-semibold">{identifiedRepresentative}</strong>
                  </span>
                </div>
              )}

              {/* Document Pages */}
              <div className="relative overflow-auto bg-bg-primary py-8 custom-scrollbar shadow-inner max-h-[700px] p-2 sm:p-4">
                <Document
                  file={documentUrl}
                  onLoadSuccess={({ numPages: n }) => setNumPages(n)}
                  loading={
                    <div className="flex h-64 flex-col items-center justify-center gap-4 text-accent">
                      <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
                      <span className="text-sm font-medium animate-pulse tracking-widest uppercase">Rendering Data…</span>
                    </div>
                  }
                  error={
                    <div className="flex h-64 items-center justify-center text-sm text-red-400">
                      Failed to decode document payload.
                    </div>
                  }
                >
                  {numPages
                    ? Array.from({ length: numPages }, (_, i) => {
                      const pageNumber = i + 1

                      return (
                        <div
                          key={pageNumber}
                          className="relative mx-auto mb-8 w-fit shadow-lg border border-border-color last:mb-0"
                          style={{ userSelect: 'none' }}
                        >
                          <div className="absolute left-4 top-4 z-10 rounded-lg border border-border-color bg-card-bg/85 px-3 py-1.5 text-xs font-mono text-text-primary backdrop-blur-md">
                            {pageNumber} / {numPages}
                          </div>

                          <Page
                            pageNumber={pageNumber}
                            renderTextLayer={true}
                            renderAnnotationLayer={true}
                            className="block relative z-0"
                          />

                          {!isCompleted && session?.fields && session.fields.filter(f => f.page === pageNumber).map((f) => {
                            if (f.field_type !== 'signature') return null

                            return (
                              <div
                                key={f.id}
                                style={{
                                  position: 'absolute',
                                  left: `${f.x_ratio * 100}%`,
                                  top: `${f.y_ratio * 100}%`,
                                  zIndex: 20,
                                }}
                                className="-translate-x-1/2 -translate-y-1/2 pointer-events-auto"
                              >
                                <div
                                  onClick={() => {
                                    const panel = document.querySelector('input[type="text"]') || document.querySelector('.SignatureCanvas') || document.querySelector('input[type="file"]')
                                    panel?.focus()
                                  }}
                                  className="flex items-center justify-center cursor-pointer group/field active:scale-95 transition-transform"
                                >
                                  <div className="relative flex h-5 w-5 items-center justify-center">
                                    <div className="absolute inset-0 rounded-full bg-cyan-500 animate-ping opacity-30" />
                                    <div className="relative h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_10px_#22d3ee]" />
                                  </div>
                                  <div className="absolute left-0 top-3 -translate-x-1/2 pt-1 flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-cyan-500/50 bg-card-bg/95 px-2.5 py-1 text-[9px] font-bold tracking-wider text-accent shadow-[0_0_20px_rgba(34,211,238,0.25)] backdrop-blur-md uppercase">
                                    <span>↓ SIGN HERE</span>
                                    <span className="text-text-secondary/60">|</span>
                                    <span className="text-text-primary max-w-[100px] truncate" title={session.signer_name}>{session.signer_name}</span>
                                  </div>
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      )
                    })
                    : null}
                </Document>
              </div>
            </div>
          ) : (
            <div className="glass-panel rounded-3xl p-8 text-center text-text-secondary">
              No document payload available for this session.
            </div>
          )}
        </>
      )}

      {/* Verified Summaries Widget */}
      <VerificationSummary authStatus={authStatus} />

      {/* Operational Verification Details Drawer */}
      <VerificationDetailsDrawer
        sessionTimestamp={session?.created_at}
        documentStatus={session?.status || 'Loaded'}
        verificationStatus={authStatus?.authorized ? 'AUTHORIZED' : 'In Progress'}
      />
    </>
  )

  // ── Render Right Column (Persistent Stepper & Active Step Container) ────
  const rightColumnContent = (
    <div className="space-y-6">
      {/* Enterprise Stepper Bar — Mounted ONCE (Persistent) */}
      <VerificationStepper
        currentStageId={currentStep}
        completedStages={completedStages}
        failedStageId={verifyingError ? currentStep : null}
      />

      {/* Persistent Verification Session Status Panel — Mounted ONCE (Persistent) */}
      <VerificationStatus authStatus={authStatus} documentLoaded={isAccessGranted && !isTransitioningToAccess && !!documentUrl} />

      {/* Active Step Container — AnimatePresence animates ONLY the active step card */}
      <AnimatePresence mode="wait">
        {isCompleted ? (
          <motion.div
            key="completed"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
            className="glass-panel rounded-3xl p-8 text-center relative overflow-hidden group"
          >
            <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/10 to-transparent opacity-50" />
            <CheckCircle2 className="h-16 w-16 text-emerald-400 mx-auto mb-4" />
            <h3 className="text-xl font-light text-emerald-500 mb-2">
              {session?.participant_role === 'cc' ? 'Document Viewed' :
                session?.participant_role === 'reviewer' ? 'Review Completed' :
                  session?.participant_role === 'approver' ? 'Approval Completed' :
                    'Signature Verified'}
            </h3>
            <p className="text-sm text-text-secondary mb-6">
              {session?.participant_role === 'cc' ? 'You have successfully viewed this document.' :
                session?.participant_role === 'reviewer' ? 'Your review action has been registered and advanced.' :
                  session?.participant_role === 'approver' ? 'Your approval action has been registered and advanced.' :
                    'This document has been successfully signed.'}
            </p>
            {signedDocumentUrl && (
              <a
                href={signedDocumentUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center justify-center gap-2 w-full rounded-2xl bg-emerald-500/20 border border-emerald-500/30 px-4 py-3 text-sm font-semibold text-emerald-500 transition-all hover:bg-emerald-500/30"
              >
                <Download className="h-4 w-4" /> View Signed Document
              </a>
            )}
          </motion.div>
        ) : verificationRequiresManualReview ? (
          <motion.div
            key="manual_review"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
            className="glass-panel rounded-3xl p-8 text-center relative overflow-hidden group"
          >
            <div className="absolute inset-0 bg-gradient-to-br from-amber-500/10 to-transparent opacity-50" />
            <div className="relative mb-6 flex justify-center">
              <div className="absolute inset-0 rounded-full bg-amber-500/10 blur-xl animate-pulse w-20 h-20 mx-auto" />
              <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-amber-500/5 border border-amber-500/20 text-amber-500">
                <AlertCircle className="h-10 w-10 animate-bounce" />
              </div>
            </div>
            <h3 className="text-xl font-light text-amber-500 mb-2">
              Manual Review Required
            </h3>
            <p className="text-sm text-text-secondary leading-relaxed mb-4">
              Your identity verification requires administrative review. Please contact support or wait for approval.
            </p>
            {verifyingError && (
              <div className="mt-4 p-3 rounded-xl border border-red-500/20 bg-red-500/5 text-xs text-red-400">
                {verifyingError}
              </div>
            )}
          </motion.div>
        ) : autoSuccessStage ? (
          <VerificationSuccess
            key="auto_success"
            title={
              autoSuccessStage === 'terms' ? 'Terms Accepted' :
              autoSuccessStage === 'email' ? 'Email Code Verified' :
              autoSuccessStage === 'national_id' ? 'National ID Verified' :
              autoSuccessStage === 'face' ? 'Identity Verified' : 'Stage Completed'
            }
            subtitle="Verification requirement satisfied successfully."
            items={
              autoSuccessStage === 'national_id' && authStatus?.identity_summary ? [
                { label: 'English Name', value: authStatus.identity_summary.full_name_en },
                { label: 'Arabic Name', value: authStatus.identity_summary.full_name_ar, dir: 'rtl' },
                { label: 'National ID', value: authStatus.identity_summary.national_id, isMono: true },
                { label: 'Country', value: authStatus.identity_summary.country },
              ] : []
            }
            autoContinueText="Proceeding to next verification step..."
          />
        ) : isVerifying ? (
          <VerificationCard
            key="loading"
            title="Processing Verification"
            subtitle="Communicating with identity services"
            icon={RefreshCw}
            estimatedTime="10–20 seconds"
            stepProgress="Processing..."
          >
            <VerificationLoading stageId={currentStep} />
          </VerificationCard>
        ) : !isAccessGranted || isTransitioningToAccess ? (
          /* Step verification cards (terms, email, national_id, identity_summary_preview, face, authorization) */
          currentStep === 'terms' ? (
            <VerificationCard
              key="step_terms"
              title="Terms & Conditions"
              subtitle="Review and accept electronic disclosure terms"
              icon={FileText}
              badgeText="Step 1 of 5"
              estimatedTime="Approx. 1 min"
              stepProgress="Step 1 of 5"
            >
              <div className="p-4 rounded-2xl border border-border-color bg-bg-primary/5 text-xs text-text-secondary max-h-48 overflow-y-auto space-y-2 custom-scrollbar">
                <p className="font-semibold text-text-primary">Electronic Record and Disclosure</p>
                <p>By accepting these terms, you agree to conduct this transaction electronically and consent to the legally binding nature of your digital signature.</p>
                <p>All activities under this session are logged for verification and audit trail purposes.</p>
              </div>

              {verifyingError && (
                <VerificationError
                  title="Terms Acceptance Error"
                  message={verifyingError}
                  onRetry={handleAcceptTerms}
                />
              )}

              {!verifyingError && (
                <button
                  onClick={handleAcceptTerms}
                  disabled={isVerifying}
                  className="flex w-full items-center justify-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 text-black px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] disabled:opacity-50 focus:ring-2 focus:ring-cyan-500/30 outline-none"
                >
                  {t('sign.accept_terms')} <ChevronRight className="h-4 w-4" />
                </button>
              )}
            </VerificationCard>
          ) : currentStep === 'email' ? (
            <VerificationCard
              key="step_email"
              title="Email Verification"
              subtitle="Authenticate your identity via 6-digit OTP code"
              icon={Mail}
              badgeText="Step 2 of 5"
              estimatedTime="Approx. 1 min"
              stepProgress="Step 2 of 5"
            >
              {!emailOtpSent ? (
                <>
                  <p className="text-xs text-text-secondary leading-relaxed">
                    To secure your signing session, we must verify your email address. A one-time verification code (OTP) will be sent to:
                  </p>
                  <div className="p-4 rounded-2xl border border-border-color bg-bg-primary/5 text-center">
                    <span className="text-sm font-semibold text-text-primary font-mono">{maskEmail(session?.signer_email)}</span>
                  </div>

                  {verifyingError && (
                    <VerificationError
                      title="OTP Dispatch Failed"
                      message={verifyingError}
                      onRetry={handleSendEmailOTP}
                    />
                  )}

                  {!verifyingError && (
                    <button
                      onClick={handleSendEmailOTP}
                      disabled={isVerifying}
                      className="flex w-full items-center justify-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 text-black px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] disabled:opacity-50 focus:ring-2 focus:ring-cyan-500/30 outline-none"
                    >
                      Send Verification Code <Mail className="h-4 w-4" />
                    </button>
                  )}
                </>
              ) : (
                <>
                  <p className="text-xs text-text-secondary leading-relaxed">
                    Please enter the verification code sent to <strong className="text-text-primary">{maskEmail(session?.signer_email)}</strong>.
                  </p>

                  <div>
                    <input
                      type="text"
                      value={emailOtpCode}
                      onChange={(e) => setEmailOtpCode(e.target.value)}
                      placeholder={t('sign.otp_placeholder')}
                      maxLength={10}
                      disabled={isVerifying}
                      className={inputClass}
                    />
                  </div>

                  {verifyingError && (
                    <VerificationError
                      title="Verification Failed"
                      message={verifyingError}
                      reasons={['Check for typos in code', 'Code may have expired', 'Request a fresh code below']}
                      onRetry={handleVerifyEmailOTP}
                      onSecondaryAction={handleSendEmailOTP}
                      secondaryActionLabel="Resend Code"
                    />
                  )}

                  {!verifyingError && (
                    <div className="space-y-3">
                      <button
                        onClick={handleVerifyEmailOTP}
                        disabled={isVerifying}
                        className="flex w-full items-center justify-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 text-black px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] disabled:opacity-50 focus:ring-2 focus:ring-cyan-500/30 outline-none"
                      >
                        Verify Code <ChevronRight className="h-4 w-4" />
                      </button>

                      <button
                        onClick={handleSendEmailOTP}
                        disabled={isVerifying}
                        className="flex w-full items-center justify-center gap-2 rounded-2xl border border-border-color bg-bg-primary/5 text-text-secondary hover:text-text-primary px-4 py-3.5 text-xs font-semibold uppercase tracking-wider transition-all duration-300 disabled:opacity-50"
                      >
                        Resend OTP Code
                      </button>
                    </div>
                  )}
                </>
              )}
            </VerificationCard>
          ) : currentStep === 'national_id' ? (
            <VerificationCard
              key="step_id"
              title="Verify National ID"
              subtitle="Upload National ID or Iqama document for OCR extraction"
              icon={CreditCard}
              badgeText="Step 3 of 5"
              estimatedTime="Approx. 1–2 min"
              stepProgress="Step 3 of 5"
            >
              {!idPreview ? (
                <>
                  <p className="text-xs text-text-secondary leading-relaxed">
                    Upload a clear photo of your National ID or Iqama document. The OCR system will extract details and register your reference face.
                  </p>
                  <label className="flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-border-color bg-card-bg p-8 cursor-pointer transition-all hover:border-cyan-500/30 hover:bg-cyan-500/5">
                    <Upload className="h-8 w-8 text-accent/60 animate-bounce" />
                    <div className="text-center">
                      <p className="text-sm text-text-primary font-medium">Select ID Image</p>
                      <p className="text-xs text-text-secondary mt-1">PNG or JPG formats supported (max 10MB)</p>
                    </div>
                    <input
                      type="file"
                      accept="image/png,image/jpeg"
                      onChange={handleIdChange}
                      disabled={isVerifying}
                      className="hidden"
                    />
                  </label>

                  {/* Upload Recommendation Tips */}
                  <div className="p-3.5 rounded-2xl border border-cyan-500/20 bg-cyan-500/5 text-xs text-text-secondary space-y-1 text-left">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-accent flex items-center gap-1">
                      <Info className="h-3 w-3" /> Upload Recommendations
                    </span>
                    <ul className="list-disc list-inside space-y-0.5 text-[11px] text-text-secondary">
                      <li>Ensure entire document boundary is visible</li>
                      <li>Good lighting without harsh shadows</li>
                      <li>Avoid camera glare or surface reflections</li>
                      <li>PNG or JPG format supported (up to 10MB)</li>
                    </ul>
                  </div>
                </>
              ) : (
                <div className="relative rounded-2xl border border-border-color bg-bg-primary/5 p-4 flex justify-center">
                  <img src={idPreview} alt="ID preview" className="rounded-xl max-h-48 object-cover shadow-md border border-cyan-500/20" />
                  <button
                    onClick={handleRemoveId}
                    className="absolute top-2 right-2 p-1.5 rounded-full bg-red-500/20 text-red-400 hover:bg-red-500/40 transition-colors"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              )}

              {verifyingError && verifyingError.failure_code === 'image_quality_check_failed' ? (
                <VerificationQualityError
                  qualityReport={verifyingError.quality_report}
                  onRetry={handleVerifyId}
                  onSecondaryAction={handleRemoveId}
                  secondaryActionLabel="Choose Different Image"
                />
              ) : verifyingError && (
                <VerificationError
                  title="ID Verification Failed"
                  message={typeof verifyingError === 'string' ? verifyingError : (verifyingError.detail || 'ID verification failed.')}
                  reasons={[
                    'Entire document boundary must be visible',
                    'Ensure lighting is clear without surface reflection',
                    'Avoid blurry images or low contrast photos',
                    'Ensure text and face photo are unobscured'
                  ]}
                  onRetry={handleVerifyId}
                  onSecondaryAction={handleRemoveId}
                  secondaryActionLabel="Choose Different Image"
                />
              )}

              {idPreview && !verifyingError && (
                <div className="space-y-3">
                  <button
                    onClick={handleVerifyId}
                    disabled={isVerifying}
                    className="flex w-full items-center justify-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 text-black px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] disabled:opacity-50 focus:ring-2 focus:ring-cyan-500/30 outline-none"
                  >
                    Verify National ID <ChevronRight className="h-4 w-4" />
                  </button>

                  <button
                    onClick={handleRemoveId}
                    disabled={isVerifying}
                    className="flex w-full items-center justify-center gap-2 rounded-2xl border border-border-color bg-bg-primary/5 text-text-secondary hover:text-text-primary px-4 py-3.5 text-xs font-semibold uppercase tracking-wider transition-all duration-300 disabled:opacity-50"
                  >
                    Choose Different Photo
                  </button>
                </div>
              )}
            </VerificationCard>
          ) : currentStep === 'identity_summary_preview' ? (
            <VerificationCard
              key="step_summary_preview"
              title="Extracted Identity Details"
              subtitle="Confirm extracted National ID details"
              icon={CreditCard}
              badgeText="Confirmation"
              estimatedTime="Approx. 30 sec"
              stepProgress="Confirmation"
            >
              <p className="text-xs text-text-secondary leading-relaxed">
                Below are the identity details extracted from your uploaded National ID. Please review them before proceeding to facial verification.
              </p>

              <div className="space-y-3 p-4 rounded-2xl border border-border-color bg-bg-primary/5 text-xs">
                <div className="flex items-center justify-between gap-4">
                  <span className="text-text-secondary shrink-0">English Name</span>
                  <span className="font-semibold text-text-primary text-right truncate" title={authStatus?.identity_summary?.full_name_en}>
                    {authStatus?.identity_summary?.full_name_en || '—'}
                  </span>
                </div>

                <div className="flex items-center justify-between gap-4">
                  <span className="text-text-secondary shrink-0">Arabic Name</span>
                  <span className="font-semibold text-text-primary text-right font-sans truncate" dir="rtl" title={authStatus?.identity_summary?.full_name_ar}>
                    {authStatus?.identity_summary?.full_name_ar || '—'}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-text-secondary">National ID</span>
                  <span className="font-semibold text-text-primary font-mono">
                    {authStatus?.identity_summary?.national_id || '—'}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-text-secondary">Country</span>
                  <span className="font-semibold text-text-primary capitalize">
                    {authStatus?.identity_summary?.country || '—'}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-text-secondary">Document Type</span>
                  <span className="font-semibold text-text-primary capitalize font-mono">
                    {authStatus?.identity_summary?.document_type || '—'}
                  </span>
                </div>
              </div>

              <button
                onClick={() => setUserAcknowledgedIdentity(true)}
                className="flex w-full items-center justify-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 text-black px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] focus:ring-2 focus:ring-cyan-500/30 outline-none"
              >
                Proceed to Verify Your Identity <ChevronRight className="h-4 w-4" />
              </button>
            </VerificationCard>
          ) : currentStep === 'face' ? (
            <VerificationCard
              key="step_face"
              title="Verify Your Identity"
              subtitle="Match facial features against reference identity photo"
              icon={Camera}
              badgeText="Step 4 of 5"
              estimatedTime="Approx. 1 min"
              stepProgress="Step 4 of 5"
            >
              <style>{`
                @keyframes scan {
                  0%, 100% { top: 10%; }
                  50% { top: 90%; }
                }
                .animate-scan {
                  animation: scan 3.5s ease-in-out infinite;
                }
              `}</style>

              {selfiePreview ? (
                <>
                  <div className="relative rounded-2xl border border-border-color bg-bg-primary/5 p-4 flex justify-center">
                    <img src={selfiePreview} alt="Selfie preview" className="rounded-xl max-h-48 object-cover aspect-square shadow-md border border-cyan-500/20" />
                  </div>
                  <p className="text-[10px] text-text-secondary text-center leading-normal">
                    Ensure your face is well-lit and not covered by hats, glasses, or masks.
                  </p>
                </>
              ) : (
                <>
                  {useUploadFallback || cameraError ? (
                    <div className="space-y-4">
                      {cameraError && (
                        <div className="p-3 rounded-xl border border-amber-500/20 bg-amber-500/5 text-xs text-amber-400 text-center">
                          Unable to access webcam. Please upload a selfie image file instead.
                        </div>
                      )}
                      <p className="text-xs text-text-secondary leading-relaxed">
                        Upload a clear selfie. The matching engine will compare your facial features with the reference identity photo.
                      </p>
                      <label className="flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-border-color bg-card-bg p-8 cursor-pointer transition-all hover:border-cyan-500/30 hover:bg-cyan-500/5">
                        <Upload className="h-8 w-8 text-accent/60 animate-bounce" />
                        <div className="text-center">
                          <p className="text-sm text-text-primary font-medium">Select Selfie Image</p>
                          <p className="text-xs text-text-secondary mt-1">PNG or JPG formats supported</p>
                        </div>
                        <input
                          type="file"
                          accept="image/png,image/jpeg"
                          onChange={handleSelfieChange}
                          disabled={isVerifying}
                          className="hidden"
                        />
                      </label>
                      {!cameraError && (
                        <button
                          onClick={startCamera}
                          className="flex w-full items-center justify-center gap-2 rounded-2xl border border-border-color bg-bg-primary/5 text-text-secondary hover:text-text-primary px-4 py-3 text-xs font-semibold uppercase tracking-wider transition-all duration-300"
                        >
                          <Camera className="h-4 w-4" /> Use Live Camera
                        </button>
                      )}
                    </div>
                  ) : cameraActive ? (
                    <div className="space-y-4">
                      <div className="relative w-full aspect-square max-w-[280px] mx-auto overflow-hidden rounded-2xl border border-border-color bg-black/40 shadow-inner">
                        <video
                          ref={videoRef}
                          style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                          className="scale-x-[-1]"
                          autoPlay
                          playsInline
                          muted
                        />
                        <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                          <div className="w-2/3 h-2/3 rounded-[50%] border-2 border-dashed border-cyan-500/40 relative">
                            <div className="absolute left-0 right-0 h-0.5 bg-cyan-400/50 shadow-[0_0_8px_#22d3ee] animate-scan" />
                          </div>
                        </div>
                      </div>
                      <p className="text-xs text-text-secondary text-center leading-normal animate-pulse">
                        Position your face inside the circle guide.
                      </p>
                      <div className="flex gap-2">
                        <button
                          onClick={capturePhoto}
                          className="flex-1 flex items-center justify-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 text-black px-4 py-3.5 text-xs font-bold uppercase tracking-wider transition-all duration-300"
                        >
                          <Camera className="h-4 w-4" /> Capture Photo
                        </button>
                        <button
                          onClick={() => { stopCamera(); setUseUploadFallback(true); }}
                          className="flex-1 flex items-center justify-center gap-2 rounded-2xl border border-border-color bg-bg-primary/5 text-text-secondary hover:text-text-primary px-4 py-3.5 text-xs font-semibold uppercase tracking-wider transition-all duration-300"
                        >
                          Upload Photo
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-6 space-y-4">
                      <div className="w-16 h-16 rounded-full bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center mx-auto text-cyan-400 shadow-[0_0_20px_rgba(34,211,238,0.1)]">
                        <Video className="h-8 w-8" />
                      </div>
                      <div className="space-y-1">
                        <p className="text-sm font-medium text-text-primary">Camera Access Required</p>
                        <p className="text-xs text-text-secondary px-4">We will use your camera to take a live selfie for biometric matching.</p>
                      </div>

                      {/* Selfie Recommendations */}
                      <div className="p-3.5 rounded-2xl border border-cyan-500/20 bg-cyan-500/5 text-xs text-text-secondary space-y-1 text-left">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-accent flex items-center gap-1">
                          <Info className="h-3 w-3" /> Selfie Recommendations
                        </span>
                        <ul className="list-disc list-inside space-y-0.5 text-[11px] text-text-secondary">
                          <li>Position face centered in frame</li>
                          <li>Remove sunglasses, hats, or face coverings</li>
                          <li>Maintain neutral expression & good lighting</li>
                          <li>Ensure head is facing straight toward camera</li>
                        </ul>
                      </div>

                      <div className="space-y-3 pt-2">
                        <button
                          onClick={startCamera}
                          className="flex w-full items-center justify-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 text-black px-4 py-4 text-xs font-bold uppercase tracking-widest transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] focus:ring-2 focus:ring-cyan-500/30 outline-none"
                        >
                          Start Camera
                        </button>
                        <button
                          onClick={() => setUseUploadFallback(true)}
                          className="flex w-full items-center justify-center gap-2 rounded-2xl border border-border-color bg-bg-primary/5 text-text-secondary hover:text-text-primary px-4 py-3 text-xs font-semibold uppercase tracking-wider transition-all duration-300"
                        >
                          Upload Photo File
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}

              {verifyingError && verifyingError.failure_code === 'image_quality_check_failed' ? (
                <VerificationQualityError
                  qualityReport={verifyingError.quality_report}
                  onRetry={handleVerifyFace}
                  onSecondaryAction={useUploadFallback ? handleRemoveSelfie : handleRetake}
                  secondaryActionLabel={useUploadFallback ? 'Choose Different File' : 'Retake Photo'}
                />
              ) : verifyingError && (
                <VerificationError
                  title="Identity Verification Failed"
                  message={typeof verifyingError === 'string' ? verifyingError : (verifyingError.detail || 'Identity verification failed.')}
                  reasons={[
                    'Position face centered inside the frame guide',
                    'Maintain a neutral expression without turning head',
                    'Ensure lighting is clear without dark shadows',
                    'Remove sunglasses, hats, or obstructive face coverings'
                  ]}
                  onRetry={handleVerifyFace}
                  onSecondaryAction={useUploadFallback ? handleRemoveSelfie : handleRetake}
                  secondaryActionLabel={useUploadFallback ? 'Choose Different File' : 'Retake Photo'}
                />
              )}

              {!cameraActive && !verifyingError && (
                <div className="space-y-3 pt-2 border-t border-border-color/30">
                  <button
                    onClick={handleVerifyFace}
                    disabled={isVerifying || !selfiePreview}
                    className="flex w-full items-center justify-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 text-black px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] disabled:opacity-40 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400 disabled:shadow-none focus:ring-2 focus:ring-cyan-500/30 outline-none"
                  >
                    Verify Your Identity <ChevronRight className="h-4 w-4" />
                  </button>

                  {selfiePreview && (
                    <button
                      onClick={useUploadFallback ? handleRemoveSelfie : handleRetake}
                      disabled={isVerifying}
                      className="flex w-full items-center justify-center gap-2 rounded-2xl border border-border-color bg-bg-primary/5 text-text-secondary hover:text-text-primary px-4 py-3.5 text-xs font-semibold uppercase tracking-wider transition-all duration-300 disabled:opacity-50"
                    >
                      {useUploadFallback ? 'Choose Different Photo' : 'Retake'}
                    </button>
                  )}
                </div>
              )}
            </VerificationCard>
          ) : null
        ) : !authStatus?.authorized && currentStep === 'authorization' ? (
          <VerificationCard
            key="step_auth"
            title="Representative Authorization"
            subtitle="Evaluating identity against contract representatives"
            icon={UserCheck}
            badgeText="Step 5 of 5"
            estimatedTime="Approx. 30 sec"
            stepProgress="Step 5 of 5"
          >
            <VerificationError
              title="Authorization Denied"
              message={authStatus?.reason || 'Verified identity is not listed as an authorized representative for this contract.'}
              reasons={[
                'Verified National ID name does not match authorized contract representatives',
                'Honorific or transliteration spelling mismatch',
                'Initiator must update representative list if representative has changed'
              ]}
              onRetry={refreshAuthStatus}
            />
          </VerificationCard>
        ) : session?.participant_role === 'cc' ? (
          <motion.div key="role_cc" className="glass-panel rounded-3xl p-8 text-center relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/10 to-transparent opacity-30" />
            <User className="h-16 w-16 text-accent mx-auto mb-4" />
            <h3 className="text-xl font-light text-accent mb-2">View-Only Access</h3>
            <p className="text-sm text-text-secondary mb-6">
              You are a CC recipient on this workflow step. You have view-only authorization.
            </p>
            <button
              onClick={() => handleAction('acknowledge')}
              disabled={isSigning}
              className="flex w-full items-center justify-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 text-black px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] disabled:opacity-50 focus:ring-2 focus:ring-cyan-500/30 outline-none"
            >
              {isSigning ? <RefreshCw className="h-4 w-4 animate-spin" /> : 'Acknowledge & Finish'}
            </button>
          </motion.div>
        ) : session?.participant_role === 'reviewer' ? (
          <motion.div key="role_reviewer" className="glass-panel rounded-3xl p-6 sm:p-8 sticky top-8 space-y-6">
            <h3 className="text-lg font-light text-text-primary mb-2 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
              Reviewer Decisions
            </h3>
            <p className="text-xs text-text-secondary">
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
                className="flex w-full items-center justify-center gap-2 rounded-2xl border border-amber-500/30 bg-amber-500/10 text-amber-500 hover:bg-amber-500/20 hover:shadow-[0_0_20px_rgba(245,158,11,0.1)] px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 disabled:opacity-50"
              >
                {isSigning ? <RefreshCw className="h-4 w-4 animate-spin" /> : 'Return Document'}
              </button>
            </div>
          </motion.div>
        ) : session?.participant_role === 'approver' ? (
          <motion.div key="role_approver" className="glass-panel rounded-3xl p-6 sm:p-8 sticky top-8 space-y-6">
            <h3 className="text-lg font-light text-text-primary mb-2 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
              Approver Decisions
            </h3>
            <p className="text-xs text-text-secondary">
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
                className="flex w-full items-center justify-center gap-2 rounded-2xl border border-red-500/30 bg-red-500/10 text-red-500 hover:bg-red-500/20 hover:shadow-[0_0_20px_rgba(239,68,68,0.1)] px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 disabled:opacity-50"
              >
                {isSigning ? <RefreshCw className="h-4 w-4 animate-spin" /> : 'Reject Document'}
              </button>
            </div>
          </motion.div>
        ) : (
          /* Signature Module Section */
          <motion.div
            key="signature_module"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
            className="space-y-6"
          >
            <div className="glass-panel rounded-3xl p-6 sm:p-8">
              <div className="p-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-center space-y-1 mb-6 shadow-[0_0_20px_rgba(16,185,129,0.1)]">
                <div className="flex items-center justify-center gap-2 font-bold uppercase tracking-wider text-xs">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  Verification Complete — Electronic Signing Enabled
                </div>
                <p className="text-[11px] text-emerald-300/80">
                  All identity and authorization requirements are satisfied. Please apply your electronic signature below.
                </p>
              </div>

              <h3 className="text-lg font-light text-text-primary mb-6 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                Input Electronic Signature
              </h3>

              {/* Signature Method Tabs */}
              <div className="flex gap-2 p-1 rounded-2xl bg-bg-primary/5 border border-border-color mb-8">
                {SIGNATURE_METHODS.map(({ id, label, icon: Icon }) => (
                  <button
                    key={id}
                    onClick={() => setSignatureMethod(id)}
                    className={`relative flex-1 flex flex-col items-center justify-center gap-2 py-3 rounded-xl text-xs font-medium transition-all duration-300 ${signatureMethod === id
                        ? 'text-accent bg-cyan-500/10'
                        : 'text-text-secondary hover:text-text-primary hover:bg-bg-primary/20'
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
                    initial={{ opacity: 0, y: 5 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -5 }}
                    transition={{ duration: 0.2 }}
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
                    initial={{ opacity: 0, y: 5 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -5 }}
                    transition={{ duration: 0.2 }}
                    className="space-y-6"
                  >
                    {!uploadPreview ? (
                      <label className="flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-border-color bg-card-bg p-8 cursor-pointer transition-all hover:border-cyan-500/30 hover:bg-cyan-500/5">
                        <Upload className="h-8 w-8 text-accent/60" />
                        <div className="text-center">
                          <p className="text-sm text-text-primary">Select Image File</p>
                          <p className="text-xs text-text-secondary mt-1">PNG or JPG formats supported</p>
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
                      <div className="relative rounded-2xl border border-border-color bg-bg-primary/5 p-4">
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
                    initial={{ opacity: 0, y: 5 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -5 }}
                    transition={{ duration: 0.2 }}
                    className="space-y-4"
                  >
                    <div className="rounded-2xl border border-border-color bg-white overflow-hidden shadow-inner relative">
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
                      <span className="text-xs text-text-secondary">Trace within the bounds</span>
                      <button
                        onClick={handleClearCanvas}
                        disabled={isSigning || isDrawEmpty}
                        className="text-xs font-medium text-text-secondary hover:text-text-primary disabled:opacity-50"
                      >
                        Clear Traces
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              <motion.button
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.99 }}
                onClick={handleSign}
                disabled={isSigning}
                className="group relative mt-8 flex w-full items-center justify-center gap-2 overflow-hidden rounded-2xl bg-cyan-500 px-4 py-4 text-sm font-bold text-black transition-all hover:bg-cyan-400 hover:shadow-[0_0_30px_rgba(34,211,238,0.4)] disabled:cursor-not-allowed disabled:opacity-50 uppercase tracking-widest focus:ring-2 focus:ring-cyan-500/30 outline-none"
              >
                <span className="relative z-10 flex items-center gap-2">
                  {isSigning ? (
                    <>
                      <RefreshCw className="h-4 w-4 animate-spin" />
                      Signing Document...
                    </>
                  ) : (
                    <>
                      {t('sign.sign_document')}
                    </>
                  )}
                </span>
                <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/40 to-transparent group-hover:animate-[shimmer_1.5s_infinite]" />
              </motion.button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )

  // ── Main Page Component Output ──────────────────────────────────────────────
  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:py-20 relative z-10 font-sans">

      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: 'easeInOut' }}
        className="mb-10 text-center max-w-2xl mx-auto"
      >
        <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-medium uppercase tracking-widest text-cyan-400 mb-4 backdrop-blur-md">
          <ShieldCheck className="h-4 w-4" />
          Guided Verification Wizard
        </div>
        <h1 className="text-3xl sm:text-5xl font-light text-white neon-text-glow tracking-tight">
          Authorize Payload
        </h1>
        <p className="mt-3 text-zinc-400">Complete identity verification steps to unlock digital signature authorization.</p>
      </motion.div>

      {/* Loading Session */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 text-cyan-500">
          <RefreshCw className="h-10 w-10 animate-spin" />
          <span className="mt-4 text-sm font-medium tracking-widest uppercase animate-pulse">Decrypting Session…</span>
        </div>
      ) : null}

      {/* Top-level Error Alert */}
      <AnimatePresence>
        {!isLoading && error ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.2 }}
            className="mb-8 flex items-center gap-3 rounded-2xl border border-red-500/30 bg-red-500/10 px-6 py-4 text-sm text-red-200 backdrop-blur-md shadow-[0_0_30px_rgba(239,68,68,0.1)]"
            role="alert"
            aria-live="polite"
          >
            <AlertCircle className="h-6 w-6 text-red-400 shrink-0" />
            <p className="font-medium text-base">{error}</p>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {/* Main Content Layout */}
      {!isLoading && session ? (
        isPending ? (
          <WorkflowPendingScreen session={session} />
        ) : (
          <VerificationLayout
            leftColumn={leftColumnContent}
            rightColumn={rightColumnContent}
          />
        )
      ) : null}
    </div>
  )
}
