<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useAdminStore } from '@/stores/adminStore'

const adminStore = useAdminStore()
const logContainer = ref<HTMLElement | null>(null)

// 로그가 추가되면 자동으로 스크롤을 맨 아래로 이동
watch(
  () => adminStore.logs.length,
  async () => {
    await nextTick()
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight
    }
  }
)
</script>

<template>
  <div class="terminal-card">
    <div class="terminal-header">
      <div class="left">
        <h4>🖥️ 실시간 시스템 로그</h4>
        <span class="status-dot" :class="{ active: adminStore.wsConnected }"></span>
      </div>
      <button @click="adminStore.clearLogs()" class="clear-btn">로그 비우기</button>
    </div>
    
    <div class="terminal-body" ref="logContainer">
      <div v-if="adminStore.logs.length === 0" class="empty-msg">
        WebSocket 연결 대기 중... 로그가 발생하면 이곳에 출력됩니다.
      </div>
      <div v-for="(log, index) in adminStore.logs" :key="index" class="log-line">
        {{ log }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.terminal-card {
  background: white;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.terminal-header {
  padding: 1rem 1.2rem;
  border-bottom: 1px solid #f1f5f9;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.left {
  display: flex;
  align-items: center;
  gap: 0.8rem;
}

h4 {
  margin: 0;
  font-size: 1rem;
  color: #334155;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #cbd5e1;
}

.status-dot.active {
  background: #10b981; /* Connected Green */
  box-shadow: 0 0 0 2px #d1fae5;
}

.clear-btn {
  font-size: 0.8rem;
  color: #64748b;
  background: none;
  border: 1px solid #e2e8f0;
  padding: 0.3rem 0.6rem;
  border-radius: 4px;
  cursor: pointer;
}

.clear-btn:hover {
  background: #f8fafc;
  color: #334155;
}

.terminal-body {
  flex: 1;
  background: #1e1e1e; /* VS Code Dark Theme bg */
  padding: 1rem;
  overflow-y: auto;
  font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
  font-size: 0.85rem;
  color: #d4d4d4;
  line-height: 1.5;
  min-height: 300px;
  max-height: 500px; /* 높이 제한 */
}

.log-line {
  white-space: pre-wrap; /* 줄바꿈 허용 */
  word-break: break-all;
  border-bottom: 1px solid #333;
  padding-bottom: 2px;
  margin-bottom: 2px;
}

.empty-msg {
  color: #6b7280;
  text-align: center;
  margin-top: 2rem;
}

/* 스크롤바 커스텀 */
.terminal-body::-webkit-scrollbar {
  width: 8px;
}
.terminal-body::-webkit-scrollbar-track {
  background: #1e1e1e;
}
.terminal-body::-webkit-scrollbar-thumb {
  background: #4b5563;
  border-radius: 4px;
}
</style>