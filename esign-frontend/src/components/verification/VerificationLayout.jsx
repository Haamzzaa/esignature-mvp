import React from 'react'

export default function VerificationLayout({ leftColumn, rightColumn }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_420px] gap-8 items-start">
      {/* Left Column: Session Header, Document Viewport, Verification Summaries */}
      <div className="space-y-6">
        {leftColumn}
      </div>

      {/* Right Column: Stepper, Active Step Card, Signature Controls */}
      <div className="space-y-6 lg:sticky lg:top-8">
        {rightColumn}
      </div>
    </div>
  )
}
