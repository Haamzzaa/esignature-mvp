import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import enMessages from '../locales/en.json'
import arMessages from '../locales/ar.json'

const LocaleContext = createContext()

const messages = {
  en: enMessages,
  ar: arMessages,
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
      let template = Object.prototype.hasOwnProperty.call(activeDict, key)
        ? activeDict[key]
        : Object.prototype.hasOwnProperty.call(messages.en, key)
          ? messages.en[key]
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
