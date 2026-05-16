import { create } from 'zustand'
import type { AIAnalysis } from '../types'

const MAX_ENTRIES = 20

interface AIStore {
  analyses: AIAnalysis[]
  latest: AIAnalysis | null
  addAnalysis: (a: AIAnalysis) => void
  reset: () => void
}

export const useAIStore = create<AIStore>((set) => ({
  analyses: [],
  latest: null,

  addAnalysis(a) {
    set(s => ({
      latest: a,
      analyses: [a, ...s.analyses].slice(0, MAX_ENTRIES),
    }))
  },

  reset() {
    set({ analyses: [], latest: null })
  },
}))
