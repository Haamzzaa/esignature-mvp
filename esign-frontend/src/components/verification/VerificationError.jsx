import React from 'react'
import { AlertCircle, RefreshCw, HelpCircle, Info } from 'lucide-react'

export default function VerificationError({
  title,
  message,
  reasons = [],
  onRetry,
  onSecondaryAction,
  secondaryActionLabel
}) {
  return (
    <div className="glass-panel rounded-3xl p-6 sm:p-8 space-y-5 border-red-500/30 relative overflow-hidden font-sans">
      <div className="absolute inset-0 bg-gradient-to-br from-red-500/10 via-transparent to-transparent opacity-50 pointer-events-none" />

      <div className="flex items-start gap-3.5">
        <div className="h-10 w-10 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center text-red-400 shrink-0 shadow-[0_0_15px_rgba(239,68,68,0.15)]">
          <AlertCircle className="h-5 w-5" />
        </div>
        <div className="space-y-1 text-left">
          <h3 className="text-sm font-semibold text-red-400 tracking-tight">
            {title || 'Verification Action Required'}
          </h3>
          <p className="text-xs text-text-secondary leading-relaxed">
            {message || 'Unable to complete verification step with the provided details.'}
          </p>
        </div>
      </div>

      {/* Contextual Failure Recovery Guidance */}
      {reasons.length > 0 && (
        <div className="p-4 rounded-2xl border border-red-500/20 bg-red-500/5 text-xs text-text-secondary space-y-2 text-left">
          <div className="flex items-center gap-1.5 font-semibold text-red-300">
            <HelpCircle className="h-3.5 w-3.5" /> Actionable Recovery Guidance:
          </div>
          <ul className="list-disc list-inside space-y-1 text-text-secondary/90 pl-1 text-[11px]">
            {reasons.map((reason, idx) => (
              <li key={idx}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Action Controls */}
      <div className="flex flex-col sm:flex-row gap-3 pt-1">
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="flex-1 flex items-center justify-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 text-black px-4 py-3.5 text-xs font-bold uppercase tracking-wider transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] focus:ring-2 focus:ring-cyan-500/30 outline-none"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Try Again
          </button>
        )}

        {onSecondaryAction && secondaryActionLabel && (
          <button
            type="button"
            onClick={onSecondaryAction}
            className="flex-1 flex items-center justify-center gap-2 rounded-2xl border border-border-color bg-bg-primary/5 text-text-secondary hover:text-text-primary px-4 py-3.5 text-xs font-semibold uppercase tracking-wider transition-all duration-300"
          >
            {secondaryActionLabel}
          </button>
        )}
      </div>
    </div>
  )
}
