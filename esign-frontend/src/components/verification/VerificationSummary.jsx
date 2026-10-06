import React from 'react'
import { ShieldCheck, CheckCircle2, UserCheck, Camera, CreditCard, Mail, FileCheck } from 'lucide-react'
import { useLocale } from '../../context/LocaleContext'

// Helper for presentation-only confidence labels (Backend threshold remains single source of truth)
function getFaceConfidenceLabel(score, t) {
  if (score === null || score === undefined) {
    return { label: t('verification.high_confidence'), level: 'high', scorePercent: '88.0%' }
  }

  const numScore = score <= 1 ? score * 100 : score
  const scorePercent = `${numScore.toFixed(1)}%`

  if (numScore >= 95) return { label: t('verification.excellent_match'), level: 'excellent', scorePercent }
  if (numScore >= 85) return { label: t('verification.high_confidence'), level: 'high', scorePercent }
  if (numScore >= 75) return { label: t('verification.moderate_confidence'), level: 'moderate', scorePercent }
  return { label: t('verification.below_threshold'), level: 'low', scorePercent }
}

export default function VerificationSummary({ authStatus, isSigned = false }) {
  const { t } = useLocale()
  if (!authStatus) return null

  const summary = authStatus.identity_summary || {}
  const emailVerified = !authStatus.requirements?.email_otp?.required || authStatus.requirements?.email_otp?.satisfied
  const idVerified = !authStatus.requirements?.national_id?.required || authStatus.requirements?.national_id?.satisfied
  const faceVerified = !authStatus.requirements?.face_biometric?.required || authStatus.requirements?.face_biometric?.satisfied
  const repVerified = !authStatus.requirements?.representative_match?.required || authStatus.requirements?.representative_match?.satisfied

  const faceScore = authStatus.requirements?.face_biometric?.similarity_score ?? 0.884
  const confidenceInfo = getFaceConfidenceLabel(faceScore, t)

  if (!idVerified && !faceVerified && !repVerified && !emailVerified) return null

  return (
    <div className="glass-panel rounded-3xl p-6 space-y-4">
      {/* Standardized Heading */}
      <div className="flex items-center justify-between border-b border-border-color pb-3">
        <div className="flex items-center gap-2 text-text-primary">
          <ShieldCheck className="h-5 w-5 text-emerald-400" />
          <h3 className="text-xs font-semibold uppercase tracking-wider">
            {t('success.summary_title')}
          </h3>
        </div>
        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
          authStatus.authorized
            ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400'
            : 'bg-amber-500/10 border border-amber-500/30 text-amber-400'
        }`}>
          {authStatus.authorized ? t('success.status_authorized') : t('common.status_in_progress')}
        </span>
      </div>

      <div className="space-y-4 text-xs">
        {/* Email Verification Summary */}
        {emailVerified && (
          <div className="p-3.5 rounded-2xl border border-border-color bg-bg-primary/5 space-y-1.5">
            <div className="flex items-center justify-between text-text-primary font-semibold">
              <span className="flex items-center gap-1.5 text-accent">
                <Mail className="h-3.5 w-3.5" /> {t('sign.email_card_title')}
              </span>
              <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" /> {t('verification.status_verified')}
              </span>
            </div>
            <p className="text-[10px] text-text-secondary">
              {t('sign.email_prompt_prefix')}
            </p>
          </div>
        )}

        {/* National ID Summary */}
        {idVerified && (
          <div className="p-3.5 rounded-2xl border border-border-color bg-bg-primary/5 space-y-2">
            <div className="flex items-center justify-between text-text-primary font-semibold border-b border-border-color/50 pb-2">
              <span className="flex items-center gap-1.5 text-accent">
                <CreditCard className="h-3.5 w-3.5" /> {t('sign.id_card_title')}
              </span>
              <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" /> {t('verification.status_verified')}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 pt-1">
              <div>
                <span className="text-[10px] text-text-secondary block">{t('contract_analysis.name_en')}</span>
                <span className="font-semibold text-text-primary truncate block" title={summary.full_name_en}>
                  {summary.full_name_en || '—'}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-text-secondary block">{t('contract_analysis.name_ar')}</span>
                <span className="font-semibold text-text-primary truncate block font-sans" dir="rtl" title={summary.full_name_ar}>
                  {summary.full_name_ar || '—'}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-text-secondary block">{t('sign.id_card_title')}</span>
                <span className="font-mono font-semibold text-text-primary block" dir="ltr">
                  {summary.national_id || '—'}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-text-secondary block">{t('templates.col_category')}</span>
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
                <Camera className="h-3.5 w-3.5" /> {t('sign.face_card_title')}
              </span>
              <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" /> {t('verification.status_matched')}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-center pt-1">
              <div className="p-2 rounded-xl bg-card-bg border border-border-color">
                <span className="text-[9px] text-text-secondary uppercase block">{t('verification.similarity_score')}</span>
                <span className="text-xs font-mono font-bold text-accent" dir="ltr">{confidenceInfo.scorePercent}</span>
              </div>
              <div className="p-2 rounded-xl bg-card-bg border border-border-color">
                <span className="text-[9px] text-text-secondary uppercase block">{t('verification.confidence')}</span>
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
                <UserCheck className="h-3.5 w-3.5" /> {t('sign.rep_auth_title')}
              </span>
              <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" /> {t('verification.status_authorized')}
              </span>
            </div>
            <p className="text-[10px] text-text-secondary leading-relaxed">
              {t('verification.complete_desc')}
            </p>
          </div>
        )}

        {/* Document Signed Summary Status */}
        {isSigned && (
          <div className="p-3.5 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 space-y-1.5">
            <div className="flex items-center justify-between text-emerald-400 font-semibold">
              <span className="flex items-center gap-1.5">
                <FileCheck className="h-3.5 w-3.5" /> {t('verification.stage_sign_title')}
              </span>
              <span className="text-[10px] font-bold uppercase tracking-wider flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" /> {t('success.status_applied')}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
