import React from 'react'
import { motion } from 'framer-motion'
import { CheckCircle2, ChevronRight, ShieldCheck } from 'lucide-react'

export default function VerificationSuccess({
  title,
  subtitle,
  items = [],
  onContinue,
  autoContinueText = 'Continuing automatically...'
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: 'easeInOut' }}
      className="glass-panel rounded-3xl p-6 sm:p-8 text-center space-y-6 relative overflow-hidden border-emerald-500/30"
    >
      <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/10 via-transparent to-transparent opacity-60 pointer-events-none" />

      {/* Verified Icon */}
      <div className="relative flex justify-center">
        <div className="absolute inset-0 rounded-full bg-emerald-500/20 blur-xl animate-pulse w-16 h-16 mx-auto" />
        <div className="relative flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 shadow-[0_0_30px_rgba(16,185,129,0.2)]">
          <CheckCircle2 className="h-9 w-9" />
        </div>
      </div>

      <div>
        <h3 className="text-xl font-light text-emerald-400 tracking-tight neon-text-glow">
          {title || 'Verification Successful'}
        </h3>
        {subtitle && (
          <p className="text-xs text-text-secondary mt-1 max-w-sm mx-auto leading-relaxed">
            {subtitle}
          </p>
        )}
      </div>

      {/* Extracted Details Grid */}
      {items.length > 0 && (
        <div className="w-full text-left p-4 rounded-2xl border border-emerald-500/20 bg-emerald-500/5 space-y-2.5 text-xs">
          <div className="flex items-center justify-between border-b border-emerald-500/20 pb-2 mb-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5" /> Verified Data Snapshot
            </span>
            <span className="text-[10px] font-mono text-emerald-400 font-bold">STATUS: OK</span>
          </div>

          {items.map((item, idx) => (
            <div key={idx} className="flex items-center justify-between gap-4 py-0.5">
              <span className="text-text-secondary shrink-0">{item.label}</span>
              <span
                className={`font-semibold truncate max-w-[210px] ${item.isMono ? 'font-mono text-text-primary' : 'text-text-primary'}`}
                dir={item.dir || 'ltr'}
              >
                {item.value || '—'}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Footer Auto-continue notice */}
      <div className="pt-2 flex flex-col items-center gap-3">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-[10px] font-bold uppercase tracking-wider text-emerald-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping" />
          {autoContinueText}
        </div>

        {onContinue && (
          <button
            type="button"
            onClick={onContinue}
            className="text-xs text-text-secondary hover:text-emerald-400 underline underline-offset-4 transition-colors"
          >
            Click here to continue immediately <ChevronRight className="inline h-3 w-3" />
          </button>
        )}
      </div>
    </motion.div>
  )
}
