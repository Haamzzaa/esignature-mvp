import React from 'react'
import { ShieldCheck, CheckCircle2, Clock } from 'lucide-react'
import { useLocale } from '../../context/LocaleContext'

export default function VerificationStatus({ authStatus, currentStageId = null }) {
  const { t } = useLocale()
  if (!authStatus) return null

  const requirements = authStatus.requirements || {}

  const items = [
    {
      key: 'terms',
      label: t('sign.terms_card_title'),
      required: requirements.terms_acceptance?.required ?? true,
      satisfied: requirements.terms_acceptance?.satisfied ?? false,
    },
    {
      key: 'email',
      label: t('sign.email_card_title'),
      required: requirements.email_otp?.required ?? true,
      satisfied: requirements.email_otp?.satisfied ?? false,
    },
    {
      key: 'national_id',
      label: t('sign.id_card_title'),
      required: requirements.national_id?.required ?? true,
      satisfied: requirements.national_id?.satisfied ?? false,
    },
    {
      key: 'face',
      label: t('sign.face_card_title'),
      required: requirements.face_biometric?.required ?? true,
      satisfied: requirements.face_biometric?.satisfied ?? false,
    },
    {
      key: 'authorization',
      label: t('sign.rep_auth_title'),
      required: requirements.representative_match?.required ?? true,
      satisfied: requirements.representative_match?.satisfied ?? false,
    },
  ].filter(i => i.required)

  return (
    <div className="glass-panel rounded-2xl p-4 space-y-3 border border-border-color/80">
      <div className="flex items-center justify-between border-b border-border-color/40 pb-2.5">
        <div className="flex items-center gap-1.5 text-text-primary">
          <ShieldCheck className="h-4 w-4 text-cyan-400" />
          <span className="text-[11px] font-semibold uppercase tracking-wider text-text-secondary">
            {t('verification.session_status')}
          </span>
        </div>
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider ${
          authStatus.authorized
            ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400'
            : 'bg-cyan-500/10 border border-cyan-500/30 text-accent'
        }`}>
          {authStatus.authorized ? t('verification.ready_to_sign') : t('verification.active_session')}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-1.5 text-xs">
        {items.map(item => {
          const isSatisfied = item.satisfied
          const isCurrent = currentStageId === item.key && !isSatisfied

          return (
            <div key={item.key} className="flex items-center justify-between py-1 px-2 rounded-lg hover:bg-white/[0.02] transition-colors">
              <span className={`text-xs ${isSatisfied ? 'text-text-primary font-normal' : isCurrent ? 'text-accent font-medium' : 'text-text-secondary/70'}`}>
                {item.label}
              </span>
              {isSatisfied ? (
                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-400">
                  <CheckCircle2 className="h-3.5 w-3.5" /> {t('verification.status_verified')}
                </span>
              ) : isCurrent ? (
                <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-cyan-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-ping" />
                  <span>Current</span>
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-[11px] text-text-secondary/50">
                  <Clock className="h-3 w-3 text-text-secondary/40" /> {t('common.status_pending')}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
