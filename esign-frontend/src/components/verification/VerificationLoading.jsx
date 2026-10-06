import React from 'react'
import { RefreshCw, ShieldCheck } from 'lucide-react'
import { useLocale } from '../../context/LocaleContext'

export default function VerificationLoading({ stageId = 'national_id', customMessage = null }) {
  const { t } = useLocale()

  return (
    <div
      role="status"
      aria-live="polite"
      className="py-8 px-4 sm:px-6 text-center flex flex-col items-center justify-center space-y-5 font-sans"
    >
      {/* Pulse Glow Container */}
      <div className="relative flex items-center justify-center">
        <div className="absolute inset-0 rounded-full bg-cyan-500/20 blur-xl animate-pulse w-20 h-20" />
        <div className="relative h-16 w-16 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-accent shadow-[0_0_30px_rgba(34,211,238,0.25)]">
          <RefreshCw className="h-8 w-8 animate-spin" />
        </div>
      </div>

      {/* User-focused status messaging */}
      <div className="space-y-2 max-w-sm">
        <h4 className="text-base font-medium tracking-wide text-text-primary">
          {t('sign.processing_verification')}
        </h4>
        <p className="text-xs text-text-secondary leading-relaxed">
          {customMessage || t('sign.communicating_id_services')}
        </p>
      </div>

      <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-cyan-500/20 bg-cyan-500/5 text-[11px] font-medium text-cyan-400">
        <ShieldCheck className="h-3.5 w-3.5" />
        <span>Automated Secure Verification</span>
      </div>
    </div>
  )
}
