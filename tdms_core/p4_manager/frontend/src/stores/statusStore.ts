import { defineStore } from 'pinia'
import http from '@/api/http'
import type { IntegratedStatus } from '@/types/admin'

export const useStatusStore = defineStore('status', {
  state: () => ({
    status: {
      kr: { status: 'OFFLINE', freshness: null, tasks: null },
      us: { status: 'OFFLINE', freshness: null, tasks: null }
    } as IntegratedStatus,
    isFetching: false
  }),
  actions: {
    async fetchStatus() {
      if (this.isFetching) return
      this.isFetching = true
      try {
        const response = await http.get<IntegratedStatus>('/status')
        this.status = response.data
      } catch (error) {
        console.error('Failed to fetch integrated status:', error)
      } finally {
        this.isFetching = false
      }
    },
    async runTask(market: 'kr' | 'us', taskId: string, isTest: boolean = true) {
      try {
        const response = await http.post(`/run?market=${market}&task_id=${taskId}&is_test=${isTest}`)
        await this.fetchStatus()
        return response.data
      } catch (error) {
        console.error(`Failed to run task ${taskId} on market ${market}:`, error)
        throw error
      }
    }
  }
})
