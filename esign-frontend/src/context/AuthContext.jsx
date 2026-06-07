import { createContext, useContext, useEffect, useState } from 'react'
import { loginUser, registerUser, logoutUser, getUserMe, apiClient } from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(localStorage.getItem('token'))
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    async function loadUser() {
      if (token) {
        apiClient.defaults.headers.common['Authorization'] = `Token ${token}`
        try {
          const userData = await getUserMe()
          setUser(userData)
        } catch (err) {
          console.error('Failed to load user with current token', err)
          localStorage.removeItem('token')
          delete apiClient.defaults.headers.common['Authorization']
          setToken(null)
          setUser(null)
        }
      } else {
        delete apiClient.defaults.headers.common['Authorization']
      }
      setIsLoading(false)
    }
    loadUser()
  }, [token])

  async function login(username, password) {
    const data = await loginUser(username, password)
    localStorage.setItem('token', data.token)
    apiClient.defaults.headers.common['Authorization'] = `Token ${data.token}`
    setToken(data.token)
    setUser(data.user)
    return data.user
  }

  async function register(username, email, password) {
    const data = await registerUser(username, email, password)
    localStorage.setItem('token', data.token)
    apiClient.defaults.headers.common['Authorization'] = `Token ${data.token}`
    setToken(data.token)
    setUser(data.user)
    return data.user
  }

  async function logout() {
    try {
      await logoutUser()
    } catch (err) {
      console.error('Logout error on server', err)
    } finally {
      localStorage.removeItem('token')
      delete apiClient.defaults.headers.common['Authorization']
      setToken(null)
      setUser(null)
    }
  }

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
