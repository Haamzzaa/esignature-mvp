import React from 'react'
import { Check, Lock, AlertTriangle, ShieldCheck, FileText, Mail, CreditCard, Camera, UserCheck, PenTool } from 'lucide-react'
import { useLocale } from '../../context/LocaleContext'

export const VERIFICATION_STAGES = [
  { id: 'terms', labelKey: 'verification.stage_terms', icon: FileText, titleKey: 'verification.stage_terms_title' },
  { id: 'email', labelKey: 'verification.stage_email', icon: Mail, titleKey: 'verification.stage_email_title' },
  { id: 'national_id', labelKey: 'verification.stage_id', icon: CreditCard, titleKey: 'verification.stage_id_title' },
  { id: 'face', labelKey: 'verification.stage_face', icon: Camera, titleKey: 'verification.stage_face_title' },
  { id: 'authorization', labelKey: 'verification.stage_auth', icon: UserCheck, titleKey: 'verification.stage_auth_title' },
  { id: 'sign', labelKey: 'verification.stage_sign', icon: PenTool, titleKey: 'verification.stage_sign_title' },
]

export default function VerificationStepper({ currentStageId, completedStages = [], failedStageId = null, onSelectStage }) {
  const { t } = useLocale()
  const currentIndex = VERIFICATION_STAGES.findIndex(s => s.id === currentStageId)

  return (
    <div className="glass-panel rounded-3xl p-4 sm:p-5 space-y-4">
      <div className="flex items-center justify-between border-b border-border-color pb-3">
        <div className="flex items-center gap-2 text-text-primary">
          <ShieldCheck className="h-4 w-4 text-accent animate-pulse" />
          <span className="text-xs font-semibold uppercase tracking-wider">{t('verification.workflow_title')}</span>
        </div>
        <span className="text-[10px] font-mono text-text-secondary" dir="ltr">
          {t('verification.step_indicator', { current: Math.max(1, currentIndex + 1), total: VERIFICATION_STAGES.length })}
        </span>
      </div>

      {/* Desktop & Tablet Progress Bar */}
      <div className="relative flex items-center justify-between">
        {/* Connection Line */}
        <div className="absolute top-4 left-4 right-4 h-0.5 bg-border-color -z-0" />
        <div
          className="absolute top-4 left-4 rtl:right-4 rtl:left-auto h-0.5 bg-cyan-500/50 transition-all duration-500 -z-0"
          style={{ width: `${Math.max(0, (currentIndex / (VERIFICATION_STAGES.length - 1)) * 100)}%` }}
        />

        {VERIFICATION_STAGES.map((stage, idx) => {
          const isCompleted = completedStages.includes(stage.id)
          const isCurrent = stage.id === currentStageId
          const isFailed = stage.id === failedStageId
          const isPast = idx < currentIndex || isCompleted
          const Icon = stage.icon

          let state = 'pending'
          if (isFailed) state = 'failed'
          else if (isCompleted) state = 'completed'
          else if (isCurrent) state = 'current'

          return (
            <div key={stage.id} className="relative z-10 flex flex-col items-center">
              <button
                type="button"
                onClick={() => isPast && onSelectStage && onSelectStage(stage.id)}
                disabled={!isPast}
                className={`relative flex h-8 w-8 items-center justify-center rounded-xl border text-xs font-bold transition-all duration-300 cursor-pointer ${
                  state === 'completed'
                    ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.15)]'
                    : state === 'current'
                    ? 'border-cyan-500/60 bg-cyan-500/20 text-accent shadow-[0_0_20px_rgba(34,211,238,0.3)] ring-2 ring-cyan-500/30 scale-110'
                    : state === 'failed'
                    ? 'border-red-500/50 bg-red-500/10 text-red-400 shadow-[0_0_15px_rgba(239,68,68,0.2)]'
                    : 'border-border-color bg-card-bg text-text-secondary/40'
                }`}
                title={t(stage.titleKey)}
              >
                {state === 'completed' ? (
                  <Check className="h-4 w-4 stroke-[3]" />
                ) : state === 'failed' ? (
                  <AlertTriangle className="h-4 w-4 text-red-400" />
                ) : state === 'current' ? (
                  <Icon className="h-4 w-4 text-accent animate-pulse" />
                ) : (
                  <Lock className="h-3.5 w-3.5 opacity-50" />
                )}
              </button>

              <span className={`mt-1.5 text-[10px] font-medium tracking-tight truncate max-w-[55px] text-center ${
                isCurrent ? 'text-accent font-bold' : isCompleted ? 'text-emerald-400' : isFailed ? 'text-red-400' : 'text-text-secondary/60'
              }`}>
                {t(stage.labelKey)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
