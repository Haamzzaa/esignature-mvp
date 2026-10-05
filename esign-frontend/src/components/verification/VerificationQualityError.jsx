import React from 'react'
import { AlertTriangle, RefreshCw, HelpCircle, ShieldAlert } from 'lucide-react'

export default function VerificationQualityError({
  qualityReport,
  onRetry,
  onSecondaryAction,
  secondaryActionLabel
}) {
  const { overall_quality_score, issues = [], recommendations = [] } = qualityReport || {}
  const scorePercent = Math.round((overall_quality_score || 0) * 100)

  return (
    <div className="glass-panel rounded-3xl p-6 sm:p-8 space-y-5 border-amber-500/30 relative overflow-hidden font-sans">
      {/* Background Ambient Decorative Glow */}
      <div className="absolute inset-0 bg-gradient-to-br from-amber-500/10 via-transparent to-transparent opacity-50 pointer-events-none" />

      {/* Header */}
      <div className="flex items-start gap-3.5">
        <div className="h-10 w-10 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 shrink-0 shadow-[0_0_15px_rgba(245,158,11,0.15)]">
          <ShieldAlert className="h-5 w-5" />
        </div>
        <div className="space-y-1 text-left flex-1">
          <h3 className="text-sm font-semibold text-amber-400 tracking-tight">
            Image Quality Verification Failed
          </h3>
          <p className="text-xs text-text-secondary leading-relaxed">
            The uploaded image does not meet the quality standards required for automated processing.
          </p>
        </div>
      </div>

      {/* Overall Quality Progress Bar */}
      <div className="space-y-1.5 text-left border-t border-b border-border-color/30 py-3.5">
        <div className="flex justify-between text-xs font-semibold">
          <span className="text-text-secondary">Overall Quality</span>
          <span className="text-amber-400">{scorePercent}%</span>
        </div>
        <div className="w-full bg-bg-primary/20 rounded-full h-2 overflow-hidden border border-border-color/20">
          <div
            className="bg-gradient-to-r from-red-500 to-amber-500 h-full rounded-full transition-all duration-500"
            style={{ width: `${scorePercent}%` }}
          />
        </div>
      </div>

      {/* Problems Detected List */}
      {issues.length > 0 && (
        <div className="p-4 rounded-2xl border border-red-500/20 bg-red-500/5 text-xs text-text-secondary space-y-2 text-left">
          <div className="flex items-center gap-1.5 font-semibold text-red-300">
            <AlertTriangle className="h-3.5 w-3.5 text-red-400" /> Problems Detected:
          </div>
          <ul className="list-disc list-inside space-y-1 text-text-secondary/90 pl-1 text-[11px]">
            {issues.map((issue, idx) => (
              <li key={idx}>{issue}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Actionable Recommendations List */}
      {recommendations.length > 0 && (
        <div className="p-4 rounded-2xl border border-cyan-500/20 bg-cyan-500/5 text-xs text-text-secondary space-y-2 text-left">
          <div className="flex items-center gap-1.5 font-semibold text-cyan-300">
            <HelpCircle className="h-3.5 w-3.5 text-cyan-400" /> Recommendations:
          </div>
          <ul className="list-disc list-inside space-y-1 text-text-secondary/90 pl-1 text-[11px]">
            {recommendations.map((rec, idx) => (
              <li key={idx}>{rec}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Action Buttons */}
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
