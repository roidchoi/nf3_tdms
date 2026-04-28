// src/stores/healthStore.ts
import { defineStore } from 'pinia'
import http from '@/api/http'
import type { 
  HealthFreshness, HealthFinancials, HealthFactors, GapCheckResponse, SystemMilestone 
} from '@/types/health'

export const useHealthStore = defineStore('health', {
  state: () => ({
    freshness: null as HealthFreshness | null,
    financials: null as HealthFinancials | null,
    factors: null as HealthFactors | null,
    gapResult: null as GapCheckResponse | null,
    milestones: [] as SystemMilestone[], // [신규] 마일스톤 상태
    isLoading: false,
  }),

  actions: {
    async fetchDashboardData() {
      this.isLoading = true
      try {
        // 병렬 호출로 속도 최적화
        const [resFresh, resFin, resFact, resMile] = await Promise.all([
          http.get<HealthFreshness>('/health/freshness'),
          http.get<HealthFinancials>('/health/financials'),
          http.get<HealthFactors>('/health/factors'),
          http.get<SystemMilestone[]>('/health/milestones')
        ])
        
        this.freshness = resFresh.data
        this.financials = resFin.data
        this.factors = resFact.data
        this.milestones = resMile.data
      } catch (error) {
        console.error('Health Dashboard 데이터 로드 실패:', error)
      } finally {
        this.isLoading = false
      }
    },

    // [신규] 마일스톤 생성 액션
    async createMilestone(payload: { milestone_name: string; milestone_date: string; description: string }) {
      try {
        await http.post('/health/milestones', payload)
        // 등록 후 목록 갱신 (전체 대시보드 갱신 대신 마일스톤만 갱신해도 되지만 편의상 재호출)
        const res = await http.get<SystemMilestone[]>('/health/milestones')
        this.milestones = res.data
        return true
      } catch (error) {
        console.error('마일스톤 생성 실패:', error)
        throw error
      }
    },

    async checkGaps(startDate: string, endDate: string) {
      this.isLoading = true
      try {
        const response = await http.post<GapCheckResponse>('/health/gaps', {
          start_date: startDate,
          end_date: endDate
        })
        this.gapResult = response.data
      } catch (error) {
        console.error('누락일 검사 실패:', error)
        throw error
      } finally {
        this.isLoading = false
      }
    }
  }
})