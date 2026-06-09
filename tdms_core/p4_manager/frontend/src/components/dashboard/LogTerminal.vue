<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useLogStore } from '@/stores/logStore'

const logStore = useLogStore()
const activeTab = ref<'kr' | 'us'>('kr')
const autoScroll = ref(true)
const fontSize = ref<'sm' | 'md' | 'lg'>('md')
const isMaximized = ref(false)

const logContainerRef = ref<HTMLDivElement | null>(null)

// 로그 추가 시 하단 스크롤
const scrollToBottom = () => {
  if (!autoScroll.value || !logContainerRef.value) return
  nextTick(() => {
    if (logContainerRef.value) {
      logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
    }
  })
}

// 탭 또는 로그 배열 변경 시 스크롤
watch(
  () => activeTab.value === 'kr' ? logStore.krLogs.length : logStore.usLogs.length,
  () => {
    scrollToBottom()
  }
)

// 자동 웹소켓 연결
onMounted(() => {
  logStore.connectLogs('kr')
  logStore.connectLogs('us')
})

onUnmounted(() => {
  logStore.disconnectLogs('kr')
  logStore.disconnectLogs('us')
})

const handleToggleConnect = (market: 'kr' | 'us') => {
  const status = market === 'kr' ? logStore.krWsStatus : logStore.usWsStatus
  if (status === 'CONNECTED' || status === 'CONNECTING') {
    logStore.disconnectLogs(market)
  } else {
    logStore.connectLogs(market)
  }
}

const getLogLevelClass = (log: string) => {
  if (log.includes('[ERROR]') || log.toLowerCase().includes('error') || log.includes('SYSTEM ERROR')) return 'log-error'
  if (log.includes('[WARNING]') || log.toLowerCase().includes('warning') || log.includes('WARN')) return 'log-warn'
  if (log.includes('[INFO]') || log.toLowerCase().includes('info')) return 'log-info'
  return 'log-debug'
}

const handleScroll = () => {
  if (!logContainerRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = logContainerRef.value
  // 스크롤바가 맨 아래에서 20px 이내에 위치하면 autoScroll 유지, 아니면 해제
  const isAtBottom = scrollHeight - scrollTop - clientHeight < 20
  autoScroll.value = isAtBottom
}
</script>

<template>
  <div class="log-terminal-container" :class="{ 'maximized': isMaximized }">
    <!-- 터미널 윈도우 헤더 -->
    <header class="terminal-header">
      <div class="header-left">
        <span class="dot red" @click="logStore.clearLogs(activeTab)"></span>
        <span class="dot yellow" @click="autoScroll = !autoScroll"></span>
        <span class="dot green" @click="isMaximized = !isMaximized"></span>
        <span class="title">📟 TDMS Realtime Output Stream ({{ activeTab.toUpperCase() }})</span>
      </div>
      
      <!-- 터미널 제어바 -->
      <div class="header-controls">
        <!-- 폰트 크기 토글 -->
        <div class="btn-group font-selector">
          <button :class="{ active: fontSize === 'sm' }" @click="fontSize = 'sm'">A-</button>
          <button :class="{ active: fontSize === 'md' }" @click="fontSize = 'md'">A</button>
          <button :class="{ active: fontSize === 'lg' }" @click="fontSize = 'lg'">A+</button>
        </div>

        <!-- 자동스크롤 고정 토글 -->
        <button class="control-btn" :class="{ active: autoScroll }" @click="autoScroll = !autoScroll">
          {{ autoScroll ? '🔒 Auto Scroll' : '🔓 Scroll Lock' }}
        </button>

        <!-- 버퍼 클리어 -->
        <button class="control-btn danger" @click="logStore.clearLogs(activeTab)">
          🗑️ Clear
        </button>
      </div>
    </header>

    <!-- 시장 탭 및 소켓 연결 제어바 -->
    <nav class="terminal-tabs-bar">
      <div class="tabs">
        <button 
          class="tab-btn" 
          :class="{ active: activeTab === 'kr' }" 
          @click="activeTab = 'kr'"
        >
          🇰🇷 KDMS (한국)
          <span 
            class="status-dot" 
            :class="logStore.krWsStatus.toLowerCase()"
          ></span>
        </button>
        <button 
          class="tab-btn" 
          :class="{ active: activeTab === 'us' }" 
          @click="activeTab = 'us'"
        >
          🇺🇸 USDMS (미국)
          <span 
            class="status-dot" 
            :class="logStore.usWsStatus.toLowerCase()"
          ></span>
        </button>
      </div>

      <div class="connection-status">
        <span class="status-label">Stream Status: </span>
        <span class="status-value" :class="activeTab === 'kr' ? logStore.krWsStatus.toLowerCase() : logStore.usWsStatus.toLowerCase()">
          {{ activeTab === 'kr' ? logStore.krWsStatus : logStore.usWsStatus }}
        </span>
        <button 
          class="conn-btn" 
          :class="(activeTab === 'kr' ? logStore.krWsStatus === 'CONNECTED' : logStore.usWsStatus === 'CONNECTED') ? 'disconnect' : 'connect'"
          @click="handleToggleConnect(activeTab)"
        >
          {{ (activeTab === 'kr' ? logStore.krWsStatus === 'CONNECTED' || logStore.krWsStatus === 'CONNECTING' : logStore.usWsStatus === 'CONNECTED' || logStore.usWsStatus === 'CONNECTING') ? 'Disconnect' : 'Connect' }}
        </button>
      </div>
    </nav>

    <!-- 터미널 본체 로그 리스트 -->
    <div 
      class="terminal-body" 
      ref="logContainerRef" 
      @scroll="handleScroll"
      :class="`size-${fontSize}`"
    >
      <div class="log-viewport">
        <!-- 로그 라인이 없는 경우 -->
        <div v-if="activeTab === 'kr' ? logStore.krLogs.length === 0 : logStore.usLogs.length === 0" class="empty-logs">
          <p class="console-prompt">$ waiting for upstream system logs...</p>
          <p class="console-sub">커넥션이 수립되면 로그가 스트리밍됩니다. (오프라인 상태 시 백엔드를 구동하세요)</p>
        </div>

        <!-- 로그 출력 -->
        <template v-else>
          <div 
            v-for="(log, idx) in (activeTab === 'kr' ? logStore.krLogs : logStore.usLogs)" 
            :key="idx" 
            class="log-line" 
            :class="getLogLevelClass(log)"
          >
            <span class="line-number">{{ idx + 1 }}</span>
            <span class="line-text">{{ log }}</span>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.log-terminal-container {
  background: #090d16;
  border-radius: 16px;
  border: 1px solid rgba(165, 180, 252, 0.15);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  height: 380px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.log-terminal-container.maximized {
  position: fixed;
  top: 1rem;
  left: 1rem;
  right: 1rem;
  bottom: 1rem;
  height: calc(100vh - 2rem) !important;
  z-index: 9999;
}

/* 터미널 헤더 */
.terminal-header {
  background: #111827;
  padding: 0.75rem 1.25rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  cursor: pointer;
  transition: transform 0.2s ease;
}

.dot:hover {
  transform: scale(1.2);
}

.dot.red { background: #ef4444; }
.dot.yellow { background: #eab308; }
.dot.green { background: #22c55e; }

.title {
  font-family: 'Fira Code', 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  color: #94a3b8;
  margin-left: 0.5rem;
  font-weight: 600;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.btn-group {
  display: flex;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 6px;
  padding: 2px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.btn-group button {
  background: transparent;
  border: none;
  color: #64748b;
  padding: 0.2rem 0.5rem;
  font-size: 0.75rem;
  font-weight: 700;
  border-radius: 4px;
  cursor: pointer;
}

.btn-group button.active {
  background: rgba(165, 180, 252, 0.2);
  color: #a5b4fc;
}

.control-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #94a3b8;
  font-size: 0.75rem;
  padding: 0.25rem 0.6rem;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-weight: 600;
}

.control-btn.active {
  background: rgba(99, 102, 241, 0.2);
  color: #a5b4fc;
  border-color: rgba(99, 102, 241, 0.4);
}

.control-btn.danger:hover {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
  border-color: rgba(239, 68, 68, 0.3);
}

/* 탭바 */
.terminal-tabs-bar {
  background: #0f172a;
  padding: 0.5rem 1.25rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.tabs {
  display: flex;
  gap: 0.5rem;
}

.tab-btn {
  background: transparent;
  border: none;
  color: #64748b;
  font-size: 0.85rem;
  font-weight: 700;
  padding: 0.35rem 0.75rem;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  transition: all 0.2s ease;
}

.tab-btn:hover {
  color: #94a3b8;
  background: rgba(255, 255, 255, 0.02);
}

.tab-btn.active {
  color: #f8fafc;
  background: rgba(255, 255, 255, 0.05);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.status-dot.connected {
  background-color: var(--color-emerald);
  box-shadow: 0 0 6px var(--color-emerald);
  animation: pulse-dot 1.5s infinite;
}

.status-dot.connecting {
  background-color: var(--color-amber);
  animation: pulse-dot 1s infinite;
}

.status-dot.disconnected {
  background-color: #64748b;
}

@keyframes pulse-dot {
  0% { opacity: 0.6; }
  50% { opacity: 1; }
  100% { opacity: 0.6; }
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
}

.status-label {
  color: #64748b;
}

.status-value {
  font-weight: 800;
}

.status-value.connected { color: var(--color-emerald); }
.status-value.connecting { color: var(--color-amber); }
.status-value.disconnected { color: #64748b; }

.conn-btn {
  border: none;
  font-size: 0.7rem;
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 800;
  margin-left: 0.5rem;
  transition: all 0.2s ease;
}

.conn-btn.connect {
  background: var(--color-emerald);
  color: #0f172a;
}

.conn-btn.disconnect {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

/* 터미널 바디 */
.terminal-body {
  flex: 1;
  overflow-y: auto;
  padding: 1rem 1.25rem;
  font-family: 'Fira Code', 'JetBrains Mono', monospace;
  scroll-behavior: smooth;
}

/* 폰트사이즈 */
.terminal-body.size-sm { font-size: 0.75rem; line-height: 1.25; }
.terminal-body.size-md { font-size: 0.85rem; line-height: 1.4; }
.terminal-body.size-lg { font-size: 0.95rem; line-height: 1.5; }

.log-viewport {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.empty-logs {
  color: #475569;
  padding: 2rem 0;
  text-align: center;
}

.console-prompt {
  color: var(--color-indigo);
  font-weight: 700;
}

.console-sub {
  font-size: 0.75rem;
  color: #475569;
  margin-top: 0.5rem;
}

.log-line {
  display: flex;
  gap: 1rem;
  white-space: pre-wrap;
  word-break: break-all;
}

.line-number {
  color: #334155;
  user-select: none;
  text-align: right;
  min-width: 2.5rem;
}

.line-text {
  flex: 1;
}

/* 로그 레벨 색상 분기 */
.log-error .line-text {
  color: #f87171;
  font-weight: 600;
  background: rgba(239, 68, 68, 0.05);
}

.log-warn .line-text {
  color: #fbbf24;
}

.log-info .line-text {
  color: #e2e8f0;
}

.log-debug .line-text {
  color: #64748b;
}
</style>
