import React, { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  RotateCcw,
  User,
  FileText,
  Clock,
  Camera,
  Fingerprint,
  FileCheck,
  Building2,
  AlertCircle,
  Loader2,
  Send,
  Eye
} from 'lucide-react'
import { getReviewDetail, submitReviewDecision, API_URL } from '../../services/api'

export default function ReviewDossierModal({ participantId, isOpen, onClose, onDecisionMade }) {
  const [dossier, setDossier] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Decision state
  const [actionTab, setActionTab] = useState('approve') // 'approve' | 'resubmit' | 'reject'
  const [notes, setNotes] = useState('')
  const [targetStep, setTargetStep] = useState('national_id')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  useEffect(() => {
    if (!isOpen || !participantId) return

    let isMounted = true
    setLoading(true)
    setError(null)
    setSubmitError(null)
    setNotes('')

    getReviewDetail(participantId)
      .then((data) => {
        if (isMounted) {
          setDossier(data)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err.response?.data?.detail || 'Failed to load review case dossier.')
          setLoading(false)
        }
      })

    return () => {
      isMounted = false
    }
  }, [isOpen, participantId])

  if (!isOpen) return null

  const handleDecision = async () => {
    if (actionTab === 'reject' && !notes.trim()) {
      setSubmitError('A rejection reason is required.')
      return
    }
    if (actionTab === 'resubmit' && !targetStep) {
      setSubmitError('Please select a target verification step.')
      return
    }

    setSubmitting(true)
    setSubmitError(null)

    try {
      const payload = {
        action: actionTab,
        notes: notes.trim(),
        target_step: actionTab === 'resubmit' ? targetStep : undefined
      }

      await submitReviewDecision(participantId, payload)
      if (onDecisionMade) {
        onDecisionMade(participantId, actionTab)
      }
      onClose()
    } catch (err) {
      setSubmitError(err.response?.data?.detail || 'Failed to submit review decision.')
    } finally {
      setSubmitting(false)
    }
  }

  const getMediaUrl = (path) => {
    if (!path) return null
    if (path.startsWith('http')) return path
    return `${API_URL || ''}${path}`
  }

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto bg-black/80 backdrop-blur-md">
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          className="relative w-full max-w-5xl my-8 rounded-2xl glass-panel border border-cyan-500/20 bg-bg-surface/95 shadow-2xl shadow-cyan-950/40 flex flex-col max-h-[90vh] overflow-hidden"
        >
          {/* Header */}
          <div className="flex items-center justify-between p-5 border-b border-border-color bg-bg-surface/60">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
                <ShieldCheck className="h-6 w-6" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-bold text-text-primary">
                    Manual Authorization Review
                  </h3>
                  {dossier?.review_state?.review_status && (
                    <span className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full border ${
                      dossier.review_state.review_status === 'under_review'
                        ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                        : dossier.review_state.review_status === 'approved'
                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                        : dossier.review_state.review_status === 'rejected'
                        ? 'bg-red-500/10 text-red-400 border-red-500/30'
                        : 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30'
                    }`}>
                      {dossier.review_state.review_status.replace('_', ' ')}
                    </span>
                  )}
                </div>
                <p className="text-xs text-text-secondary mt-0.5">
                  Participant #{participantId} &bull; {dossier?.envelope?.title || 'Package Review'}
                </p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-xl text-text-secondary hover:text-text-primary hover:bg-bg-primary transition-colors cursor-pointer"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {loading ? (
              <div className="flex flex-col items-center justify-center py-20 text-cyan-400">
                <Loader2 className="h-8 w-8 animate-spin mb-3" />
                <span className="text-xs font-medium tracking-wide text-text-secondary">Loading review case dossier...</span>
              </div>
            ) : error ? (
              <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm flex items-center gap-3">
                <AlertCircle className="h-5 w-5 shrink-0" />
                <span>{error}</span>
              </div>
            ) : dossier ? (
              <>
                {/* Review Reason Highlight */}
                {dossier.review_state?.review_reason && (
                  <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 flex items-start gap-3">
                    <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5 text-amber-400" />
                    <div>
                      <div className="text-xs font-bold uppercase tracking-wider text-amber-400">Review Trigger Reason</div>
                      <div className="text-sm font-medium mt-0.5">{dossier.review_state.review_reason}</div>
                    </div>
                  </div>
                )}

                {/* Participant & Envelope Overview */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 rounded-xl glass-panel bg-bg-surface/50 border border-border-color space-y-2">
                    <div className="text-xs font-bold uppercase tracking-wider text-text-secondary flex items-center gap-1.5">
                      <User className="h-3.5 w-3.5 text-cyan-400" /> Participant Details
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs pt-1">
                      <div>
                        <span className="text-text-secondary">Name:</span>
                        <div className="font-semibold text-text-primary">{dossier.participant.name}</div>
                      </div>
                      <div>
                        <span className="text-text-secondary">Email:</span>
                        <div className="font-semibold text-text-primary truncate">{dossier.participant.email}</div>
                      </div>
                      <div>
                        <span className="text-text-secondary">Role:</span>
                        <div className="font-semibold text-text-primary capitalize">{dossier.participant.role}</div>
                      </div>
                      <div>
                        <span className="text-text-secondary">Workflow Status:</span>
                        <div className="font-semibold text-text-primary capitalize">{dossier.participant.status}</div>
                      </div>
                    </div>
                  </div>

                  <div className="p-4 rounded-xl glass-panel bg-bg-surface/50 border border-border-color space-y-2">
                    <div className="text-xs font-bold uppercase tracking-wider text-text-secondary flex items-center gap-1.5">
                      <FileText className="h-3.5 w-3.5 text-cyan-400" /> Envelope Details
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs pt-1">
                      <div>
                        <span className="text-text-secondary">Envelope ID:</span>
                        <div className="font-semibold text-text-primary">#{dossier.envelope.id}</div>
                      </div>
                      <div>
                        <span className="text-text-secondary">Status:</span>
                        <div className="font-semibold text-text-primary capitalize">{dossier.envelope.status}</div>
                      </div>
                      <div className="col-span-2">
                        <span className="text-text-secondary">Title:</span>
                        <div className="font-semibold text-text-primary truncate">{dossier.envelope.title}</div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Identity Verification Section */}
                <div className="p-5 rounded-xl glass-panel bg-bg-surface/50 border border-border-color space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-bold text-text-primary flex items-center gap-2">
                      <Fingerprint className="h-4 w-4 text-cyan-400" /> National ID Verification Evidence
                    </div>
                    {dossier.identity_verification && (
                      <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full border ${
                        dossier.identity_verification.status === 'verified'
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                          : dossier.identity_verification.status === 'requires_manual_review'
                          ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                          : 'bg-red-500/10 text-red-400 border-red-500/30'
                      }`}>
                        {dossier.identity_verification.status.replace('_', ' ').toUpperCase()}
                      </span>
                    )}
                  </div>

                  {dossier.identity_verification ? (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs bg-bg-primary/40 p-3 rounded-lg">
                        <div>
                          <span className="text-text-secondary">Extracted Name (EN):</span>
                          <div className="font-semibold text-text-primary mt-0.5">{dossier.identity_verification.full_name_en || dossier.identity_verification.full_name || 'N/A'}</div>
                        </div>
                        <div>
                          <span className="text-text-secondary">Extracted Name (AR):</span>
                          <div className="font-semibold text-text-primary mt-0.5 font-arabic">{dossier.identity_verification.full_name_ar || 'N/A'}</div>
                        </div>
                        <div>
                          <span className="text-text-secondary">National ID Number:</span>
                          <div className="font-semibold text-text-primary mt-0.5">{dossier.identity_verification.national_id_number || 'N/A'}</div>
                        </div>
                        <div>
                          <span className="text-text-secondary">Document Match Score:</span>
                          <div className="font-semibold text-cyan-400 mt-0.5">
                            {dossier.identity_verification.identity_match_score != null
                              ? `${(dossier.identity_verification.identity_match_score * 100).toFixed(1)}%`
                              : 'N/A'}
                          </div>
                        </div>
                      </div>

                      {dossier.identity_verification.failure_reason && (
                        <div className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 p-2.5 rounded-lg flex items-center gap-2">
                          <AlertCircle className="h-4 w-4 shrink-0" />
                          <span>Discrepancy: {dossier.identity_verification.failure_reason}</span>
                        </div>
                      )}

                      {/* Images Grid */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                        {dossier.identity_verification.document_image_url && (
                          <div className="space-y-1.5">
                            <span className="text-[11px] font-semibold text-text-secondary uppercase">ID Document Capture</span>
                            <div className="relative rounded-xl overflow-hidden border border-border-color bg-black/40 aspect-[16/10] flex items-center justify-center group">
                              <img
                                src={getMediaUrl(dossier.identity_verification.document_image_url)}
                                alt="National ID Evidence"
                                className="object-contain max-h-full max-w-full"
                              />
                              <a
                                href={getMediaUrl(dossier.identity_verification.document_image_url)}
                                target="_blank"
                                rel="noreferrer"
                                className="absolute top-2 right-2 p-1.5 rounded-lg bg-black/60 text-white hover:bg-black/80 transition-colors opacity-0 group-hover:opacity-100"
                                title="Open full image"
                              >
                                <Eye className="h-4 w-4" />
                              </a>
                            </div>
                          </div>
                        )}

                        {dossier.identity_verification.reference_face_image_url && (
                          <div className="space-y-1.5">
                            <span className="text-[11px] font-semibold text-text-secondary uppercase">Extracted ID Photo Crop</span>
                            <div className="relative rounded-xl overflow-hidden border border-border-color bg-black/40 aspect-[16/10] flex items-center justify-center group">
                              <img
                                src={getMediaUrl(dossier.identity_verification.reference_face_image_url)}
                                alt="Reference Face Crop"
                                className="object-contain max-h-full max-w-full"
                              />
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="text-xs text-text-secondary italic py-2">No national ID verification record submitted yet.</div>
                  )}
                </div>

                {/* Face Biometric Verification Section */}
                <div className="p-5 rounded-xl glass-panel bg-bg-surface/50 border border-border-color space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-bold text-text-primary flex items-center gap-2">
                      <Camera className="h-4 w-4 text-cyan-400" /> Face Biometrics Evidence
                    </div>
                    {dossier.biometric_verification && (
                      <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full border ${
                        dossier.biometric_verification.status === 'matched'
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                          : dossier.biometric_verification.status === 'requires_manual_review'
                          ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                          : 'bg-red-500/10 text-red-400 border-red-500/30'
                      }`}>
                        {dossier.biometric_verification.status.replace('_', ' ').toUpperCase()}
                      </span>
                    )}
                  </div>

                  {dossier.biometric_verification ? (
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs bg-bg-primary/40 p-3 rounded-lg">
                      <div>
                        <span className="text-text-secondary">Similarity Score:</span>
                        <div className="font-semibold text-cyan-400 mt-0.5">
                          {dossier.biometric_verification.similarity_score != null
                            ? `${(dossier.biometric_verification.similarity_score * 100).toFixed(1)}%`
                            : 'N/A'}
                        </div>
                      </div>
                      <div>
                        <span className="text-text-secondary">Liveness Score:</span>
                        <div className="font-semibold text-text-primary mt-0.5">
                          {dossier.biometric_verification.liveness_score != null
                            ? `${(dossier.biometric_verification.liveness_score * 100).toFixed(1)}%`
                            : 'N/A'}
                        </div>
                      </div>
                      <div>
                        <span className="text-text-secondary">Biometric Status:</span>
                        <div className="font-semibold text-text-primary capitalize mt-0.5">
                          {dossier.biometric_verification.status}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="text-xs text-text-secondary italic py-2">No face biometric verification record submitted yet.</div>
                  )}
                </div>

                {/* Representative Authorization Section */}
                <div className="p-5 rounded-xl glass-panel bg-bg-surface/50 border border-border-color space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-bold text-text-primary flex items-center gap-2">
                      <Building2 className="h-4 w-4 text-cyan-400" /> Representative Authorization
                    </div>
                    {dossier.representative_authorization && (
                      <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full border ${
                        dossier.representative_authorization.authorized
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                          : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                      }`}>
                        {dossier.representative_authorization.status || (dossier.representative_authorization.authorized ? 'AUTHORIZED' : 'PENDING')}
                      </span>
                    )}
                  </div>

                  {dossier.representative_authorization && (
                    <div className="space-y-3">
                      {dossier.representative_authorization.contract_representatives?.length > 0 ? (
                        <div>
                          <span className="text-[11px] font-semibold text-text-secondary uppercase block mb-1.5">Contract Extracted Representatives</span>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            {dossier.representative_authorization.contract_representatives.map((rep, idx) => (
                              <div key={idx} className="p-2.5 rounded-lg bg-bg-primary/40 border border-border-color text-xs">
                                <div className="font-semibold text-text-primary">{rep.name_en || rep.name_ar}</div>
                                {rep.title_en && <div className="text-text-secondary text-[11px]">{rep.title_en}</div>}
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : (
                        <div className="text-xs text-text-secondary italic">No representative clauses extracted from contract.</div>
                      )}
                    </div>
                  )}
                </div>

                {/* Audit History */}
                {dossier.audit_history?.length > 0 && (
                  <div className="p-5 rounded-xl glass-panel bg-bg-surface/50 border border-border-color space-y-3">
                    <div className="text-sm font-bold text-text-primary flex items-center gap-2">
                      <Clock className="h-4 w-4 text-cyan-400" /> Audit Log History
                    </div>
                    <div className="max-h-36 overflow-y-auto space-y-1.5 pr-2">
                      {dossier.audit_history.map((log) => (
                        <div key={log.id} className="flex items-center justify-between text-[11px] p-2 rounded bg-bg-primary/30 border border-border-color/50">
                          <span className="font-medium text-text-primary truncate">{log.event}</span>
                          <span className="text-text-secondary shrink-0 ml-2">
                            {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : null}
          </div>

          {/* Decision Actions Footer */}
          {dossier && (
            <div className="p-5 border-t border-border-color bg-bg-surface/80 space-y-4">
              {/* Action Tabs */}
              <div className="flex items-center gap-2 border-b border-border-color/60 pb-3">
                <button
                  type="button"
                  onClick={() => setActionTab('approve')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 ${
                    actionTab === 'approve'
                      ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                      : 'text-text-secondary hover:text-text-primary hover:bg-bg-primary/50'
                  }`}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" /> Approve
                </button>
                <button
                  type="button"
                  onClick={() => setActionTab('resubmit')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 ${
                    actionTab === 'resubmit'
                      ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                      : 'text-text-secondary hover:text-text-primary hover:bg-bg-primary/50'
                  }`}
                >
                  <RotateCcw className="h-3.5 w-3.5" /> Request Resubmission
                </button>
                <button
                  type="button"
                  onClick={() => setActionTab('reject')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 ${
                    actionTab === 'reject'
                      ? 'bg-red-500/20 text-red-400 border border-red-500/40'
                      : 'text-text-secondary hover:text-text-primary hover:bg-bg-primary/50'
                  }`}
                >
                  <XCircle className="h-3.5 w-3.5" /> Reject
                </button>
              </div>

              {/* Action Form Inputs */}
              <div className="space-y-3">
                {actionTab === 'resubmit' && (
                  <div>
                    <label className="text-xs font-semibold text-text-secondary block mb-1">
                      Required Resubmission Step:
                    </label>
                    <select
                      value={targetStep}
                      onChange={(e) => setTargetStep(e.target.value)}
                      className="w-full sm:w-64 px-3 py-2 text-xs rounded-xl bg-bg-primary border border-border-color text-text-primary focus:outline-none focus:border-cyan-500"
                    >
                      <option value="national_id">National ID Document</option>
                      <option value="face">Face Biometric / Selfie</option>
                    </select>
                  </div>
                )}

                <div>
                  <label className="text-xs font-semibold text-text-secondary block mb-1">
                    {actionTab === 'approve'
                      ? 'Reviewer Approval Note (Optional):'
                      : actionTab === 'resubmit'
                      ? 'Instructions for Signer (Will be shown to user):'
                      : 'Rejection Reason (Required):'}
                  </label>
                  <textarea
                    rows={2}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder={
                      actionTab === 'approve'
                        ? 'e.g. Identity variance verified and approved.'
                        : actionTab === 'resubmit'
                        ? 'e.g. Please capture a clearer photo without glare.'
                        : 'e.g. Identity document appears fraudulent or altered.'
                    }
                    className="w-full px-3 py-2 text-xs rounded-xl bg-bg-primary border border-border-color text-text-primary placeholder:text-text-secondary/50 focus:outline-none focus:border-cyan-500"
                  />
                </div>

                {submitError && (
                  <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 p-2 rounded-lg flex items-center gap-2">
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    <span>{submitError}</span>
                  </div>
                )}
              </div>

              {/* Buttons */}
              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={onClose}
                  disabled={submitting}
                  className="px-4 py-2 text-xs font-semibold text-text-secondary hover:text-text-primary hover:bg-bg-primary/60 rounded-xl transition-colors"
                >
                  Cancel
                </button>

                <button
                  type="button"
                  onClick={handleDecision}
                  disabled={submitting}
                  className={`px-5 py-2 text-xs font-bold rounded-xl flex items-center gap-2 transition-all cursor-pointer ${
                    actionTab === 'approve'
                      ? 'bg-emerald-500 hover:bg-emerald-400 text-black shadow-lg shadow-emerald-500/20'
                      : actionTab === 'resubmit'
                      ? 'bg-amber-500 hover:bg-amber-400 text-black shadow-lg shadow-amber-500/20'
                      : 'bg-red-500 hover:bg-red-400 text-white shadow-lg shadow-red-500/20'
                  }`}
                >
                  {submitting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-3.5 w-3.5" />
                  )}
                  {actionTab === 'approve'
                    ? 'Confirm Approval'
                    : actionTab === 'resubmit'
                    ? 'Request Resubmission'
                    : 'Confirm Rejection'}
                </button>
              </div>
            </div>
          )}
        </motion.div>
      </div>
    </AnimatePresence>
  )
}
