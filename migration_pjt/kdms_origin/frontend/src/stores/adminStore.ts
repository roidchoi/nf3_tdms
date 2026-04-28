import { defineStore } from 'pinia'
import http from '@/api/http'
import type { JobStatuses, ScheduleItem, CronConfig, ScheduleCreatePayload } from '@/types/admin'

export const useAdminStore = defineStore('admin', {
  state: () => ({
    // 1. 태스크 상태 (job_statuses)
    statuses: {} as JobStatuses,
    
    // 2. 스케줄 목록
    schedules: [] as ScheduleItem[],
    
    // 3. 실시간 로그 관리
    logs: [] as string[],
    wsConnected: false,
    ws: null as WebSocket | null,
  }),

  actions: {
    // --- [API] 태스크 상태 조회 (Polling용) ---
    async fetchJobStatuses() {
      try {
        // GET /api/v1/admin/tasks/status
        const response = await http.get<JobStatuses>('/admin/tasks/status')
        this.statuses = response.data
      } catch (error) {
        console.error('태스크 상태 조회 실패:', error)
      }
    },

    // --- [API] 스케줄 목록 조회 ---
    async fetchSchedules() {
      try {
        // GET /api/v1/admin/schedules
        // 백엔드 응답 구조: { "schedules": [...] }
        const response = await http.get<{ schedules: ScheduleItem[] }>('/admin/schedules')
        this.schedules = response.data.schedules
      } catch (error) {
        console.error('스케줄 목록 조회 실패:', error)
      }
    },

    // --- [API] 태스크 수동 실행 ---
    async runTask(taskId: string, testMode: boolean = false) {
      try {
        // POST /api/v1/admin/tasks/{task_id}/run
        await http.post(`/admin/tasks/${taskId}/run`, { test_mode: testMode })
        // 실행 즉시 상태 한 번 갱신
        await this.fetchJobStatuses()
        return true
      } catch (error) {
        console.error(`태스크 실행 실패 (${taskId}):`, error)
        throw error
      }
    },

    // [신규] 스케줄 생성
    async createSchedule(payload: ScheduleCreatePayload) {
      try {
        await http.post('/admin/schedules', payload)
        await this.fetchSchedules() // 목록 갱신
        return true
      } catch (error) {
        console.error('스케줄 생성 실패:', error)
        throw error
      }
    },

    // [신규] 스케줄 수정 (시간 변경 등)
    async updateSchedule(scheduleId: string, config: CronConfig) {
      try {
        await http.put(`/admin/schedules/${scheduleId}`, { config })
        await this.fetchSchedules()
        return true
      } catch (error) {
        console.error('스케줄 수정 실패:', error)
        throw error
      }
    },

    // [신규] 스케줄 활성/비활성 토글
    async toggleSchedule(scheduleId: string) {
      try {
        await http.post(`/admin/schedules/${scheduleId}/toggle`)
        await this.fetchSchedules()
        return true
      } catch (error) {
        console.error('스케줄 토글 실패:', error)
        throw error
      }
    },

    // [신규] 스케줄 삭제
    async deleteSchedule(scheduleId: string) {
      try {
        await http.delete(`/admin/schedules/${scheduleId}`)
        await this.fetchSchedules()
        return true
      } catch (error) {
        console.error('스케줄 삭제 실패:', error)
        throw error
      }
    },

    // --- [WebSocket] 실시간 로그 연결 ---
    connectWebSocket() {
      if (this.ws) return // 이미 연결됨

      // Vite 프록시를 통해 연결 (ws://localhost:5173/api/... -> ws://localhost:8000/api/...)
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const wsUrl = `${protocol}//${window.location.host}/api/v1/admin/logs/ws`

      this.ws = new WebSocket(wsUrl)

      this.ws.onopen = () => {
        console.log('[WS] 로그 스트림 연결됨')
        this.wsConnected = true
        this.addLog('--- 실시간 로그 서버에 연결되었습니다 ---')
      }

      this.ws.onmessage = (event) => {
        // 서버에서 온 로그 메시지 저장
        this.addLog(event.data)
      }

      this.ws.onclose = () => {
        console.log('[WS] 연결 종료')
        this.wsConnected = false
        this.ws = null
        // 3초 후 재연결 시도 (간단한 복구 로직)
        setTimeout(() => this.connectWebSocket(), 3000)
      }

      this.ws.onerror = (error) => {
        console.error('[WS] 오류 발생:', error)
        this.ws?.close()
      }
    },

    disconnectWebSocket() {
      if (this.ws) {
        this.ws.close()
        this.ws = null
        this.wsConnected = false
      }
    },

    // 로그 추가 (메모리 관리: 최대 1000줄 유지)
    addLog(message: string) {
      this.logs.push(message)
      if (this.logs.length > 1000) {
        this.logs.shift() // 가장 오래된 로그 삭제
      }
    },
    
    clearLogs() {
      this.logs = []
    }
  }
})