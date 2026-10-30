import { reactive } from 'vue'

function safeParse(raw) {
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

const state = reactive({
  token: localStorage.getItem('dc2_token') || '',
  user: safeParse(localStorage.getItem('dc2_user')) || null,
})

export const authState = state

export function setAuth(token, user) {
  state.token = token
  state.user = user
  localStorage.setItem('dc2_token', token)
  localStorage.setItem('dc2_user', JSON.stringify(user))
}

export function clearAuth() {
  state.token = ''
  state.user = null
  localStorage.removeItem('dc2_token')
  localStorage.removeItem('dc2_user')
}

export function isAdmin() {
  return !!(state.user && state.user.role === 'admin')
}
