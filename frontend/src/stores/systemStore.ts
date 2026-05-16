import { create } from 'zustand'
import type { SystemStatus } from '../types'

interface SystemStore {
  status: SystemStatus | null
  wsConnected: boolean
  activePanel: 'flow' | 'mt5' | 'analytics' | 'replay'
  setStatus: (s: SystemStatus) => void
  setWsConnected: (v: boolean) => void
  setActivePanel: (p: 'flow' | 'mt5' | 'analytics' | 'replay') => void
}

export const useSystemStore = create<SystemStore>((set) => ({
  status: null,
  wsConnected: false,
  activePanel: 'flow',

  setStatus(s) { set({ status: s }) },
  setWsConnected(v) { set({ wsConnected: v }) },
  setActivePanel(p) { set({ activePanel: p }) },
}))
