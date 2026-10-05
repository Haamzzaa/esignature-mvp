import React, { useEffect, useState } from 'react'
import { RefreshCw, CheckCircle2, Clock, ShieldCheck, Info } from 'lucide-react'

const STAGE_TIMELINES = {
  national_id: [
    { id: 'upload', label: 'Upload Complete' },
    { id: 'image', label: 'Image Loaded & Decoded' },
    { id: 'reading', label: 'Reading Document OCR' },
    { id: 'extracting', label: 'Extracting Identity Fields' },
    { id: 'validating', label: 'Validating Expiry & Bounds' }
  ],
  face: [
    { id: 'capture', label: 'Photo Capture Complete' },
    { id: 'landmarks', label: 'Facial Landmarks Detected' },
    { id: 'quality', label: 'Checking Image Quality & Lighting' },
    { id: 'embedding', label: 'Generating Biometric Embedding' },
    { id: 'matching', label: 'Comparing Feature Embeddings' }
  ],
  authorization: [
    { id: 'representatives', label: 'Loading Contract Representatives' },
    { id: 'normalizing', label: 'Normalizing Name Transliterations' },
    { id: 'matching_identity', label: 'Matching Verified Identity' },
    { id: 'evaluating', label: 'Evaluating Authorization Policy' }
  ],
  terms: [
    { id: 'reading_terms', label: 'Reading Terms & Conditions' },
    { id: 'registering', label: 'Registering User Consent' },
    { id: 'sealing', label: 'Sealing Acceptance Record' }
  ],
  email: [
    { id: 'dispatching', label: 'Dispatching Verification Token' },
    { id: 'verifying_code', label: 'Verifying OTP Checksum' },
    { id: 'securing_session', label: 'Securing Session Token' }
  ]
}

export default function VerificationLoading({ stageId = 'national_id', customMessage = null }) {
  const [secondsElapsed, setSecondsElapsed] = useState(0)

  // Live mm:ss elapsed timer
  useEffect(() => {
    setSecondsElapsed(0)
    const interval = setInterval(() => {
      setSecondsElapsed(prev => prev + 1)
    }, 1000)
    return () => clearInterval(interval)
  }, [stageId])

  const mins = Math.floor(secondsElapsed / 60).toString().padStart(2, '0')
  const secs = (secondsElapsed % 60).toString().padStart(2, '0')
  const formattedTime = `${mins}:${secs}`

  const timelineSteps = STAGE_TIMELINES[stageId] || STAGE_TIMELINES.national_id

  const activeStepIdx = Math.min(
    Math.floor((secondsElapsed / 3) % timelineSteps.length),
    timelineSteps.length - 1
  )

  return (
    <div
      role="status"
      aria-live="polite"
      className="py-6 px-4 sm:px-6 text-center flex flex-col items-center justify-center space-y-6 font-sans"
    >
      {/* Pulse Glow Container */}
      <div className="relative flex items-center justify-center">
        <div className="absolute inset-0 rounded-full bg-cyan-500/20 blur-xl animate-pulse w-20 h-20" />
        <div className="relative h-16 w-16 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-accent shadow-[0_0_30px_rgba(34,211,238,0.25)]">
          <RefreshCw className="h-8 w-8 animate-spin" />
        </div>
      </div>

      {/* Dual Timing Metrics: Typical Processing Guidance & Live Elapsed Timer */}
      <div className="space-y-2 w-full max-w-sm">
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="p-2.5 rounded-xl border border-border-color bg-bg-primary/5 text-left">
            <span className="text-[10px] text-text-secondary uppercase tracking-wider block">Typical Processing</span>
            <span className="font-medium text-text-primary text-[11px] flex items-center gap-1 mt-0.5 leading-snug">
              <Info className="h-3 w-3 text-accent shrink-0" /> Processing stage
            </span>
          </div>

          <div className="p-2.5 rounded-xl border border-cyan-500/30 bg-cyan-500/10 text-left">
            <span className="text-[10px] text-cyan-400 uppercase tracking-wider block">Elapsed Time</span>
            <span className="font-mono font-bold text-white text-sm flex items-center gap-1 mt-0.5">
              <Clock className="h-3.5 w-3.5 text-accent" /> {formattedTime}
            </span>
          </div>
        </div>

        <p className="text-[10px] text-text-secondary/70 italic leading-relaxed">
          Processing time varies depending on document quality, image size, and network conditions.
        </p>

        {customMessage && (
          <p className="text-[11px] text-text-secondary/90 pt-1">
            {customMessage}
          </p>
        )}
      </div>

      {/* State-Driven Verification Timeline */}
      <div className="w-full max-w-sm rounded-2xl border border-border-color bg-bg-primary/5 p-4 space-y-2.5 text-left text-xs">
        <div className="flex items-center justify-between border-b border-border-color/50 pb-2 mb-3">
          <span className="text-[10px] font-bold uppercase tracking-wider text-text-secondary flex items-center gap-1.5">
            <ShieldCheck className="h-3.5 w-3.5 text-accent" /> Verification Pipeline
          </span>
          <span className="text-[10px] font-mono text-cyan-400">Active</span>
        </div>

        {timelineSteps.map((step, idx) => {
          const isDone = idx < activeStepIdx
          const isCurrent = idx === activeStepIdx
          const isPending = idx > activeStepIdx

          return (
            <div key={step.id} className="flex items-center justify-between gap-3 py-0.5">
              <div className="flex items-center gap-2.5">
                {isDone ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                ) : isCurrent ? (
                  <div className="relative h-4 w-4 flex items-center justify-center shrink-0">
                    <div className="absolute inset-0 rounded-full bg-cyan-400 animate-ping opacity-40" />
                    <div className="h-2 w-2 rounded-full bg-cyan-400" />
                  </div>
                ) : (
                  <div className="h-4 w-4 rounded-full border border-border-color bg-card-bg shrink-0" />
                )}

                <span className={`text-xs font-medium ${
                  isDone
                    ? 'text-emerald-400 line-through decoration-emerald-500/30'
                    : isCurrent
                    ? 'text-text-primary font-semibold'
                    : 'text-text-secondary/50'
                }`}>
                  {step.label}
                </span>
              </div>

              <span className="text-[10px] font-mono shrink-0">
                {isDone ? (
                  <span className="text-emerald-400 font-bold">✓ Complete</span>
                ) : isCurrent ? (
                  <span className="text-accent font-semibold animate-pulse">In Progress...</span>
                ) : (
                  <span className="text-text-secondary/40">Pending</span>
                )}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
