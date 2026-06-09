import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface FreshnessInfo {
  status: string
  latest_trading_date?: string
  total_active_stocks?: number
  collected_daily_count?: number
  daily_coverage_ratio?: number
  is_daily_fresh?: boolean
  offline?: boolean
  message?: string
}

export interface GapItem {
  date: string
  status: string
  total_targets: number
  valid_targets: number
  missing_count: number
  missing_items: string[]
}

export interface IntegratedGaps {
  market: string
  start_date: string
  end_date: string
  gaps: GapItem[]
  offline?: boolean
}

export interface Milestone {
  milestone_name: string
  milestone_date: string
  description?: string
  updated_at?: string
}

export interface BlacklistItem {
  cik: string
  ticker: string
  reason_cd: string
  detail: string
  is_blocked: boolean
  updated_at?: string
}

export interface BlacklistResponse {
  status: string
  blocked_count: number
  blacklist: BlacklistItem[]
  offline?: boolean
}

export const useHealthStore = defineStore('health', () => {
  const krFreshness = ref<FreshnessInfo | null>(null)
  const usFreshness = ref<FreshnessInfo | null>(null)
  
  const krGaps = ref<IntegratedGaps | null>(null)
  const usGaps = ref<IntegratedGaps | null>(null)
  
  const milestones = ref<Milestone[]>([])
  const blacklist = ref<BlacklistItem[]>([])
  const blacklistOffline = ref(false)

  const loadingFreshness = ref(false)
  const loadingGaps = ref(false)
  const loadingMilestones = ref(false)
  const loadingBlacklist = ref(false)

  // 1. 신선도 조회
  const fetchFreshness = async (market: 'kr' | 'us') => {
    loadingFreshness.value = true
    try {
      const resp = await fetch(`/api/mgr/health/freshness/${market}`)
      const data = await resp.json()
      if (market === 'kr') {
        krFreshness.value = data
      } else {
        usFreshness.value = data
      }
    } catch (err) {
      const offlineFallback = { status: 'RED', offline: true, message: String(err) }
      if (market === 'kr') {
        krFreshness.value = offlineFallback
      } else {
        usFreshness.value = offlineFallback
      }
    } finally {
      loadingFreshness.value = false
    }
  }

  // 2. 갭 조회
  const fetchGaps = async (market: 'kr' | 'us', startDate?: string, endDate?: string) => {
    loadingGaps.value = true
    try {
      const params = new URLSearchParams()
      if (startDate) params.append('start_date', startDate)
      if (endDate) params.append('end_date', endDate)
      
      const resp = await fetch(`/api/mgr/health/gaps/${market}?${params.toString()}`)
      const data = await resp.json()
      if (market === 'kr') {
        krGaps.value = data
      } else {
        usGaps.value = data
      }
    } catch (err) {
      const fallback: IntegratedGaps = {
        market,
        start_date: startDate || '',
        end_date: endDate || '',
        gaps: [],
        offline: true
      }
      if (market === 'kr') {
        krGaps.value = fallback
      } else {
        usGaps.value = fallback
      }
    } finally {
      loadingGaps.value = false
    }
  }

  // 3. 한국 마일스톤 조회
  const fetchMilestones = async () => {
    loadingMilestones.value = true
    try {
      const resp = await fetch('/api/mgr/health/kr/milestones')
      if (resp.ok) {
        milestones.value = await resp.json()
      } else {
        milestones.value = []
      }
    } catch (err) {
      milestones.value = []
    } finally {
      loadingMilestones.value = false
    }
  }

  // 4. 한국 마일스톤 등록/수정
  const createMilestone = async (payload: Milestone) => {
    const resp = await fetch('/api/mgr/health/kr/milestones', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!resp.ok) {
      const txt = await resp.text()
      throw new Error(`마일스톤 등록 실패: ${txt}`)
    }
    await fetchMilestones()
  }

  // 5. 미국 블랙리스트 조회
  const fetchBlacklist = async () => {
    loadingBlacklist.value = true
    try {
      const resp = await fetch('/api/mgr/health/us/blacklist')
      const data = await resp.json()
      blacklist.value = data.blacklist || []
      blacklistOffline.value = !!data.offline
    } catch (err) {
      blacklist.value = []
      blacklistOffline.value = true
    } finally {
      loadingBlacklist.value = false
    }
  }

  // 6. 미국 블랙리스트 차단 해제
  const releaseBlacklist = async (cik: string) => {
    const resp = await fetch(`/api/mgr/health/us/blacklist/${cik}/release`, {
      method: 'POST'
    })
    if (!resp.ok) {
      const txt = await resp.text()
      throw new Error(`블랙리스트 해제 실패: ${txt}`)
    }
    await fetchBlacklist()
  }

  return {
    krFreshness,
    usFreshness,
    krGaps,
    usGaps,
    milestones,
    blacklist,
    blacklistOffline,
    loadingFreshness,
    loadingGaps,
    loadingMilestones,
    loadingBlacklist,
    fetchFreshness,
    fetchGaps,
    fetchMilestones,
    createMilestone,
    fetchBlacklist,
    releaseBlacklist
  }
})
