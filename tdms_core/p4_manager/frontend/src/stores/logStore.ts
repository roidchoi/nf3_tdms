import { defineStore } from 'pinia'

export interface LogState {
  krLogs: string[]
  usLogs: string[]
  krWsStatus: 'CONNECTING' | 'CONNECTED' | 'DISCONNECTED'
  usWsStatus: 'CONNECTING' | 'CONNECTED' | 'DISCONNECTED'
}

let krWs: WebSocket | null = null
let usWs: WebSocket | null = null

export const useLogStore = defineStore('log', {
  state: (): LogState => ({
    krLogs: [],
    usLogs: [],
    krWsStatus: 'DISCONNECTED',
    usWsStatus: 'DISCONNECTED',
  }),
  actions: {
    connectLogs(market: 'kr' | 'us', logFile?: string): void {
      // 1. 기존 연결 클리어
      this.disconnectLogs(market)

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const host = window.location.host
      // Nginx /ws/logs/{market} 주소와 매핑
      let url = `${protocol}//${host}/ws/logs/${market}`
      if (logFile) {
        url += `?log_file=${encodeURIComponent(logFile)}`
      }

      if (market === 'kr') {
        this.krWsStatus = 'CONNECTING'
        krWs = new WebSocket(url)

        krWs.onopen = () => {
          this.krWsStatus = 'CONNECTED'
        }

        krWs.onmessage = (event) => {
          this.krLogs.push(event.data)
          if (this.krLogs.length > 500) {
            this.krLogs.shift()
          }
        }

        krWs.onclose = () => {
          this.krWsStatus = 'DISCONNECTED'
          krWs = null
        }

        krWs.onerror = () => {
          this.krWsStatus = 'DISCONNECTED'
          krWs = null
        }
      } else {
        this.usWsStatus = 'CONNECTING'
        usWs = new WebSocket(url)

        usWs.onopen = () => {
          this.usWsStatus = 'CONNECTED'
        }

        usWs.onmessage = (event) => {
          this.usLogs.push(event.data)
          if (this.usLogs.length > 500) {
            this.usLogs.shift()
          }
        }

        usWs.onclose = () => {
          this.usWsStatus = 'DISCONNECTED'
          usWs = null
        }

        usWs.onerror = () => {
          this.usWsStatus = 'DISCONNECTED'
          usWs = null
        }
      }
    },
    disconnectLogs(market: 'kr' | 'us'): void {
      if (market === 'kr') {
        if (krWs) {
          krWs.close()
          krWs = null
        }
        this.krWsStatus = 'DISCONNECTED'
      } else {
        if (usWs) {
          usWs.close()
          usWs = null
        }
        this.usWsStatus = 'DISCONNECTED'
      }
    },
    clearLogs(market: 'kr' | 'us'): void {
      if (market === 'kr') {
        this.krLogs = []
      } else {
        this.usLogs = []
      }
    }
  }
})
