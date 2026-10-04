import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import enMessages from '../locales/en.json'

// Safely discover and load any existing locale JSON files via Vite eager glob
const localeFiles = import.meta.glob('../locales/*.json', { eager: true, import: 'default' })

const LocaleContext = createContext()

const messages = {
  en: enMessages,
  ar: localeFiles['../locales/ar.json'] || {},
}

export function LocaleProvider({ children }) {
  const [language, setLanguage] = useState(() => {
    return localStorage.getItem('esign_locale') || 'en'
  })

  useEffect(() => {
    const isRtl = language === 'ar'
    document.documentElement.dir = isRtl ? 'rtl' : 'ltr'
    document.documentElement.lang = language
    localStorage.setItem('esign_locale', language)
  }, [language])

  const toggleLanguage = useCallback(() => {
    setLanguage((prev) => (prev === 'en' ? 'ar' : 'en'))
  }, [])

  const t = useCallback(
    (key, params) => {
      const activeDict = messages[language] || messages.en
      const targetVal = activeDict?.[key]
      const fallbackVal = messages.en?.[key]

      // If active dictionary value exists and is non-empty, use it; otherwise fallback to en, then key
      let template = (typeof targetVal === 'string' && targetVal.trim() !== '')
        ? targetVal
        : (typeof fallbackVal === 'string' && fallbackVal.trim() !== '')
          ? fallbackVal
          : key

      if (typeof template === 'string' && params) {
        Object.entries(params).forEach(([paramKey, val]) => {
          template = template.replace(new RegExp(`\\{${paramKey}\\}`, 'g'), String(val))
        })
      }

      return template
    },
    [language]
  )

  return (
    <LocaleContext.Provider value={{ language, setLanguage, toggleLanguage, t }}>
      {children}
    </LocaleContext.Provider>
  )
}

export function useLocale() {
  const context = useContext(LocaleContext)
  if (!context) {
    throw new Error('useLocale must be used within a LocaleProvider')
  }
  return context
}
