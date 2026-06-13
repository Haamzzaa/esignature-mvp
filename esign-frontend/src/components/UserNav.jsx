import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { User, LogOut, Sun, Moon } from 'lucide-react'

export default function UserNav() {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  
  if (!user) return null
  
  return (
    <div className="flex items-center gap-3 glass-panel rounded-xl px-4 h-10 text-xs text-text-secondary">
      <div className="flex items-center gap-1.5">
        <div className="h-1.5 w-1.5 rounded-full bg-cyan-400 shadow-[0_0_6px_rgba(34,211,238,0.4)] animate-pulse" />
        <span className="font-semibold text-text-primary">{user.username}</span>
      </div>
      <div className="h-3 w-px bg-border-color" />
      <button
        type="button"
        onClick={toggleTheme}
        className="text-text-secondary hover:text-cyan-400 transition-colors cursor-pointer font-medium flex items-center gap-1 focus:outline-none"
        title={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
      >
        {theme === 'light' ? <Moon className="h-3.5 w-3.5" /> : <Sun className="h-3.5 w-3.5" />}
        <span>{theme === 'light' ? 'Dark' : 'Light'}</span>
      </button>
      <div className="h-3 w-px bg-border-color" />
      <button
        type="button"
        onClick={logout}
        className="text-text-secondary hover:text-red-400 transition-colors cursor-pointer font-medium flex items-center gap-1 focus:outline-none"
        title="Sign out of workspace"
      >
        <LogOut className="h-3.5 w-3.5" />
        <span>Logout</span>
      </button>
    </div>
  )
}
