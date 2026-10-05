import React from 'react'

export default function VerificationCard({
  title,
  subtitle,
  icon: Icon,
  badgeText,
  estimatedTime,
  stepProgress,
  children,
  className = ''
}) {
  return (
    <section
      role="region"
      aria-label={title || 'Verification Step'}
      className={`glass-panel rounded-3xl p-6 sm:p-8 sticky top-8 space-y-6 relative overflow-hidden transition-all duration-300 ${className}`}
    >
      {/* Background Decorative Ambient Glow */}
      <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/10 via-transparent to-transparent opacity-30 pointer-events-none" />

      {/* Standardized Verification Header */}
      {(title || Icon || badgeText || estimatedTime || stepProgress) && (
        <div className="border-b border-border-color pb-4 space-y-2">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              {Icon && (
                <div className="h-9 w-9 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-accent shrink-0">
                  <Icon className="h-5 w-5 animate-pulse" />
                </div>
              )}
              <div>
                {title && (
                  <h3 className="text-lg font-light text-text-primary tracking-tight flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                    {title}
                  </h3>
                )}
                {subtitle && <p className="text-xs text-text-secondary mt-0.5">{subtitle}</p>}
              </div>
            </div>

            {/* Badges */}
            <div className="flex flex-col items-end gap-1.5 shrink-0">
              {badgeText && (
                <span className="inline-flex items-center gap-1 rounded-full border border-cyan-500/20 bg-cyan-500/5 px-2.5 py-0.5 text-[10px] font-bold uppercase text-accent tracking-wider">
                  {badgeText}
                </span>
              )}
              {stepProgress && (
                <span className="text-[10px] font-mono text-text-secondary/70">
                  {stepProgress}
                </span>
              )}
            </div>
          </div>

          {/* Sub-header Metadata (Estimated Time) */}
          {estimatedTime && (
            <div className="flex items-center justify-between pt-1 text-[11px] text-text-secondary/80 font-medium border-t border-border-color/30">
              <span className="flex items-center gap-1 text-text-secondary/70">
                ⏱ Est. Time: <strong className="text-text-primary font-normal">{estimatedTime}</strong>
              </span>
              <span className="text-[10px] text-accent/80 font-mono uppercase tracking-wider">
                Automated Verification
              </span>
            </div>
          )}
        </div>
      )}

      {/* Card Content Body */}
      <div className="relative z-10 space-y-4">
        {children}
      </div>
    </section>
  )
}
