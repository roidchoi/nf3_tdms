import { defineStore } from 'pinia'
import http from '@/api/http'
import axios from 'axios'

export interface BackupInfo {
  path: string
  filename: string
  tag: string
  created_at: string
  size_bytes: number
  verified: boolean
}

export const useBackupStore = defineStore('backup', {
  state: () => ({
    currentEnv: 'unknown' as 'dev' | 'server' | 'unknown',
    backups: [] as BackupInfo[],
    loading: false,
    error: null as string | null
  }),
  actions: {
    async fetchEnv() {
      try {
        const response = await http.get<{ env: 'dev' | 'server' | 'unknown' }>('/env')
        this.currentEnv = response.data.env
      } catch (error) {
        console.error('Failed to fetch environment profile:', error)
        this.currentEnv = 'unknown'
      }
    },
    async fetchBackups() {
      this.loading = true
      this.error = null
      try {
        const response = await http.get<BackupInfo[]>('/backup/list')
        this.backups = response.data
      } catch (error) {
        console.error('Failed to fetch backup list:', error)
        this.error = '백업 목록을 불러오는 도중 오류가 발생했습니다.'
      } finally {
        this.loading = false
      }
    },
    async createBackup(tag: string = 'manual') {
      this.loading = true
      this.error = null
      try {
        const response = await http.post(`/backup?tag=${tag}`, {}, {
          timeout: 60000 // 백업은 파일 압축이 있으므로 타임아웃을 60초로 넉넉하게 설정
        })
        await this.fetchBackups()
        return response.data
      } catch (error) {
        console.error('Failed to create backup:', error)
        if (axios.isAxiosError(error) && error.response) {
          const detail = error.response.data?.detail
          this.error = detail || '백업 생성에 실패했습니다.'
        } else {
          this.error = '백업 생성에 실패했습니다. 네트워크 상태를 확인하세요.'
        }
        throw new Error(this.error || '백업 생성에 실패했습니다.')
      } finally {
        this.loading = false
      }
    }
  }
})
