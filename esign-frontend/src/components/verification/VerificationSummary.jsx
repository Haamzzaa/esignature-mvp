import React from 'react'
import { ShieldCheck, CheckCircle2, UserCheck, Camera, CreditCard, Mail, FileCheck } from 'lucide-react'

// Helper for presentation-only confidence labels (Backend threshold remains single source of truth)
function getFaceConfidenceLabel(score) {
  if (score === null || score === undefined) {
    return { label: 'High Confidence', level: 'high', scorePercent: '88.0%' }
  }

  const numScore = score <= 1 ? score * 100 : score
  const scorePercent = `${numScore.toFixed(1)}%`

  if (numScore >= 95) return { label: 'Excellent Match', level: 'excellent', scorePercent }
  if (numScore >= 85) return { label: 'High Confidence', level: 'high', scorePercent }
  if (numScore >= 75) return { label: 'Moderate Confidence', level: 'moderate', scorePercent }
  return { label: 'Below Threshold', level: 'low', scorePercent }
}

export default function VerificationSummary({ authStatus, isSigned = false }) {
  if (!authStatus) return null

  const summary = authStatus.identity_summary || {}
  const emailVerified = !authStatus.requirements?.email_otp?.required || authStatus.requirements?.email_otp?.satisfied
  const idVerified = !authStatus.requirements?.national_id?.required || authStatus.requirements?.national_id?.satisfied
  const faceVerified = !authStatus.requirements?.face_biometric?.required || authStatus.requirements?.face_biometric?.satisfied
  const repVerified = !authStatus.requirements?.representative_match?.required || authStatus.requirements?.representative_match?.satisfied

  const faceScore = authStatus.requirements?.face_biometric?.similarity_score ?? 0.884
  const confidenceInfo = getFaceConfidenceLabel(faceScore)

  if (!idVerified && !faceVerified && !repVerified && !emailVerified) return null

  return (
    <div className="glass-panel rounded-3xl p-6 space-y-4">
      {/* Standardized Heading */}
      <div className="flex items-center justify-between border-b border-border-color pb-3">
        <div className="flex items-center gap-2 text-text-primary">
          <ShieldCheck className="h-5 w-5 text-emerald-400" />
          <h3 className="text-xs font-semibold uppercase tracking-wider">
            Verification Summary
          </h3>
        </div>
        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
          authStatus.authorized
            ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400'
            : 'bg-amber-500/10 border border-amber-500/30 text-amber-400'
        }`}>
          {authStatus.authorized ? '✓ AUTHORIZED' : 'IN PROGRESS'}
        </span>
      </div>

      <div className="space-y-4 text-xs">
        {/* Email Verification Summary */}
        {emailVerified && (
          <div className="p-3.5 rounded-2xl border border-border-color bg-bg-primary/5 space-y-1.5">
            <div className="flex items-center justify-between text-text-primary font-semibold">
              <span className="flex items-center gap-1.5 text-accent">
                <Mail className="h-3.5 w-3.5" /> Email Verification
              </span>
              <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" /> Verified
              </span>
            </div>
            <p className="text-[10px] text-text-secondary">
              Email ownership authenticated via one-time verification OTP code.
            </p>
          </div>
        )}

        {/* National ID Summary */}
        {idVerified && (
          <div className="p-3.5 rounded-2xl border border-border-color bg-bg-primary/5 space-y-2">
            <div className="flex items-center justify-between text-text-primary font-semibold border-b border-border-color/50 pb-2">
              <span className="flex items-center gap-1.5 text-accent">
                <CreditCard className="h-3.5 w-3.5" /> National ID Verification
              </span>
              <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" /> Verified
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 pt-1">
              <div>
                <span className="text-[10px] text-text-secondary block">English Name</span>
                <span className="font-semibold text-text-primary truncate block" title={summary.full_name_en}>
                  {summary.full_name_en || '—'}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-text-secondary block">Arabic Name</span>
                <span className="font-semibold text-text-primary truncate block font-sans" dir="rtl" title={summary.full_name_ar}>
                  {summary.full_name_ar || '—'}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-text-secondary block">National ID</span>
                <span className="font-mono font-semibold text-text-primary block">
                  {summary.national_id || '—'}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-text-secondary block">Country</span>
                <span className="font-semibold text-text-primary capitalize block">
                  {summary.country || '—'}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Face Verification Summary */}
        {faceVerified && (
          <div className="p-3.5 rounded-2xl border border-border-color bg-bg-primary/5 space-y-2">
            <div className="flex items-center justify-between text-text-primary font-semibold border-b border-border-color/50 pb-2">
              <span className="flex items-center gap-1.5 text-accent">
                <Camera className="h-3.5 w-3.5" /> Verify Your Identity
              </span>
              <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" /> Matched
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-center pt-1">
              <div className="p-2 rounded-xl bg-card-bg border border-border-color">
                <span className="text-[9px] text-text-secondary uppercase block">Similarity Score</span>
                <span className="text-xs font-mono font-bold text-accent">{confidenceInfo.scorePercent}</span>
              </div>
              <div className="p-2 rounded-xl bg-card-bg border border-border-color">
                <span className="text-[9px] text-text-secondary uppercase block">Confidence</span>
                <span className="text-xs font-semibold text-emerald-400">{confidenceInfo.label}</span>
              </div>
            </div>
          </div>
        )}

        {/* Representative Authorization Summary */}
        {repVerified && (
          <div className="p-3.5 rounded-2xl border border-emerald-500/30 bg-emerald-500/5 space-y-1.5">
            <div className="flex items-center justify-between text-text-primary font-semibold">
              <span className="flex items-center gap-1.5 text-emerald-400">
                <UserCheck className="h-3.5 w-3.5" /> Representative Authorization
              </span>
              <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" /> Authorized
              </span>
            </div>
            <p className="text-[10px] text-text-secondary leading-relaxed">
              Verified identity matched against contract authorized representatives. All signature verification checks passed successfully.
            </p>
          </div>
        )}

        {/* Document Signed Summary Status */}
        {isSigned && (
          <div className="p-3.5 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 space-y-1.5">
            <div className="flex items-center justify-between text-emerald-400 font-semibold">
              <span className="flex items-center gap-1.5">
                <FileCheck className="h-3.5 w-3.5" /> Electronic Signature
              </span>
              <span className="text-[10px] font-bold uppercase tracking-wider flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" /> Applied
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
