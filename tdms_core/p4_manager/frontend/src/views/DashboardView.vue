<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useStatusStore } from '@/stores/statusStore'
import TaskStatusCard from '@/components/dashboard/TaskStatusCard.vue'
import LogTerminal from '@/components/dashboard/LogTerminal.vue'
import ScheduleView from '@/views/ScheduleView.vue'
import HealthView from '@/views/HealthView.vue'

const statusStore = useStatusStore()
const activeTab = ref<'dashboard' | 'schedules' | 'health'>('dashboard')

// 2초 주기 상태 폴링
let pollInterval: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await statusStore.fetchStatus()
  pollInterval = setInterval(() => {
    statusStore.fetchStatus()
  }, 2000)
})

onUnmounted(() => {
  if (pollInterval) {
    clearInterval(pollInterval)
  }
})
</script>

<template>
  <div class="dashboard-container">
    <!-- 대시보드 상단 타이틀 -->
    <header class="dashboard-header">
      <div class="header-main-row">
        <div class="logo-area">
          <span class="neon-dot"></span>
          <h1>TDMS Integrated Manager</h1>
        </div>
        
        <!-- 대시보드 메인 내비게이션 탭 -->
        <nav class="main-navigation">
          <button 
            class="nav-tab-btn" 
            :class="{ active: activeTab === 'dashboard' }" 
            @click="activeTab = 'dashboard'"
          >
            📊 모니터링 보드
          </button>
          <button 
            class="nav-tab-btn" 
            :class="{ active: activeTab === 'schedules' }" 
            @click="activeTab = 'schedules'"
          >
            📅 스케줄 및 크론
          </button>
          <button 
            class="nav-tab-btn" 
            :class="{ active: activeTab === 'health' }" 
            @click="activeTab = 'health'"
          >
            🏥 데이터 헬스 모니터
          </button>
        </nav>
      </div>
      <p class="subtitle">글로벌 금융 데이터 수집 및 적재 시스템 모니터링</p>
    </header>

    <!-- 1. 모니터링 대시보드 탭 콘텐츠 -->
    <div v-if="activeTab === 'dashboard'" class="tab-content-wrapper">
      <!-- 통합 게이트웨이 / 시장 헬스 보드 -->
      <section class="health-board">
        <!-- 한국 시장(KDMS) -->
        <div class="health-card" :class="statusStore.status.kr.status.toLowerCase()">
          <div class="health-info">
            <div class="market-tag">
              <span class="flag">🇰🇷</span>
              <span>한국 시장 (KDMS)</span>
            </div>
            <div class="status-indicator">
              <span class="pulse-dot"></span>
              <span class="status-text">{{ statusStore.status.kr.status }}</span>
            </div>
          </div>
          <div class="freshness-details" v-if="statusStore.status.kr.freshness">
            <div class="metric">
              <span class="m-label">최종 수집일</span>
              <span class="m-value">{{ statusStore.status.kr.freshness.latest_trading_date || '-' }}</span>
            </div>
            <div class="metric">
              <span class="m-label">수집 완료율</span>
              <span class="m-value">{{ (statusStore.status.kr.freshness.daily_coverage_ratio * 100).toFixed(1) }}%</span>
            </div>
            <div class="metric">
              <span class="m-label">신선도 상태</span>
              <span class="status-badge" :style="{ backgroundColor: statusStore.status.kr.freshness.status === 'GREEN' ? 'var(--color-emerald)' : 'var(--color-amber)' }">
                {{ statusStore.status.kr.freshness.status }}
              </span>
            </div>
          </div>
          <div class="offline-placeholder" v-else>
            <span>대상 백엔드가 오프라인 상태이거나 정보를 가져올 수 없습니다.</span>
          </div>
        </div>

        <!-- 미국 시장(USDMS) -->
        <div class="health-card" :class="statusStore.status.us.status.toLowerCase()">
          <div class="health-info">
            <div class="market-tag">
              <span class="flag">🇺🇸</span>
              <span>미국 시장 (USDMS)</span>
            </div>
            <div class="status-indicator">
              <span class="pulse-dot"></span>
              <span class="status-text">{{ statusStore.status.us.status }}</span>
            </div>
          </div>
          <div class="freshness-details" v-if="statusStore.status.us.freshness">
            <div class="metric">
              <span class="m-label">최종 수집일</span>
              <span class="m-value">{{ statusStore.status.us.freshness.latest_trading_date || '-' }}</span>
            </div>
            <div class="metric">
              <span class="m-label">수집 완료율</span>
              <span class="m-value">{{ (statusStore.status.us.freshness.daily_coverage_ratio * 100).toFixed(1) }}%</span>
            </div>
            <div class="metric">
              <span class="m-label">신선도 상태</span>
              <span class="status-badge" :style="{ backgroundColor: statusStore.status.us.freshness.status === 'GREEN' ? 'var(--color-emerald)' : 'var(--color-amber)' }">
                {{ statusStore.status.us.freshness.status }}
              </span>
            </div>
          </div>
          <div class="offline-placeholder" v-else>
            <span>대상 백엔드가 오프라인 상태이거나 정보를 가져올 수 없습니다.</span>
          </div>
        </div>
      </section>

      <!-- 수집 태스크 제어 섹션 -->
      <main class="tasks-section">
        <div class="section-title">
          <h2>⚡ 실시간 태스크 제어 및 수동 기동</h2>
          <div class="divider"></div>
        </div>

        <div class="tasks-grid">
          <!-- 한국: 일일 수집 -->
          <TaskStatusCard 
            market="kr"
            taskId="daily_update"
            title="일일 업데이트"
            icon="📅"
            :status="statusStore.status.kr.tasks"
          />

          <!-- 한국: 재무 제표 -->
          <TaskStatusCard 
            market="kr"
            taskId="financial_update"
            title="재무 업데이트"
            icon="💵"
            :status="statusStore.status.kr.tasks"
          />

          <!-- 미국: 일일 Routine -->
          <TaskStatusCard 
            market="us"
            taskId="daily_routine"
            title="Daily Routine"
            icon="🇺🇸"
            :status="statusStore.status.us.tasks"
          />

          <!-- 미국: 주간 Backfill -->
          <TaskStatusCard 
            market="us"
            taskId="weekly_backfill"
            title="Weekly Backfill"
            icon="⏳"
            :status="statusStore.status.us.tasks"
          />
        </div>
      </main>

      <!-- 실시간 로그 모니터링 섹션 -->
      <section class="log-monitor-wrapper">
        <div class="section-title">
          <h2>📊 실시간 로그 스트리밍 (Output Stream)</h2>
          <div class="divider"></div>
        </div>
        <LogTerminal />
      </section>
    </div>

    <!-- 2. 스케줄 오케스트레이션 탭 콘텐츠 -->
    <div v-if="activeTab === 'schedules'" class="tab-content-wrapper">
      <ScheduleView />
    </div>

    <!-- 3. 데이터 헬스 모니터 탭 콘텐츠 -->
    <div v-else-if="activeTab === 'health'" class="tab-content-wrapper">
      <HealthView />
    </div>
  </div>
</template>


<style scoped>
.dashboard-container {
  max-width: 1280px;
  margin: 0 auto;
  padding: 2.5rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 2.5rem;
}

.header-main-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
}

.main-navigation {
  display: flex;
  gap: 0.75rem;
}

.nav-tab-btn {
  background: rgba(30, 41, 59, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  color: #94a3b8;
  padding: 8px 16px;
  font-size: 0.95rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.nav-tab-btn:hover {
  background: rgba(30, 41, 59, 0.7);
  color: #f1f5f9;
}

.nav-tab-btn.active {
  background: rgba(99, 102, 241, 0.15);
  border-color: rgba(99, 102, 241, 0.35);
  color: #a5b4fc;
}

.dashboard-header {
  text-align: left;
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.neon-dot {
  width: 12px;
  height: 12px;
  background-color: var(--color-indigo);
  border-radius: 50%;
  box-shadow: 0 0 12px var(--color-indigo);
  display: inline-block;
}

.dashboard-header h1 {
  font-size: 2.25rem;
  margin: 0;
  font-weight: 800;
  background: linear-gradient(135deg, #f8fafc 30%, #a5b4fc 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.subtitle {
  color: #94a3b8;
  margin: 0.5rem 0 0 0;
  font-size: 1rem;
}

/* 헬스 보드 */
.health-board {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.5rem;
}

.health-card {
  background: rgba(30, 41, 59, 0.4);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  transition: all 0.3s ease;
}

.health-card.online {
  border-left: 4px solid var(--color-emerald);
}

.health-card.offline {
  border-left: 4px solid var(--color-rose);
  opacity: 0.8;
}

.health-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.market-tag {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 700;
  font-size: 1.1rem;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 800;
  font-size: 0.85rem;
}

.online .status-indicator {
  color: var(--color-emerald);
}

.online .pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--color-emerald);
  box-shadow: 0 0 8px var(--color-emerald);
  animation: pulse 2s infinite;
}

.offline .status-indicator {
  color: var(--color-rose);
}

.offline .pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--color-rose);
  box-shadow: 0 0 8px var(--color-rose);
}

@keyframes pulse {
  0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
  70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
  100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
}

.freshness-details {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  background: rgba(15, 23, 42, 0.3);
  padding: 1rem;
  border-radius: 12px;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  align-items: center;
}

.m-label {
  font-size: 0.75rem;
  color: #94a3b8;
}

.m-value {
  font-size: 0.95rem;
  font-weight: 700;
  color: #f8fafc;
}

.status-badge {
  padding: 0.1rem 0.5rem;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 800;
}

.offline-placeholder {
  color: #64748b;
  font-size: 0.85rem;
  padding: 1rem;
  text-align: center;
  background: rgba(15, 23, 42, 0.1);
  border-radius: 12px;
}

/* 태스크 제어 섹션 */
.tasks-section {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.section-title h2 {
  font-size: 1.25rem;
  margin: 0;
  color: #f1f5f9;
  font-weight: 700;
}

.divider {
  height: 2px;
  background: linear-gradient(90deg, var(--color-indigo) 0%, transparent 100%);
  margin-top: 0.5rem;
  border-radius: 9999px;
}

.tasks-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.5rem;
}
</style>
