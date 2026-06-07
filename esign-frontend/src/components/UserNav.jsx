import { useAuth } from '../context/AuthContext'
import { User, LogOut } from 'lucide-react'

export default function UserNav() {
  const { user, logout } = useAuth()
  
  if (!user) return null
  
  return (
    <div className="flex items-center gap-3 bg-white/[0.02] border border-white/10 rounded-xl px-4 py-2 text-xs text-zinc-300 backdrop-blur-md">
      <div className="flex items-center gap-1.5">
        <div className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-pulse" />
        <span className="font-semibold text-zinc-300">{user.username}</span>
      </div>
      <div className="h-3 w-px bg-white/15" />
      <button
        type="button"
        onClick={logout}
        className="text-zinc-500 hover:text-red-400 transition-colors cursor-pointer font-medium flex items-center gap-1 focus:outline-none"
        title="Sign out of workspace"
      >
        <LogOut className="h-3.5 w-3.5" />
        <span>Logout</span>
      </button>
    </div>
  )
}
