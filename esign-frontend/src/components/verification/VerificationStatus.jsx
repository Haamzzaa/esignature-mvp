import React from 'react'
import { ShieldCheck, CheckCircle2, Clock, XCircle, FileCheck, Lock, Unlock } from 'lucide-react'

export default function VerificationStatus({ authStatus, documentLoaded = true }) {
  if (!authStatus) return null

  const requirements = authStatus.requirements || {}

  const checkItems = [
    {
      key: 'document',
      label: 'Document Payload',
      satisfied: documentLoaded,
      customTag: 'Loaded'
    },
    {
      key: 'terms_acceptance',
      label: 'Terms Accepted',
      required: requirements.terms_acceptance?.required ?? true,
      satisfied: requirements.terms_acceptance?.satisfied ?? false,
    },
    {
      key: 'email_otp',
      label: 'Email Verification',
      required: requirements.email_otp?.required ?? true,
      satisfied: requirements.email_otp?.satisfied ?? false,
    },
    {
      key: 'national_id',
      label: 'National ID Verification',
      required: requirements.national_id?.required ?? true,
      satisfied: requirements.national_id?.satisfied ?? false,
    },
    {
      key: 'face_biometric',
      label: 'Verify Your Identity',
      required: requirements.face_biometric?.required ?? true,
      satisfied: requirements.face_biometric?.satisfied ?? false,
    },
    {
      key: 'representative_match',
      label: 'Representative Authorization',
      required: requirements.representative_match?.required ?? true,
      satisfied: requirements.representative_match?.satisfied ?? false,
    },
  ]

  return (
    <div className="glass-panel rounded-3xl p-6 space-y-4 shadow-lg border border-border-color">
      <div className="flex items-center justify-between border-b border-border-color pb-3">
        <div className="flex items-center gap-2 text-text-primary">
          <ShieldCheck className="h-5 w-5 text-accent animate-pulse" />
          <h3 className="text-xs font-semibold uppercase tracking-wider">
            Verification Session Status
          </h3>
        </div>
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider ${
          authStatus.authorized
            ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400'
            : 'bg-cyan-500/10 border border-cyan-500/30 text-accent'
        }`}>
          {authStatus.authorized ? 'Ready to Sign' : 'Active Session'}
        </span>
      </div>

      <div className="space-y-2.5">
        {checkItems.map(item => {
          const isSatisfied = item.key === 'document' ? item.satisfied : (!item.required || item.satisfied)

          return (
            <div key={item.key} className="flex items-center justify-between text-xs">
              <span className="text-text-secondary font-medium">{item.label}</span>
              {isSatisfied ? (
                <span className="inline-flex items-center gap-1 font-semibold text-emerald-400">
                  <CheckCircle2 className="h-3.5 w-3.5" /> {item.customTag || 'Verified'}
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 font-medium text-text-secondary/60">
                  <Clock className="h-3.5 w-3.5 text-amber-400/80" /> Pending
                </span>
              )}
            </div>
          )
        })}
      </div>

      {/* Signing Status Banner */}
      <div className={`mt-4 p-3.5 rounded-2xl border text-center transition-colors duration-300 ${
        authStatus.authorized
          ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400 shadow-[0_0_20px_rgba(16,185,129,0.1)]'
          : 'bg-red-500/10 border-red-500/20 text-red-400'
      }`}>
        <div className="text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2">
          {authStatus.authorized ? (
            <>
              <Unlock className="h-4 w-4 text-emerald-400" />
              Signing Status: READY
            </>
          ) : (
            <>
              <Lock className="h-4 w-4 text-red-400" />
              Signing Status: LOCKED
            </>
          )}
        </div>
        {!authStatus.authorized && authStatus.reason && (
          <div className="text-[10px] mt-1 text-red-300 font-medium">
            {authStatus.reason}
          </div>
        )}
      </div>
    </div>
  )
}
