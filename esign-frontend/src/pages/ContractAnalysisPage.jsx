import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Sparkles, FileText, UploadCloud, ArrowLeft, RefreshCw, AlertCircle, CheckCircle } from 'lucide-react'
import { analyzeContract } from '../services/api.js'
import { useLocale } from '../context/LocaleContext'

export default function ContractAnalysisPage() {
  const { t } = useLocale()
  const [file, setFile] = useState(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0])
      setError('')
      setResult(null)
    }
  }

  const handleAnalyze = async (e) => {
    e.preventDefault()
    if (!file) {
      setError(t('contract_analysis.select_pdf_error'))
      return
    }
    setIsAnalyzing(true)
    setError('')
    try {
      const data = await analyzeContract(file)
      setResult(data)
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
        err?.message ||
        t('contract_analysis.analyze_error')
      )
    } finally {
      setIsAnalyzing(false)
    }
  }

  const isRepresentativeFound = result && result.candidates && result.candidates.length > 0;

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:py-16 relative z-10 space-y-10">
      
      {/* Back to Workspace Header */}
      <div className="flex items-center gap-4">
        <Link
          to="/"
          className="inline-flex items-center gap-2 rounded-xl glass-panel hover:bg-cyan-500/10 px-4 h-9 text-xs font-semibold text-text-primary hover:text-cyan-400 transition-all cursor-pointer"
        >
          <ArrowLeft className="h-3.5 w-3.5 rtl:rotate-180" />
          {t('nav.back_to_dashboard')}
        </Link>
      </div>

      {/* Main Title Banner */}
      <div className="space-y-2 border-b border-border-color pb-8">
        <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-cyan-400 backdrop-blur-md">
          <Sparkles className="h-3.5 w-3.5" />
          {t('contract_analysis.badge')}
        </div>
        <h1 className="text-4xl font-bold tracking-tight text-text-primary sm:text-[50px] sm:leading-none">
          {t('contract_analysis.title')}
        </h1>
        <p className="text-sm font-medium text-text-secondary sm:text-base">
          {t('contract_analysis.subtitle')}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        
        {/* Left Card: File Upload */}
        <div className="space-y-6">
          <div className="glass-panel rounded-3xl p-6 space-y-6">
            <h2 className="text-lg font-semibold text-text-primary flex items-center gap-2">
              <FileText className="h-5 w-5 text-cyan-400" />
              {t('contract_analysis.upload_title')}
            </h2>

            <form onSubmit={handleAnalyze} className="space-y-6">
              <div className="border-2 border-dashed border-border-color hover:border-cyan-500/30 rounded-2xl p-8 text-center bg-card-bg cursor-pointer transition-all relative group">
                <input
                  type="file"
                  accept=".pdf"
                  onChange={handleFileChange}
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                />
                <div className="flex flex-col items-center justify-center space-y-3">
                  <div className="rounded-2xl p-4 bg-cyan-500/10 text-cyan-400 group-hover:bg-cyan-500 group-hover:text-black transition-all">
                    <UploadCloud className="h-8 w-8" />
                  </div>
                  {file ? (
                    <div>
                      <p className="text-sm font-bold text-cyan-400" dir="ltr">{file.name}</p>
                      <p className="text-xs text-text-secondary mt-1" dir="ltr">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                    </div>
                  ) : (
                    <div>
                      <p className="text-sm font-semibold text-text-primary">{t('contract_analysis.drop_hint')}</p>
                      <p className="text-xs text-text-secondary mt-1">{t('contract_analysis.size_hint')}</p>
                    </div>
                  )}
                </div>
              </div>

              {error && (
                <div className="flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-xs text-red-200">
                  <AlertCircle className="h-5 w-5 text-red-400 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <button
                type="submit"
                disabled={isAnalyzing || !file}
                className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 disabled:cursor-not-allowed text-black h-12 text-sm font-bold transition-all shadow-[0_0_20px_rgba(34,211,238,0.2)] cursor-pointer"
              >
                {isAnalyzing ? (
                  <>
                    <RefreshCw className="h-5 w-5 animate-spin" />
                    {t('contract_analysis.analyzing')}
                  </>
                ) : (
                  <>
                    <Sparkles className="h-5 w-5" />
                    {t('contract_analysis.btn_analyze')}
                  </>
                )}
              </button>
            </form>
          </div>
        </div>

        {/* Right Card: Analysis Results */}
        <div>
          <div className="glass-panel rounded-3xl p-6 min-h-[350px] flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-border-color pb-4 mb-6">
                <h2 className="text-lg font-semibold text-text-primary">
                  {t('contract_analysis.results_title')}
                </h2>
                {result && (
                  <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
                    isRepresentativeFound ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-zinc-500/10 text-zinc-400 border border-zinc-500/20'
                  }`}>
                    {isRepresentativeFound ? (
                      <>
                        <CheckCircle className="h-3.5 w-3.5" />
                        {t('contract_analysis.candidate_found')}
                      </>
                    ) : (
                      t('contract_analysis.no_candidates')
                    )}
                  </span>
                )}
              </div>

              <AnimatePresence mode="wait">
                {result ? (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className="space-y-6"
                  >
                    {result.candidates && result.candidates.length > 0 ? (
                      <div className="space-y-4">
                        {result.candidates.map((cand, idx) => (
                          <div key={cand.id || idx} className="bg-card-bg border border-border-color rounded-2xl p-5 space-y-4">
                            <div className="flex items-center justify-between border-b border-border-color/50 pb-2">
                              <span className="text-[10px] text-cyan-400 font-bold uppercase tracking-widest font-mono">
                                {t('contract_analysis.candidate_prefix')} {result.candidates.length > 1 ? `#${idx + 1}` : ''}
                              </span>
                            </div>
                            
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              {/* Name English */}
                              <div className="space-y-1">
                                <span className="text-[10px] text-text-secondary uppercase tracking-widest font-bold">{t('contract_analysis.name_en')}</span>
                                <p className="text-sm font-bold text-text-primary mt-0.5" dir="ltr">
                                  {cand.name_en || <span className="text-zinc-600 font-normal italic">{t('contract_analysis.not_detected')}</span>}
                                </p>
                              </div>

                              {/* Name Arabic */}
                              <div className="space-y-1 text-right rtl:text-right">
                                <span className="text-[10px] text-text-secondary uppercase tracking-widest font-bold block text-left rtl:text-right">{t('contract_analysis.name_ar')}</span>
                                <p className="text-sm font-bold text-text-primary mt-0.5" dir="rtl">
                                  {cand.name_ar || <span className="text-zinc-600 font-normal italic" dir="ltr">{t('contract_analysis.not_detected')}</span>}
                                </p>
                              </div>

                              {/* Title English */}
                              <div className="space-y-1">
                                <span className="text-[10px] text-text-secondary uppercase tracking-widest font-bold">{t('contract_analysis.title_en')}</span>
                                <p className="text-sm font-semibold text-text-primary mt-0.5" dir="ltr">
                                  {cand.title_en || <span className="text-zinc-600 font-normal italic">{t('contract_analysis.not_detected')}</span>}
                                </p>
                              </div>

                              {/* Title Arabic */}
                              <div className="space-y-1 text-right rtl:text-right">
                                <span className="text-[10px] text-text-secondary uppercase tracking-widest font-bold block text-left rtl:text-right">{t('contract_analysis.title_ar')}</span>
                                <p className="text-sm font-semibold text-text-primary mt-0.5" dir="rtl">
                                  {cand.title_ar || <span className="text-zinc-600 font-normal italic" dir="ltr">{t('contract_analysis.not_detected')}</span>}
                                </p>
                              </div>
                            </div>

                            {cand.authority_clause && (
                              <div className="border-t border-border-color/50 pt-3">
                                <span className="text-[10px] text-text-secondary uppercase tracking-widest font-bold block mb-1">{t('contract_analysis.capacity_clause')}</span>
                                <p className="text-xs font-medium text-text-primary bg-black/20 p-2.5 rounded-lg border border-border-color/30 leading-relaxed">
                                  "{cand.authority_clause}"
                                </p>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center py-10 text-center text-zinc-600">
                        <AlertCircle className="h-8 w-8 mb-2 text-zinc-500" />
                        <p className="text-sm font-medium">{t('contract_analysis.no_candidates_desc')}</p>
                      </div>
                    )}
                  </motion.div>
                ) : (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="flex flex-col items-center justify-center py-20 text-center text-zinc-600"
                  >
                    <Sparkles className="h-12 w-12 mb-3 text-zinc-800" />
                    <p className="text-sm font-medium">{t('contract_analysis.awaiting_analysis')}</p>
                    <p className="text-xs text-zinc-600 mt-1 max-w-[240px]">{t('contract_analysis.awaiting_analysis_desc')}</p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>

      </div>

    </div>
  )
}
