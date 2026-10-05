import React from 'react'
import { Lock, CheckCircle2, ShieldCheck, ArrowRight, UserCheck, CreditCard, Mail, Camera } from 'lucide-react'

export default function LockedSigningNotice({
  isAuthorized,
  remainingSteps = [],
  reason,
  acknowledgedUnlock = false,
  onProceedToSign
}) {
  // ── Authorized State: Intentional Transition Card ────────────────────────
  if (isAuthorized) {
    if (!acknowledgedUnlock) {
      return (
        <div className="glass-panel rounded-3xl p-6 sm:p-8 text-center space-y-6 relative overflow-hidden border-emerald-500/40">
          <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/10 via-transparent to-transparent opacity-60 pointer-events-none" />

          {/* Icon */}
          <div className="relative flex justify-center">
            <div className="absolute inset-0 rounded-full bg-emerald-500/20 blur-xl animate-pulse w-16 h-16 mx-auto" />
            <div className="relative flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 shadow-[0_0_30px_rgba(16,185,129,0.2)]">
              <CheckCircle2 className="h-9 w-9" />
            </div>
          </div>

          <div>
            <h3 className="text-xl font-light text-emerald-400 tracking-tight neon-text-glow">
              Verification Complete
            </h3>
            <p className="text-xs text-text-secondary mt-1.5 max-w-sm mx-auto leading-relaxed">
              Your identity has been successfully verified and representative authorization has been confirmed. Electronic signing is now available.
            </p>
          </div>

          {/* Pre-Signing Verification Report */}
          <div className="w-full text-left p-4 rounded-2xl border border-emerald-500/20 bg-emerald-500/5 space-y-2.5 text-xs">
            <div className="flex items-center justify-between border-b border-emerald-500/20 pb-2 mb-1">
              <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                <ShieldCheck className="h-3.5 w-3.5" /> Enterprise Verification Report
              </span>
              <span className="text-[10px] font-mono text-emerald-400 font-bold">STATUS: AUTHORIZED</span>
            </div>

            <div className="space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-text-secondary flex items-center gap-1.5">
                  <Mail className="h-3.5 w-3.5 text-emerald-400" /> Email Verification
                </span>
                <span className="font-semibold text-emerald-400">✓ Verified</span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-text-secondary flex items-center gap-1.5">
                  <CreditCard className="h-3.5 w-3.5 text-emerald-400" /> National ID Verification
                </span>
                <span className="font-semibold text-emerald-400">✓ Verified</span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-text-secondary flex items-center gap-1.5">
                  <Camera className="h-3.5 w-3.5 text-emerald-400" /> Face Verification
                </span>
                <span className="font-semibold text-emerald-400">✓ Matched</span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-text-secondary flex items-center gap-1.5">
                  <UserCheck className="h-3.5 w-3.5 text-emerald-400" /> Representative Authorization
                </span>
                <span className="font-semibold text-emerald-400">✓ Authorized</span>
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={onProceedToSign}
            className="flex w-full items-center justify-center gap-2 rounded-2xl bg-cyan-500 hover:bg-cyan-400 text-black px-4 py-4 text-sm font-bold uppercase tracking-widest transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.3)] focus:ring-2 focus:ring-cyan-500/30 outline-none"
          >
            Proceed to Electronic Signature <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      )
    }

    // Unlocked Banner when user has acknowledged transition
    return (
      <div className="p-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-center space-y-1 mb-6 shadow-[0_0_20px_rgba(16,185,129,0.1)]">
        <div className="flex items-center justify-center gap-2 font-bold uppercase tracking-wider text-xs">
          <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          Verification Complete — Electronic Signing Enabled
        </div>
        <p className="text-[11px] text-emerald-300/80">
          All identity and authorization requirements are satisfied. Please apply your electronic signature below.
        </p>
      </div>
    )
  }

  // ── Locked State Guidance ──────────────────────────────────────────────────
  const stepLabels = {
    terms_acceptance: 'Terms & Conditions Acceptance',
    terms: 'Terms & Conditions Acceptance',
    email_otp: 'Email Verification',
    national_id: 'National ID Verification',
    face_biometric: 'Verify Your Identity',
    representative_match: 'Representative Authorization'
  }

  return (
    <div className="glass-panel rounded-3xl p-6 sm:p-8 text-center space-y-5 relative overflow-hidden border-red-500/20">
      <div className="absolute inset-0 bg-gradient-to-br from-red-500/10 via-transparent to-transparent opacity-40 pointer-events-none" />

      {/* Lock Icon */}
      <div className="relative flex justify-center">
        <div className="relative flex h-16 w-16 items-center justify-center rounded-full bg-red-500/10 border border-red-500/20 text-red-400 shadow-[0_0_25px_rgba(239,68,68,0.15)]">
          <Lock className="h-8 w-8" />
        </div>
      </div>

      <div>
        <h3 className="text-lg font-light text-red-400 tracking-tight">
          Electronic Signature Controls Locked
        </h3>
        <p className="text-xs text-text-secondary mt-1.5 max-w-sm mx-auto leading-relaxed">
          Cryptographic signing controls remain disabled until all required identity and representative authorization checks complete successfully.
        </p>
      </div>

      {/* Remaining Steps Checklist */}
      <div className="p-4 rounded-2xl border border-border-color bg-bg-primary/5 text-xs text-left space-y-2.5 max-w-sm mx-auto">
        <div className="flex items-center justify-between border-b border-border-color pb-2">
          <span className="text-[10px] font-bold uppercase tracking-wider text-text-secondary flex items-center gap-1.5">
            <ShieldCheck className="h-3.5 w-3.5 text-amber-400" /> Remaining Requirements
          </span>
          <span className="text-[10px] font-mono text-amber-400">Locked</span>
        </div>

        <div className="space-y-1.5 pt-0.5">
          {remainingSteps.length > 0 ? (
            remainingSteps.map((stepKey, idx) => {
              const label = stepLabels[stepKey] || stepKey
              return (
                <div key={idx} className="flex items-center justify-between text-text-secondary">
                  <div className="flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-amber-400 shrink-0 animate-pulse" />
                    <span className="text-xs font-medium text-text-primary">{label}</span>
                  </div>
                  <span className="text-[10px] text-amber-400/80 font-mono">Pending</span>
                </div>
              )
            })
          ) : (
            <div className="text-xs text-text-secondary italic">
              Completing final representative authorization check...
            </div>
          )}
        </div>
      </div>

      {/* Next Step Guidance */}
      <div className="p-3 rounded-xl border border-cyan-500/20 bg-cyan-500/5 text-xs text-cyan-300 max-w-sm mx-auto flex items-center justify-center gap-2">
        <ArrowRight className="h-4 w-4 shrink-0 text-accent" />
        <span>Authorization will automatically evaluate after fulfilling pending steps.</span>
      </div>

      {reason && (
        <div className="p-3 rounded-xl border border-red-500/20 bg-red-500/5 text-xs text-red-300 font-medium max-w-sm mx-auto">
          Reason: {reason}
        </div>
      )}
    </div>
  )
}
