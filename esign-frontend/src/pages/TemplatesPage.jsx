import { useEffect, useState } from 'react'
import { getTemplates, deleteTemplate, updateTemplate, createTemplate } from '../services/api.js'
import UserNav from '../components/UserNav.jsx'
import { useLocale } from '../context/LocaleContext'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  Layers, 
  Plus, 
  Search, 
  Trash2, 
  Edit3, 
  Play, 
  RefreshCw, 
  AlertCircle, 
  FolderMinus, 
  Bookmark, 
  Eye, 
  EyeOff, 
  ChevronRight,
  Sparkles,
  ArrowLeft,
  X,
  Settings,
  Bell,
  Share2,
  Printer,
  UserPlus,
  ChevronDown,
  User,
  Mail,
  Check
} from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

const CATEGORIES = ['All', 'General', 'Legal', 'HR', 'Finance', 'Operations']

export default function TemplatesPage() {
  const { t } = useLocale()
  const navigate = useNavigate()
  const [templates, setTemplates] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  
  // Search & Filter state
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('All')
  const [selectedTab, setSelectedTab] = useState('all') // all, private, public

  // Edit & Create Modal State
  const [editingTemplate, setEditingTemplate] = useState(null)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [editCategory, setEditCategory] = useState('General')
  const [editVisibility, setEditVisibility] = useState('private')
  const [isUpdating, setIsUpdating] = useState(false)
  const [updateError, setUpdateError] = useState('')

  // Modal Workflow & Settings tab states
  const [modalActiveTab, setModalActiveTab] = useState('details') // details, workflow, settings
  const [modalSteps, setModalSteps] = useState([{ step: 1, role: 'signer' }])
  const [modalSendReminders, setModalSendReminders] = useState(false)
  const [modalSendFinalEmail, setModalSendFinalEmail] = useState(true)
  const [modalAllowPrinting, setModalAllowPrinting] = useState(true)
  const [modalAdditionalRecipients, setModalAdditionalRecipients] = useState([])
  const [modalNewCCEmail, setModalNewCCEmail] = useState('')
  const [modalCCError, setModalCCError] = useState('')

  async function loadTemplates() {
    setIsLoading(true)
    setError('')
    try {
      const res = await getTemplates()
      setTemplates(res)
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
        err?.message ||
        t('templates.syncing')
      )
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadTemplates()
  }, [])

  const handleDelete = async (id, e) => {
    e.stopPropagation()
    if (!window.confirm(t('templates.delete_confirm'))) return
    try {
      await deleteTemplate(id)
      setTemplates(prev => prev.filter(t => t.id !== id))
    } catch (err) {
      alert(err?.response?.data?.detail || t('errors.network_error'))
    }
  }

  const handleCreateClick = () => {
    setEditingTemplate({
      id: 'new',
      name: '',
      description: '',
      category: 'General',
      visibility: 'private',
      workflow_definition: [{ step: 1, role: 'signer' }],
      request_settings: {
        send_reminders: false,
        send_final_email: true,
        allow_printing: true,
        additional_recipients: []
      }
    })
    setEditName('')
    setEditDesc('')
    setEditCategory('General')
    setEditVisibility('private')
    setModalSteps([{ step: 1, role: 'signer' }])
    setModalSendReminders(false)
    setModalSendFinalEmail(true)
    setModalAllowPrinting(true)
    setModalAdditionalRecipients([])
    setModalNewCCEmail('')
    setModalCCError('')
    setModalActiveTab('details')
    setUpdateError('')
  }

  const addModalStep = () => {
    const nextStep = modalSteps.length > 0 ? Math.max(...modalSteps.map(s => s.step)) + 1 : 1
    setModalSteps(prev => [...prev, { step: nextStep, role: 'signer' }])
  }

  const removeModalStep = (index) => {
    setModalSteps(prev => {
      const filtered = prev.filter((_, idx) => idx !== index)
      const sorted = [...filtered].sort((a, b) => a.step - b.step)
      let currentStep = 0
      let lastOriginalStep = -1
      return sorted.map(item => {
        if (item.step !== lastOriginalStep) {
          currentStep++
          lastOriginalStep = item.step
        }
        return {
          ...item,
          step: currentStep
        }
      })
    })
  }

  const updateModalStep = (index, field, value) => {
    setModalSteps(prev => prev.map((item, idx) => {
      if (idx === index) {
        return {
          ...item,
          [field]: value
        }
      }
      return item
    }))
  }

  const addModalCC = () => {
    setModalCCError('')
    const email = modalNewCCEmail.trim()
    if (!email) return

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(email)) {
      setModalCCError(t('errors.invalid_email'))
      return
    }

    if (modalAdditionalRecipients.includes(email)) {
      setModalCCError(t('errors.required_fields'))
      return
    }

    setModalAdditionalRecipients(prev => [...prev, email])
    setModalNewCCEmail('')
  }

  const removeModalCC = (email) => {
    setModalAdditionalRecipients(prev => prev.filter(e => e !== email))
  }

  const handleEditClick = (tpl, e) => {
    e.stopPropagation()
    setEditingTemplate(tpl)
    setEditName(tpl.name)
    setEditDesc(tpl.description || '')
    setEditCategory(tpl.category || 'General')
    setEditVisibility(tpl.visibility || 'private')
    setModalSteps(tpl.workflow_definition || [{ step: 1, role: 'signer' }])
    const settings = tpl.request_settings || {}
    setModalSendReminders(settings.send_reminders ?? false)
    setModalSendFinalEmail(settings.send_final_email ?? true)
    setModalAllowPrinting(settings.allow_printing ?? true)
    setModalAdditionalRecipients(settings.additional_recipients || [])
    setModalNewCCEmail('')
    setModalCCError('')
    setModalActiveTab('details')
    setUpdateError('')
  }

  const handleUpdate = async (e) => {
    e.preventDefault()
    if (!editName.trim()) return setUpdateError(t('errors.required_fields'))
    
    // Validate steps: must have at least one signer
    if (modalSteps.length === 0) {
      return setUpdateError(t('templates.no_steps_defined'))
    }
    const hasSigner = modalSteps.some(s => s.role === 'signer')
    if (!hasSigner) {
      return setUpdateError(t('templates.no_steps_defined'))
    }

    setIsUpdating(true)
    setUpdateError('')
    try {
      const payload = {
        name: editName.trim(),
        description: editDesc.trim(),
        category: editCategory,
        visibility: editVisibility,
        workflow_definition: modalSteps,
        request_settings: {
          send_reminders: modalSendReminders,
          send_final_email: modalSendFinalEmail,
          allow_printing: modalAllowPrinting,
          additional_recipients: modalAdditionalRecipients
        }
      }

      if (editingTemplate.id === 'new') {
        const created = await createTemplate(payload)
        setTemplates(prev => [created, ...prev])
      } else {
        const updated = await updateTemplate(editingTemplate.id, payload)
        setTemplates(prev => prev.map(t => t.id === editingTemplate.id ? updated : t))
      }
      setEditingTemplate(null)
    } catch (err) {
      setUpdateError(err?.response?.data?.detail || t('errors.network_error'))
    } finally {
      setIsUpdating(false)
    }
  }

  // Filter templates
  const filteredTemplates = templates.filter(tpl => {
    const matchesSearch = 
      tpl.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (tpl.description && tpl.description.toLowerCase().includes(searchTerm.toLowerCase()))
    
    const matchesCategory = 
      selectedCategory === 'All' || 
      tpl.category?.toLowerCase() === selectedCategory.toLowerCase()

    const matchesTab = 
      selectedTab === 'all' ||
      tpl.visibility === selectedTab

    return matchesSearch && matchesCategory && matchesTab
  })

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:py-16 relative z-10 space-y-8 font-sans">
      
      {/* Return link */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-400 hover:text-cyan-400 transition-colors"
        >
          <ArrowLeft className="h-4 w-4 rtl:rotate-180" />
          {t('nav.back_to_dashboard')}
        </Link>
      </motion.div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6 border-b border-white/5 pb-6">
        <div className="space-y-2">
          <h1 className="text-3xl font-light tracking-tight text-white sm:text-5xl neon-text-glow">
            {t('templates.title')}
          </h1>
          <p className="text-sm font-medium text-zinc-400">
            {t('templates.subtitle')}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
          <UserNav />
          <button
            type="button"
            onClick={handleCreateClick}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black px-6 py-3.5 text-xs font-bold transition-all duration-300 shadow-[0_0_20px_rgba(34,211,238,0.2)] hover:shadow-[0_0_30px_rgba(34,211,238,0.4)] uppercase tracking-wider cursor-pointer"
          >
            <Plus className="h-4 w-4 stroke-[3]" />
            {t('templates.btn_create')}
          </button>
        </div>
      </div>

      <AnimatePresence mode="wait">
        {isLoading ? (
          <motion.div 
            key="loading"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center py-40 text-cyan-500"
          >
            <RefreshCw className="h-10 w-10 animate-spin" />
            <span className="mt-4 text-xs font-semibold tracking-widest uppercase animate-pulse">{t('templates.syncing')}</span>
          </motion.div>
        ) : error ? (
          <motion.div
            key="error"
            className="flex items-center gap-4 rounded-2xl border border-red-500/30 bg-red-500/10 px-6 py-5 text-sm text-red-200 backdrop-blur-md shadow-[0_0_30px_rgba(239,68,68,0.1)]"
          >
            <AlertCircle className="h-6 w-6 text-red-400 shrink-0" />
            <div>
              <h3 className="font-semibold text-lg">{t('templates.load_error')}</h3>
              <p className="text-zinc-400 mt-1">{error}</p>
              <button onClick={loadTemplates} className="mt-3 text-xs font-semibold uppercase tracking-wider text-red-400 hover:text-red-300">{t('common.retry')}</button>
            </div>
          </motion.div>
        ) : (
          <motion.div 
            key="content"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="space-y-6"
          >
            {/* Search, Tabs, Filters Area */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white/[0.01] border border-white/5 rounded-3xl p-4">
              
              {/* Tabs */}
              <div className="flex items-center bg-black/40 rounded-xl p-1 border border-white/5 shrink-0 self-start md:self-auto">
                {[
                  { id: 'all', label: t('templates.tab_all') },
                  { id: 'private', label: t('templates.tab_private') },
                  { id: 'public', label: t('templates.tab_public') }
                ].map(tab => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setSelectedTab(tab.id)}
                    className={`px-4 py-2 rounded-lg text-xs font-bold tracking-wide uppercase transition-all duration-200 cursor-pointer ${
                      selectedTab === tab.id 
                        ? 'bg-cyan-500 text-black shadow-[0_0_10px_rgba(34,211,238,0.2)]' 
                        : 'text-zinc-400 hover:text-white'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Search input */}
              <div className="relative flex-1 max-w-md w-full">
                <Search className="absolute left-3.5 rtl:left-auto rtl:right-3.5 h-4 w-4 text-zinc-500 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder={t('templates.search_placeholder')}
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full rounded-2xl border border-white/10 bg-black/40 px-4 py-3 pl-11 rtl:pl-4 rtl:pr-11 text-xs text-zinc-200 placeholder:text-zinc-600 outline-none transition-all focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/20"
                />
              </div>
            </div>

            {/* Category selection */}
            <div className="flex flex-wrap items-center gap-2">
              {CATEGORIES.map(cat => {
                const catKey = cat.toLowerCase()
                const label = t('templates.cat_' + catKey) || cat
                return (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => setSelectedCategory(cat)}
                    className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-all cursor-pointer ${
                      selectedCategory === cat 
                        ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.1)]' 
                        : 'bg-white/[0.01] border-white/5 text-zinc-500 hover:border-white/15 hover:text-zinc-300'
                    }`}
                  >
                    {label}
                  </button>
                )
              })}
            </div>

            {/* Blueprints Display Table */}
            {filteredTemplates.length > 0 ? (
              <div className="glass-panel rounded-3xl overflow-hidden border border-white/5 shadow-2xl">
                <table className="w-full text-left rtl:text-right border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-white/5 text-zinc-500 uppercase text-[9px] font-bold tracking-wider bg-white/[0.002]">
                      <th className="px-6 py-4">{t('templates.col_template_name')}</th>
                      <th className="px-6 py-4">{t('templates.col_category')}</th>
                      <th className="px-6 py-4">{t('templates.col_visibility')}</th>
                      <th className="px-6 py-4">{t('templates.col_steps_profile')}</th>
                      <th className="px-6 py-4">{t('templates.col_last_modified')}</th>
                      <th className="px-6 py-4 text-right rtl:text-left">{t('templates.col_actions')}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {filteredTemplates.map(tpl => {
                      const stepsCount = tpl.workflow_definition?.length ?? 0
                      
                      return (
                        <tr 
                          key={tpl.id}
                          onClick={() => navigate(`/create-request?templateId=${tpl.id}`)}
                          className="hover:bg-white/[0.02] transition-colors group/row cursor-pointer"
                        >
                          <td className="px-6 py-4 align-middle">
                            <div className="space-y-0.5">
                              <span className="font-semibold text-white group-hover:text-cyan-400 transition-colors leading-tight">
                                {tpl.name}
                              </span>
                              {tpl.description && (
                                <p className="text-[11px] text-zinc-500 truncate max-w-[240px]">{tpl.description}</p>
                              )}
                            </div>
                          </td>
                          <td className="px-6 py-4 align-middle">
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold border border-cyan-500/10 bg-cyan-500/5 text-cyan-400 uppercase tracking-wider">
                              {t('templates.cat_' + (tpl.category?.toLowerCase() || 'general')) || tpl.category || 'General'}
                            </span>
                          </td>
                          <td className="px-6 py-4 align-middle">
                            <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold border capitalize ${
                              tpl.visibility === 'public'
                                ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400'
                                : 'border-zinc-500/20 bg-zinc-500/10 text-zinc-400'
                            }`}>
                              {tpl.visibility === 'public' ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
                              {tpl.visibility === 'public' ? t('templates.visibility_public') : t('templates.visibility_private')}
                            </span>
                          </td>
                          <td className="px-6 py-4 align-middle font-mono text-zinc-300 font-bold">
                            {stepsCount === 1 ? t('templates.steps_preset_single') : t('templates.steps_preset', { count: stepsCount })}
                          </td>
                          <td className="px-6 py-4 align-middle text-zinc-500 text-xs font-medium">
                            {new Date(tpl.updated_at).toLocaleDateString(undefined, {
                              month: 'short',
                              day: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit'
                            })}
                          </td>
                          <td className="px-6 py-4 align-middle text-right rtl:text-left" onClick={e => e.stopPropagation()}>
                            <div className="flex items-center justify-end rtl:justify-start gap-2">
                              <Link
                                to={`/create-request?templateId=${tpl.id}`}
                                className="inline-flex items-center gap-1 rounded-lg bg-cyan-500 hover:bg-cyan-400 px-3 py-1.5 text-[11px] font-bold text-black transition-all cursor-pointer"
                                title={t('templates.btn_use')}
                              >
                                <Play className="h-3 w-3 fill-black text-black rtl:rotate-180" />
                                {t('templates.btn_use')}
                              </Link>
                              
                              <button
                                type="button"
                                onClick={(e) => handleEditClick(tpl, e)}
                                className="rounded-lg p-2 bg-zinc-800 border border-white/5 hover:border-cyan-500/30 text-zinc-400 hover:text-cyan-400 transition-all cursor-pointer"
                                title={t('templates.btn_edit')}
                              >
                                <Edit3 className="h-3.5 w-3.5" />
                              </button>

                              <button
                                type="button"
                                onClick={(e) => handleDelete(tpl.id, e)}
                                className="rounded-lg p-2 bg-zinc-800 border border-white/5 hover:border-red-500/30 text-zinc-400 hover:text-red-400 transition-all cursor-pointer"
                                title={t('templates.btn_delete')}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              /* Onboarding Empty State */
              <div className="flex flex-col items-center justify-center py-24 text-center space-y-4 bg-white/[0.005] border border-dashed border-white/10 rounded-[2rem] px-4">
                <div className="rounded-full bg-cyan-500/10 border border-cyan-500/20 p-5 text-cyan-400 animate-pulse">
                  <Bookmark className="h-10 w-10" />
                </div>
                <div className="space-y-1 max-w-sm">
                  <h3 className="text-base font-semibold text-white">{t('templates.empty_title')}</h3>
                  <p className="text-xs text-zinc-500">{t('templates.empty_desc')}</p>
                </div>
                <button
                  type="button"
                  onClick={handleCreateClick}
                  className="inline-flex items-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black px-5 py-3 text-xs font-bold transition-all shadow-[0_0_15px_rgba(34,211,238,0.2)] cursor-pointer"
                >
                  <Plus className="h-4 w-4 stroke-[3]" />
                  {t('templates.btn_create')}
                </button>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Edit & Create Template Modal */}
      <AnimatePresence>
        {editingTemplate && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            {/* Backdrop blur */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setEditingTemplate(null)}
              className="absolute inset-0 bg-black/80 backdrop-blur-md"
            />

            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 15 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 15 }}
              className="relative w-full max-w-2xl overflow-hidden rounded-[2rem] border border-white/10 bg-[#0B1220] p-6 sm:p-8 shadow-[0_25px_60px_rgba(0,0,0,0.95),0_0_30px_rgba(34,211,238,0.15)] z-10"
            >
              <button
                type="button"
                onClick={() => setEditingTemplate(null)}
                className="absolute right-6 rtl:right-auto rtl:left-6 top-6 rounded-full bg-white/5 p-1 text-zinc-400 hover:bg-white/10 hover:text-white transition-colors cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>

              <div className="mb-6 space-y-1">
                <div className="inline-flex items-center gap-1.5 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-cyan-400">
                  <Sparkles className="h-3 w-3" />
                  {t('templates.blueprint_studio')}
                </div>
                <h3 className="text-xl font-light text-white sm:text-2xl">
                  {editingTemplate.id === 'new' ? t('templates.modal_create_title') : t('templates.modal_edit_title')}
                </h3>
                <p className="text-xs text-zinc-500">{t('templates.modal_subtitle')}</p>
              </div>

              {/* Three Tab Navigation */}
              <div className="flex items-center bg-black/40 rounded-xl p-1 border border-white/5 mb-6 shrink-0">
                {[
                  { id: 'details', label: t('templates.tab_step_1') },
                  { id: 'workflow', label: t('templates.tab_step_2') },
                  { id: 'settings', label: t('templates.tab_step_3') }
                ].map(tab => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setModalActiveTab(tab.id)}
                    className={`flex-1 py-2 rounded-lg text-xs font-bold tracking-wide uppercase transition-all duration-200 cursor-pointer ${
                      modalActiveTab === tab.id 
                        ? 'bg-cyan-500 text-black shadow-[0_0_10px_rgba(34,211,238,0.2)]' 
                        : 'text-zinc-400 hover:text-white'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              <form onSubmit={handleUpdate} className="space-y-4">
                
                {/* TAB 1: General Details */}
                {modalActiveTab === 'details' && (
                  <div className="space-y-4">
                    <div className="space-y-1.5">
                      <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wide">{t('templates.label_name')}</label>
                      <input
                        type="text"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        placeholder={t('templates.placeholder_name')}
                        className="w-full rounded-xl border border-white/10 bg-black/40 px-4 py-3 text-xs text-zinc-200 outline-none transition-all focus:border-cyan-500/40 focus:bg-cyan-950/5 focus:ring-1 focus:ring-cyan-500/20"
                        required
                      />
                    </div>

                    <div className="space-y-1.5">
                      <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wide">{t('templates.label_description')}</label>
                      <textarea
                        rows="3"
                        value={editDesc}
                        onChange={(e) => setEditDesc(e.target.value)}
                        placeholder={t('templates.placeholder_description')}
                        className="w-full rounded-xl border border-white/10 bg-black/40 px-4 py-3 text-xs text-zinc-200 outline-none transition-all focus:border-cyan-500/40 resize-none focus:bg-cyan-950/5 focus:ring-1 focus:ring-cyan-500/20"
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-1.5">
                        <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wide">{t('templates.label_category')}</label>
                        <select
                          value={editCategory}
                          onChange={(e) => setEditCategory(e.target.value)}
                          className="w-full rounded-xl border border-white/10 bg-black/60 px-4 py-3 text-xs text-zinc-200 outline-none cursor-pointer focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/20"
                        >
                          {CATEGORIES.filter(c => c !== 'All').map(c => (
                            <option key={c} value={c} className="bg-[#0B1220]">{t('templates.cat_' + c.toLowerCase()) || c}</option>
                          ))}
                        </select>
                      </div>

                      <div className="space-y-1.5">
                        <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wide">{t('templates.label_visibility')}</label>
                        <select
                          value={editVisibility}
                          onChange={(e) => setEditVisibility(e.target.value)}
                          className="w-full rounded-xl border border-white/10 bg-black/60 px-4 py-3 text-xs text-zinc-200 outline-none cursor-pointer focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/20"
                        >
                          <option value="private" className="bg-[#0B1220]">{t('templates.visibility_private_self')}</option>
                          <option value="public" className="bg-[#0B1220]">{t('templates.visibility_public_shared')}</option>
                        </select>
                      </div>
                    </div>
                  </div>
                )}

                {/* TAB 2: Workflow Blueprint */}
                {modalActiveTab === 'workflow' && (
                  <div className="space-y-4">
                    <div className="flex justify-between items-center pb-2 border-b border-white/5">
                      <span className="text-xs font-bold text-zinc-400 uppercase tracking-wider">{t('templates.step_config_title')}</span>
                      <button
                        type="button"
                        onClick={addModalStep}
                        className="inline-flex items-center gap-1 px-3 py-1.5 text-[11px] font-bold rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 hover:bg-cyan-500 hover:text-black hover:border-cyan-400 transition-all cursor-pointer"
                      >
                        <Plus className="h-3.5 w-3.5" />
                        {t('templates.btn_add_step')}
                      </button>
                    </div>

                    <div className="max-h-60 overflow-y-auto pr-1 space-y-3 custom-scrollbar">
                      {modalSteps.map((step, idx) => (
                        <div key={idx} className="flex items-center gap-3 bg-white/[0.02] border border-white/5 rounded-2xl p-3 relative group">
                          {/* Step Number Input */}
                          <div className="w-16 space-y-1">
                            <span className="block text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">{t('templates.step_label')}</span>
                            <input
                              type="number"
                              min="1"
                              value={step.step || 1}
                              onChange={(e) => updateModalStep(idx, 'step', parseInt(e.target.value) || 1)}
                              className="w-full rounded-lg border border-white/10 bg-black/40 px-2 py-1.5 text-xs text-zinc-200 outline-none transition-all text-center focus:border-cyan-500/40"
                            />
                          </div>

                          {/* Role Selector */}
                          <div className="flex-1 space-y-1">
                            <span className="block text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">{t('templates.label_role')}</span>
                            <select
                              value={step.role || 'signer'}
                              onChange={(e) => updateModalStep(idx, 'role', e.target.value)}
                              className="w-full rounded-lg border border-white/10 bg-black/60 px-3 py-1.5 text-xs text-zinc-200 outline-none cursor-pointer focus:border-cyan-500/40"
                            >
                              <option value="signer" className="bg-[#0B1220]">{t('templates.role_signer_desc')}</option>
                              <option value="approver" className="bg-[#0B1220]">{t('templates.role_approver_desc')}</option>
                              <option value="reviewer" className="bg-[#0B1220]">{t('templates.role_reviewer_desc')}</option>
                              <option value="cc" className="bg-[#0B1220]">{t('templates.role_cc_desc')}</option>
                            </select>
                          </div>

                          {/* Action Button */}
                          <button
                            type="button"
                            onClick={() => removeModalStep(idx)}
                            className="rounded-lg p-2 bg-zinc-800 border border-white/5 hover:border-red-500/30 text-zinc-400 hover:text-red-400 transition-all cursor-pointer self-end shrink-0"
                            title={t('common.delete')}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ))}

                      {modalSteps.length === 0 && (
                        <div className="text-center py-8 text-zinc-500 text-xs">
                          {t('templates.no_steps_defined')}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* TAB 3: Request Settings */}
                {modalActiveTab === 'settings' && (
                  <div className="space-y-4">
                    {/* Toggle cards */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      
                      {/* Reminders */}
                      <div className="bg-white/[0.01] border border-white/5 rounded-2xl p-4 flex flex-col justify-between min-h-[110px] transition-all duration-300 hover:border-cyan-500/20">
                        <div className="flex justify-between items-start">
                          <span className="text-[9px] uppercase font-bold tracking-widest text-zinc-500">{t('templates.card_alerts')}</span>
                          <Bell className={`h-4 w-4 ${modalSendReminders ? 'text-cyan-400' : 'text-zinc-500'}`} />
                        </div>
                        <div className="mt-2 space-y-1.5">
                          <h4 className="text-xs font-bold text-white leading-tight">{t('templates.card_reminders')}</h4>
                          <label className="flex items-center gap-2 cursor-pointer select-none">
                            <input
                              type="checkbox"
                              checked={modalSendReminders}
                              onChange={(e) => setModalSendReminders(e.target.checked)}
                              className="sr-only peer"
                            />
                            <div className="relative w-8 h-5 bg-white/10 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-zinc-400 after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-cyan-500 peer-checked:after:bg-black peer-checked:after:border-cyan-400" />
                          </label>
                        </div>
                      </div>

                      {/* Final Delivery */}
                      <div className="bg-white/[0.01] border border-white/5 rounded-2xl p-4 flex flex-col justify-between min-h-[110px] transition-all duration-300 hover:border-cyan-500/20">
                        <div className="flex justify-between items-start">
                          <span className="text-[9px] uppercase font-bold tracking-widest text-zinc-500">{t('templates.card_delivery')}</span>
                          <Share2 className={`h-4 w-4 ${modalSendFinalEmail ? 'text-cyan-400' : 'text-zinc-500'}`} />
                        </div>
                        <div className="mt-2 space-y-1.5">
                          <h4 className="text-xs font-bold text-white leading-tight">{t('templates.card_final_email')}</h4>
                          <label className="flex items-center gap-2 cursor-pointer select-none">
                            <input
                              type="checkbox"
                              checked={modalSendFinalEmail}
                              onChange={(e) => setModalSendFinalEmail(e.target.checked)}
                              className="sr-only peer"
                            />
                            <div className="relative w-8 h-5 bg-white/10 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-zinc-400 after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-cyan-500 peer-checked:after:bg-black peer-checked:after:border-cyan-400" />
                          </label>
                        </div>
                      </div>

                      {/* Print Permission */}
                      <div className="bg-white/[0.01] border border-white/5 rounded-2xl p-4 flex flex-col justify-between min-h-[110px] transition-all duration-300 hover:border-cyan-500/20">
                        <div className="flex justify-between items-start">
                          <span className="text-[9px] uppercase font-bold tracking-widest text-zinc-500">{t('templates.card_permissions')}</span>
                          <Printer className={`h-4 w-4 ${modalAllowPrinting ? 'text-cyan-400' : 'text-zinc-500'}`} />
                        </div>
                        <div className="mt-2 space-y-1.5">
                          <h4 className="text-xs font-bold text-white leading-tight">{t('templates.card_allow_printing')}</h4>
                          <label className="flex items-center gap-2 cursor-pointer select-none">
                            <input
                              type="checkbox"
                              checked={modalAllowPrinting}
                              onChange={(e) => setModalAllowPrinting(e.target.checked)}
                              className="sr-only peer"
                            />
                            <div className="relative w-8 h-5 bg-white/10 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-zinc-400 after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-cyan-500 peer-checked:after:bg-black peer-checked:after:border-cyan-400" />
                          </label>
                        </div>
                      </div>

                    </div>

                    {/* Additional Observers */}
                    <div className="bg-white/[0.005] border border-white/5 rounded-2xl p-4 space-y-3">
                      <div>
                        <h4 className="text-xs font-bold text-white flex items-center gap-1">
                          <Mail className="h-3.5 w-3.5 text-cyan-400" />
                          {t('templates.cc_observers_title')}
                        </h4>
                        <p className="text-[9px] text-zinc-500 mt-0.5">{t('templates.cc_observers_desc')}</p>
                      </div>

                      <div className="flex gap-2">
                        <input
                          type="email"
                          value={modalNewCCEmail}
                          onChange={(e) => {
                            setModalNewCCEmail(e.target.value)
                            setModalCCError('')
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault()
                              addModalCC()
                            }
                          }}
                          placeholder={t('templates.placeholder_cc_email')}
                          className="flex-1 rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-cyan-500/40"
                        />
                        <button
                          type="button"
                          onClick={addModalCC}
                          className="inline-flex items-center justify-center gap-1 rounded-xl bg-zinc-800 hover:bg-cyan-500 hover:text-black border border-white/10 px-4 py-2 text-xs font-bold text-zinc-300 transition-all cursor-pointer shrink-0"
                        >
                          <Plus className="h-3.5 w-3.5" />
                          {t('templates.btn_add_cc_btn')}
                        </button>
                      </div>

                      {modalCCError && (
                        <p className="text-[10px] text-red-400 font-semibold">{modalCCError}</p>
                      )}

                      {modalAdditionalRecipients.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 pt-1.5">
                          {modalAdditionalRecipients.map((email) => (
                            <span
                              key={email}
                              className="inline-flex items-center gap-1 rounded-lg border border-cyan-500/20 bg-cyan-500/10 px-2.5 py-1 text-[10px] font-medium text-cyan-300 font-mono"
                            >
                              {email}
                              <button
                                type="button"
                                onClick={() => removeModalCC(email)}
                                className="rounded p-0.5 hover:bg-cyan-500/20 text-cyan-400 hover:text-cyan-200 transition-colors cursor-pointer"
                              >
                                <X className="h-3 w-3" />
                              </button>
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {updateError && (
                  <p className="text-xs font-semibold text-red-400 mt-2">{updateError}</p>
                )}

                <div className="flex justify-end rtl:justify-start gap-3 pt-4 border-t border-white/5">
                  <button
                    type="button"
                    onClick={() => setEditingTemplate(null)}
                    disabled={isUpdating}
                    className="rounded-xl bg-zinc-800 hover:bg-zinc-700 border border-white/5 px-4 py-2.5 text-xs font-semibold text-zinc-300 transition-all cursor-pointer"
                  >
                    {t('common.cancel')}
                  </button>
                  <button
                    type="submit"
                    disabled={isUpdating}
                    className="inline-flex items-center justify-center rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black px-5 py-2.5 text-xs font-bold transition-all shadow-[0_0_15px_rgba(34,211,238,0.15)] cursor-pointer"
                  >
                    {isUpdating ? t('templates.btn_saving') : t('templates.btn_save')}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  )
}
