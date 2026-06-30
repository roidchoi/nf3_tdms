import { defineStore } from 'pinia'
import http from '@/api/http'
import axios from 'axios'

export interface SyncStatusResponse {
  status: 'IDLE' | 'RUNNING' | 'SUCCESS' | 'ERROR'
  logs: string[]
  error_message: string
}

export interface AuditResponse {
  status: 'success' | 'error'
  market: string
  audit_type: string
  raw_output: string
}

export interface DetectServerResponse {
  server_ip: string | null
  method: 'dns' | 'scan' | 'failed'
}

export interface ConnectionTestResponse {
  connected: boolean
  message: string
}

export const useSyncStore = defineStore('sync', {
  state: () => ({
    syncStatus: 'IDLE' as 'IDLE' | 'RUNNING' | 'SUCCESS' | 'ERROR',
    syncLogs: [] as string[],
    syncErrorMessage: '',
    loading: false,
    error: null as string | null,
    detectedServerIp: null as string | null,
    detectionMethod: null as 'dns' | 'scan' | 'failed' | null,
    connectionStatus: null as boolean | null,
    connectionMessage: '',
    auditReport: null as string | null,
    auditLoading: false
  }),
  actions: {
    async startSync(market: 'kdms' | 'usdms', direction: 'pull' | 'push', confirmText: string) {
      this.loading = true
      this.error = null
      try {
        const response = await http.post('/sync', {
          market,
          direction,
          confirm_text: confirmText
        })
        this.syncStatus = 'RUNNING'
        return response.data
      } catch (error) {
        console.error('Failed to start sync:', error)
        if (axios.isAxiosError(error) && error.response) {
          this.error = error.response.data?.detail || '동기화 시작에 실패했습니다.'
        } else {
          this.error = '동기화 시작에 실패했습니다. 네트워크 상태를 확인하세요.'
        }
        throw new Error(this.error || '동기화 시작에 실패했습니다.')
      } finally {
        this.loading = false
      }
    },
    async fetchSyncStatus() {
      try {
        const response = await http.get<SyncStatusResponse>('/sync/status')
        this.syncStatus = response.data.status
        this.syncLogs = response.data.logs
        this.syncErrorMessage = response.data.error_message
      } catch (error) {
        console.error('Failed to fetch sync status:', error)
      }
    },
    async runAudit(market: 'kdms' | 'usdms') {
      this.auditLoading = true
      this.error = null
      this.auditReport = null
      try {
        const response = await http.post<AuditResponse>(`/sync/audit?market=${market}`, {}, {
          timeout: 60000
        })
        this.auditReport = response.data.raw_output
        return response.data
      } catch (error) {
        console.error('Failed to run audit:', error)
        if (axios.isAxiosError(error) && error.response) {
          this.error = error.response.data?.detail || '감사 리포트 조회에 실패했습니다.'
        } else {
          this.error = '감사 리포트 조회에 실패했습니다.'
        }
        throw new Error(this.error || '감사 리포트 조회에 실패했습니다.')
      } finally {
        this.auditLoading = false
      }
    },
    async detectServerIp() {
      this.loading = true
      this.error = null
      this.detectedServerIp = null
      this.detectionMethod = null
      try {
        const response = await http.get<DetectServerResponse>('/network/detect-server', {
          timeout: 15000 // 스캔이 조금 더 걸릴 수 있으므로 15초 설정
        })
        this.detectedServerIp = response.data.server_ip
        this.detectionMethod = response.data.method
        return response.data
      } catch (error) {
        console.error('Failed to detect server IP:', error)
        this.error = '서버 IP 탐색에 실패했습니다.'
        throw new Error(this.error || '서버 IP 탐색에 실패했습니다.')
      } finally {
        this.loading = false
      }
    },
    async syncIp(target: 'dev' | 'server', ip: string) {
      this.loading = true
      this.error = null
      try {
        const response = await http.post('/network/sync-ip', {
          target,
          ip
        })
        return response.data
      } catch (error) {
        console.error('Failed to sync IP:', error)
        if (axios.isAxiosError(error) && error.response) {
          this.error = error.response.data?.detail || '.env IP 반영에 실패했습니다.'
        } else {
          this.error = '.env IP 반영에 실패했습니다.'
        }
        throw new Error(this.error || '.env IP 반영에 실패했습니다.')
      } finally {
        this.loading = false
      }
    },
    async testConnection(ip: string, port: number = 8000) {
      this.loading = true
      this.connectionStatus = null
      this.connectionMessage = ''
      try {
        const response = await http.post<ConnectionTestResponse>('/network/test-connection', {
          ip,
          port
        })
        this.connectionStatus = response.data.connected
        this.connectionMessage = response.data.message
        return response.data
      } catch (error) {
        console.error('Failed to test connection:', error)
        this.connectionStatus = false
        this.connectionMessage = '연결 상태를 확인할 수 없습니다.'
        throw new Error(this.connectionMessage)
      } finally {
        this.loading = false
      }
    }
  }
})
