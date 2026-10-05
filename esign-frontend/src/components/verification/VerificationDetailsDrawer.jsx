import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, Shield, Clock, FileCheck, CheckCircle2 } from 'lucide-react'

export default function VerificationDetailsDrawer({
  sessionTimestamp,
  idDuration = '3.2s',
  faceDuration = '1.8s',
  authDuration = '0.5s',
  documentStatus = 'Loaded',
  verificationStatus = 'In Progress'
}) {
  const [isOpen, setIsOpen] = useState(false)
  const timestamp = sessionTimestamp || new Date().toLocaleString()

  return (
    <div className="w-full glass-panel rounded-2xl overflow-hidden border border-border-color transition-all duration-300">
      <button
        type="button"
        onClick={() => setIsOpen(prev => !prev)}
        className="w-full flex items-center justify-between px-4 py-3 bg-card-bg hover:bg-bg-primary/20 text-xs font-semibold text-text-secondary hover:text-text-primary transition-colors outline-none focus:ring-2 focus:ring-cyan-500/30"
        aria-expanded={isOpen}
      >
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-accent" />
          <span>Verification Details</span>
        </div>
        <div className="flex items-center gap-2">
          <ChevronDown className={`h-4 w-4 transition-transform duration-300 ${isOpen ? 'rotate-180 text-accent' : ''}`} />
        </div>
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
            className="overflow-hidden border-t border-border-color/50 bg-bg-primary/5 p-4 space-y-3 text-xs"
          >
            <div className="grid grid-cols-2 gap-3 text-left">
              <div className="p-2.5 rounded-xl border border-border-color bg-card-bg">
                <span className="text-[10px] text-text-secondary block">Verification Timestamp</span>
                <span className="font-mono font-semibold text-text-primary text-[11px] block truncate" title={timestamp}>
                  {timestamp}
                </span>
              </div>

              <div className="p-2.5 rounded-xl border border-border-color bg-card-bg">
                <span className="text-[10px] text-text-secondary block">Document Status</span>
                <span className="font-semibold text-emerald-400 text-[11px] block capitalize flex items-center gap-1">
                  <FileCheck className="h-3 w-3" /> {documentStatus}
                </span>
              </div>

              <div className="p-2.5 rounded-xl border border-border-color bg-card-bg">
                <span className="text-[10px] text-text-secondary block">Identity Verification Duration</span>
                <span className="font-mono font-semibold text-text-primary text-[11px] block flex items-center gap-1">
                  <Clock className="h-3 w-3 text-accent" /> {idDuration}
                </span>
              </div>

              <div className="p-2.5 rounded-xl border border-border-color bg-card-bg">
                <span className="text-[10px] text-text-secondary block">Face Verification Duration</span>
                <span className="font-mono font-semibold text-text-primary text-[11px] block flex items-center gap-1">
                  <Clock className="h-3 w-3 text-accent" /> {faceDuration}
                </span>
              </div>

              <div className="p-2.5 rounded-xl border border-border-color bg-card-bg">
                <span className="text-[10px] text-text-secondary block">Authorization Duration</span>
                <span className="font-mono font-semibold text-text-primary text-[11px] block flex items-center gap-1">
                  <Clock className="h-3 w-3 text-accent" /> {authDuration}
                </span>
              </div>

              <div className="p-2.5 rounded-xl border border-border-color bg-card-bg">
                <span className="text-[10px] text-text-secondary block">Verification Status</span>
                <span className="font-semibold text-accent text-[11px] block flex items-center gap-1">
                  <CheckCircle2 className="h-3 w-3" /> {verificationStatus}
                </span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
