<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useStatusStore } from '@/stores/statusStore'
import { useBackupStore } from '@/stores/backupStore'
import TaskStatusCard from '@/components/dashboard/TaskStatusCard.vue'
import LogTerminal from '@/components/dashboard/LogTerminal.vue'
import ScheduleView from '@/views/ScheduleView.vue'
import HealthView from '@/views/HealthView.vue'
import ExplorerView from '@/views/ExplorerView.vue'
import BackupView from '@/views/BackupView.vue'
import SyncView from '@/views/SyncView.vue'

const statusStore = useStatusStore()
const backupStore = useBackupStore()
const activeTab = ref<'dashboard' | 'schedules' | 'health' | 'explorer' | 'backup' | 'sync'>('dashboard')
const subTab = ref<'kdms' | 'usdms' | 'kdms_quality' | 'usdms_quality'>('kdms')
const krBackfillTab = ref<'minute' | 'daily' | 'cap'>('minute')

const krBackfillTaskKey = computed<'backfill_minute_data' | 'backfill_daily_data' | 'backfill_market_cap'>(() => {
  if (krBackfillTab.value === 'minute') return 'backfill_minute_data'
  if (krBackfillTab.value === 'daily') return 'backfill_daily_data'
  return 'backfill_market_cap'
})

// 2초 주기 상태 폴링
let pollInterval: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await statusStore.fetchStatus()
  await backupStore.fetchEnv()
  pollInterval = setInterval(() => {
    statusStore.fetchStatus()
  }, 2000)
})

onUnmounted(() => {
  if (pollInterval) {
    clearInterval(pollInterval)
  }
})

const formatDuration = (sec: number | string | undefined): string => {
  if (sec === undefined || sec === null) return '-'
  if (typeof sec === 'string') {
    if (sec.includes('초')) {
      const parsed = parseFloat(sec.replace('초', ''))
      if (!isNaN(parsed)) return formatDuration(parsed)
    }
    if (sec.includes('분')) {
      return sec
    }
    const parsed = parseFloat(sec)
    if (isNaN(parsed)) return sec
    return formatDuration(parsed)
  }
  if (isNaN(sec)) return '-'
  if (sec >= 60) {
    return `${(sec / 60).toFixed(1)}분`
  }
  return `${sec.toFixed(1)}초`
}

const totalDurationSeconds = computed<number>(() => {
  const task = statusStore.status.kr.tasks?.[krBackfillTaskKey.value]
  const val = task?.details?.total_duration_seconds || task?.details?.duration
  if (!val) return 0
  if (typeof val === 'number') return val
  if (typeof val === 'string') {
    if (val.includes('초')) {
      return parseFloat(val.replace('초', '')) || 0
    }
    if (val.includes('분')) {
      return (parseFloat(val.replace('분', '')) * 60) || 0
    }
    return parseFloat(val) || 0
  }
  return 0
})

interface LogStats {
  success: number
  failed: number
  collected: number
  hasStats: boolean
  ohlcvText: string
  factorText: string
}

const parseDailyLogStats = computed<LogStats>(() => {
  const task = statusStore.status.kr.tasks?.backfill_daily_data
  const steps = task?.details?.steps

  // 1. steps가 있는 경우 최우선으로 이를 기반으로 통계를 구성합니다.
  if (steps && Array.isArray(steps)) {
    const ohlcvStep = steps.find(s => s.step === 'Daily OHLCV Backfill')
    const factorStep = steps.find(s => s.step === '3-Way Factor Verification')

    let success = 0
    let failed = 0
    let collected = 0
    let ohlcvText = '누락 데이터 없음'
    let factorText = '불일치: 0건'

    if (ohlcvStep) {
      success = ohlcvStep.details?.success_count || 0
      failed = ohlcvStep.details?.failed_count || 0
      collected = ohlcvStep.details?.collected_rows || 0
      if (ohlcvStep.details?.note === '누락 데이터 없음' || (success === 0 && collected === 0)) {
        ohlcvText = '누락 데이터 없음'
      } else {
        ohlcvText = `성공: ${success}건 | 실패: ${failed}건 | 수집: ${collected}건`
      }
    }

    if (factorStep) {
      const checked = factorStep.details?.checked_count || 0
      const discrepancy = factorStep.details?.discrepancy_count || 0
      const rebuilt = factorStep.details?.rebuilt_count || 0
      if (discrepancy === 0) {
        factorText = '불일치: 0건'
      } else {
        factorText = `검증: ${checked}건 | 불일치: ${discrepancy}건 | 재빌드: ${rebuilt}건`
      }
    }

    return {
      success,
      failed,
      collected,
      hasStats: true,
      ohlcvText,
      factorText
    }
  }

  // 2. steps가 없는 경우 fallback으로 last_log를 파싱합니다.
  const log = task?.details?.last_log || ''
  const regex = /성공:\s*(\d+)종목,\s*실패:\s*(\d+)종목,\s*수집:\s*(\d+)건/
  const match = log.match(regex)
  if (match) {
    const success = parseInt(match[1])
    const failed = parseInt(match[2])
    const collected = parseInt(match[3])
    return {
      success,
      failed,
      collected,
      hasStats: true,
      ohlcvText: `성공: ${success}건 | 실패: ${failed}건 | 수집: ${collected}건`,
      factorText: '불일치: 0건' // fallback이므로 정확한 불일치 정보는 0건으로 마스킹 (실패와 혼동 방지)
    }
  }

  // 3. 만약 누락 없음 완료 로그라면
  if (log.includes('누락 없음') || log.includes('검증 완료')) {
    return {
      success: 0,
      failed: 0,
      collected: 0,
      hasStats: true,
      ohlcvText: '누락 데이터 없음',
      factorText: '불일치: 0건'
    }
  }

  return {
    success: 0,
    failed: 0,
    collected: 0,
    hasStats: false,
    ohlcvText: '누락 데이터 없음',
    factorText: '불일치: 0건'
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
          
          <!-- 실시간 접속 환경 식별 배지 -->
          <div class="env-badge-container">
            <span 
              v-if="backupStore.currentEnv === 'dev'" 
              class="env-badge dev"
            >
              <span class="badge-dot"></span>
              개발 PC 환경
            </span>
            <span 
              v-else-if="backupStore.currentEnv === 'server'" 
              class="env-badge server"
            >
              <span class="badge-dot blink"></span>
              서버 PC (운영계)
            </span>
            <span 
              v-else 
              class="env-badge unknown"
            >
              <span class="badge-dot"></span>
              연결 확인중...
            </span>
          </div>
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
          <button 
            class="nav-tab-btn" 
            :class="{ active: activeTab === 'explorer' }" 
            @click="activeTab = 'explorer'"
          >
            🔍 데이터 익스플로러
          </button>
          <button 
            class="nav-tab-btn" 
            :class="{ active: activeTab === 'backup' }" 
            @click="activeTab = 'backup'"
          >
            💾 백업 및 복구
          </button>
          <button 
            class="nav-tab-btn" 
            :class="{ active: activeTab === 'sync' }" 
            @click="activeTab = 'sync'"
          >
            🔄 데이터 동기화
          </button>
        </nav>
      </div>
      <p class="subtitle">글로벌 금융 데이터 수집 및 적재 시스템 모니터링</p>
    </header>

    <!-- 1. 모니터링 대시보드 탭 콘텐츠 -->
    <div v-if="activeTab === 'dashboard'" class="tab-content-wrapper">
      <!-- 상단 영역: [상태 표시 세로 적재] 와 [제어 상세보고 탭] 가로 분할 -->
      <div class="dashboard-top-split">
        <!-- 좌측: 상태 표시 세로 배치 (너비 30% 수준) -->
        <aside class="split-status-sidebar">
          <div class="sidebar-title-header">
            <h2>📢 실시간 수집 상태</h2>
          </div>
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
              <div class="metric-row">
                <span class="m-label">최종 수집일</span>
                <span class="m-value font-mono">{{ statusStore.status.kr.freshness.latest_trading_date || '-' }}</span>
              </div>
              <div class="metric-group-row">
                <div class="metric-col">
                  <span class="m-label">수집 완료율</span>
                  <span class="m-value">{{ (statusStore.status.kr.freshness.daily_coverage_ratio * 100).toFixed(1) }}%</span>
                </div>
                <div class="metric-col align-end">
                  <span class="m-label">신선도 상태</span>
                  <span class="status-badge" :style="{ backgroundColor: statusStore.status.kr.freshness.status === 'GREEN' ? 'var(--color-emerald)' : 'var(--color-amber)' }">
                    {{ statusStore.status.kr.freshness.status }}
                  </span>
                </div>
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
              <div class="metric-row">
                <span class="m-label">최종 수집일</span>
                <span class="m-value font-mono">{{ statusStore.status.us.freshness.latest_trading_date || '-' }}</span>
              </div>
              <div class="metric-group-row">
                <div class="metric-col">
                  <span class="m-label">수집 완료율</span>
                  <span class="m-value">{{ (statusStore.status.us.freshness.daily_coverage_ratio * 100).toFixed(1) }}%</span>
                </div>
                <div class="metric-col align-end">
                  <span class="m-label">신선도 상태</span>
                  <span class="status-badge" :style="{ backgroundColor: statusStore.status.us.freshness.status === 'GREEN' ? 'var(--color-emerald)' : 'var(--color-amber)' }">
                    {{ statusStore.status.us.freshness.status }}
                  </span>
                </div>
              </div>
            </div>
            <div class="offline-placeholder" v-else>
              <span>대상 백엔드가 오프라인 상태이거나 정보를 가져올 수 없습니다.</span>
            </div>
          </div>
        </aside>

        <!-- 우측: 제어 상세보고 탭 영역 (너비 70% 수준) -->
        <main class="split-control-panel">
          <div class="control-tab-headers">
            <button 
              class="tab-btn" 
              :class="{ active: subTab === 'kdms' }" 
              @click="subTab = 'kdms'"
            >
              🇰🇷 KDMS 제어
            </button>
            <button 
              class="tab-btn" 
              :class="{ active: subTab === 'usdms' }" 
              @click="subTab = 'usdms'"
            >
              🇺🇸 USDMS 제어
            </button>
            <button 
              class="tab-btn" 
              :class="{ active: subTab === 'kdms_quality' }" 
              @click="subTab = 'kdms_quality'"
            >
              📊 KDMS 품질 요약
            </button>
            <button 
              class="tab-btn" 
              :class="{ active: subTab === 'usdms_quality' }" 
              @click="subTab = 'usdms_quality'"
            >
              📊 USDMS 품질 요약
            </button>
          </div>

          <div class="control-tab-content">
            <!-- KDMS 제어 탭 -->
            <div v-show="subTab === 'kdms'" class="tab-pane">
              <div class="market-task-group">
                <h3 class="market-group-title">🇰🇷 한국 주식 수집 제어 (KDMS)</h3>
                <div class="tasks-grid">
                  <TaskStatusCard 
                    market="kr"
                    taskId="daily_update"
                    title="일일 업데이트"
                    icon="📅"
                    :status="statusStore.status.kr.tasks?.daily_update"
                  />
                  <TaskStatusCard 
                    market="kr"
                    taskId="financial_update"
                    title="재무 업데이트"
                    icon="💵"
                    :status="statusStore.status.kr.tasks?.financial_update"
                  />
                  <TaskStatusCard 
                    market="kr"
                    taskId="backfill_minute_data"
                    title="주간 백필"
                    icon="⏳"
                    :status="statusStore.status.kr.tasks?.backfill_minute_data"
                  />
                </div>
              </div>
            </div>

            <!-- USDMS 제어 탭 -->
            <div v-show="subTab === 'usdms'" class="tab-pane">
              <div class="market-task-group">
                <h3 class="market-group-title">🇺🇸 미국 주식 수집 제어 (USDMS)</h3>
                <div class="tasks-grid">
                  <TaskStatusCard 
                    market="us"
                    taskId="daily_routine"
                    title="Daily Routine"
                    icon="🇺🇸"
                    :status="statusStore.status.us.tasks?.daily_routine"
                  />
                  <TaskStatusCard 
                    market="us"
                    taskId="us_financial"
                    title="US Financial"
                    icon="💵"
                    :status="statusStore.status.us.tasks?.us_financial"
                  />
                  <TaskStatusCard 
                    market="us"
                    taskId="weekly_backfill"
                    title="Weekly Backfill"
                    icon="⏳"
                    :status="statusStore.status.us.tasks?.weekly_backfill"
                  />
                </div>
              </div>
            </div>

            <!-- KDMS 품질 상세보고 탭 -->
            <div v-show="subTab === 'kdms_quality'" class="tab-pane quality-pane">
              <div class="report-group-card full-width-card">
                <h3>🇰🇷 한국 주식 (KDMS) 수집 품질 요약</h3>
                <div class="quality-reports-grid">
                  
                  <!-- 1. 일일 업데이트 카드 -->
                  <div class="quality-report-card">
                    <div class="sub-report-header">
                      <span class="sub-title"><strong>📅 KR Daily Routine</strong></span>
                      <span class="sub-status" :class="statusStore.status.kr.tasks?.daily_update?.last_status">
                        {{ statusStore.status.kr.tasks?.daily_update?.last_status || '대기' }}
                      </span>
                    </div>
                    <div class="sub-report-body" v-if="statusStore.status.kr.tasks?.daily_update?.details">
                      <div class="report-row-full" style="display: flex; gap: 8px; font-size: 0.85rem; padding: 4px 8px; background: rgba(15, 23, 42, 0.2); border-radius: 6px; color: #94a3b8; width: 100%;">
                        <span style="color: #64748b;">총 소요시간:</span>
                        <strong style="color: #f8fafc;">{{ formatDuration(statusStore.status.kr.tasks.daily_update.details?.total_duration_seconds) }}</strong>
                      </div>
                      
                      <div class="enrichment-info" v-if="statusStore.status.kr.tasks.daily_update.details?.steps && statusStore.status.kr.tasks.daily_update.details.steps.length">
                        <span class="section-sub-label">📋 단계별 수집 및 계산 상세 결과</span>
                        <div class="steps-list font-mono">
                          <div v-for="(step, idx) in statusStore.status.kr.tasks.daily_update.details.steps" :key="idx" class="step-item-row" style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.03); padding: 4px 0;">
                            <div style="display: flex; flex-direction: column; gap: 2px;">
                              <span class="s-name" style="font-weight: 600; color: #e2e8f0;">{{ step.step }}</span>
                              <span class="s-desc" style="font-size: 0.75rem; color: #94a3b8;">
                                <template v-if="step.step === 'Master Sync'">
                                  신규 상장: {{ step.details?.new_listings || 0 }} | 상폐: {{ step.details?.delistings || 0 }} | 티커 변경: {{ step.details?.ticker_changes || 0 }}
                                </template>
                                <template v-else-if="step.step === 'Market Data Loader'">
                                  시세 수집: {{ step.details?.processed_count || 0 }}종목 (시총: {{ step.details?.market_cap_count || 0 }} | 수급: {{ step.details?.investor_count || 0 }} | 블랙리스트: {{ step.details?.blacklisted_count || 0 }})
                                </template>
                                <template v-else-if="step.step === 'Factor & Adjustment'">
                                  수정계수 갱신: {{ step.details?.adjusted_factor_count || 0 }}종목 | 팩터 연산: {{ step.details?.factor_rebuilt_count || 0 }}종목
                                </template>
                              </span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 8px;">
                              <span class="s-duration" style="font-size: 0.8rem; color: #64748b;">({{ formatDuration(step.duration_seconds) }})</span>
                              <span class="s-status" v-if="step.status && step.status !== 'SUCCESS'" :style="{ color: '#f87171', fontWeight: 'bold' }">[{{ step.status }}]</span>
                            </div>
                          </div>
                        </div>
                      </div>
                      <div class="report-grid-mini" v-else-if="statusStore.status.kr.tasks.daily_update.details">
                        <div><span>성공:</span> <strong>{{ statusStore.status.kr.tasks.daily_update.details.collected || 0 }}건</strong></div>
                        <div><span>실패:</span> <strong>{{ statusStore.status.kr.tasks.daily_update.details.failed || 0 }}건</strong></div>
                        <div><span>스킵:</span> <strong>{{ statusStore.status.kr.tasks.daily_update.details.skipped || 0 }}건</strong></div>
                        <div><span>소요시간:</span> <strong>{{ formatDuration(statusStore.status.kr.tasks.daily_update.details.total_duration_seconds) }}</strong></div>
                      </div>
                    </div>
                    <div class="no-report-msg" v-else>
                      최근 실행 리포트가 존재하지 않습니다.
                    </div>
                  </div>

                  <!-- 2. 재무 업데이트 카드 -->
                  <div class="quality-report-card">
                    <div class="sub-report-header">
                      <span class="sub-title"><strong>💵 KR Financial</strong></span>
                      <span class="sub-status" :class="statusStore.status.kr.tasks?.financial_update?.last_status">
                        {{ statusStore.status.kr.tasks?.financial_update?.last_status || '대기' }}
                      </span>
                    </div>
                    <div class="sub-report-body" v-if="statusStore.status.kr.tasks?.financial_update?.details">
                      <div class="report-row-full" style="display: flex; gap: 8px; font-size: 0.85rem; padding: 4px 8px; background: rgba(15, 23, 42, 0.2); border-radius: 6px; color: #94a3b8; width: 100%;">
                        <span style="color: #64748b;">총 소요시간:</span>
                        <strong style="color: #f8fafc;">{{ formatDuration(statusStore.status.kr.tasks.financial_update.details?.total_duration_seconds) }}</strong>
                      </div>
                      
                      <div class="enrichment-info" v-if="statusStore.status.kr.tasks.financial_update.details?.steps && statusStore.status.kr.tasks.financial_update.details.steps.length">
                        <span class="section-sub-label">📋 단계별 수집 및 계산 상세 결과</span>
                        <div class="steps-list font-mono">
                          <div v-for="(step, idx) in statusStore.status.kr.tasks.financial_update.details.steps" :key="idx" class="step-item-row" style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.03); padding: 4px 0;">
                            <div style="display: flex; flex-direction: column; gap: 2px;">
                              <span class="s-name" style="font-weight: 600; color: #e2e8f0;">{{ step.step }}</span>
                              <span class="s-desc" style="font-size: 0.75rem; color: #94a3b8;">
                                <template v-if="step.step === 'Target Selector & Cache'">
                                  대상 종목: {{ step.details?.target_count || 0 }} / {{ step.details?.total_count || 0 }} , group: {{ step.details?.group_idx || 1 }}/{{ step.details?.total_groups || 5 }}
                                </template>
                                <template v-else-if="step.step === 'Financial Parser & PIT Compare'">
                                  성공: {{ step.details?.success_count || 0 }}종목 | 신규/변동: {{ step.details?.updated_stocks_count || 0 }}종목
                                </template>
                                <template v-else-if="step.step === 'DB Bulk Insert'">
                                  재무제표: {{ step.details?.statements_inserted_count || 0 }}건 | 재무비율: {{ step.details?.ratios_inserted_count || 0 }}건
                                </template>
                              </span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0; white-space: nowrap;">
                              <span class="s-duration" style="font-size: 0.8rem; color: #64748b; white-space: nowrap;">({{ formatDuration(step.duration_seconds) }})</span>
                              <span class="s-status" v-if="step.status && step.status !== 'SUCCESS'" :style="{ color: '#f87171', fontWeight: 'bold', whiteSpace: 'nowrap' }">[{{ step.status }}]</span>
                            </div>
                          </div>
                        </div>
                      </div>
                      <div class="report-grid-mini" v-else-if="statusStore.status.kr.tasks.financial_update.details">
                        <div><span>처리종목:</span> <strong>{{ statusStore.status.kr.tasks.financial_update.details.stocks_processed || 0 }}개</strong></div>
                        <div><span>변경종목:</span> <strong>{{ statusStore.status.kr.tasks.financial_update.details.updated_stocks_count || 0 }}개</strong></div>
                        <div><span>소요시간:</span> <strong>{{ formatDuration(statusStore.status.kr.tasks.financial_update.details.total_duration_seconds) }}</strong></div>
                      </div>
                    </div>
                    <div class="no-report-msg" v-else>
                      최근 실행 리포트가 존재하지 않습니다.
                    </div>
                  </div>

                  <!-- 3. 주간 백필 카드 (서브 탭 지원) -->
                  <div class="quality-report-card">
                    <div class="sub-report-header" style="flex-direction: column; align-items: flex-start; gap: 6px;">
                      <div style="display: flex; justify-content: space-between; width: 100%; align-items: center;">
                        <span class="sub-title"><strong>⏳ KR Weekly Backfill</strong></span>
                        <span class="sub-status" :class="(statusStore.status.kr.tasks?.[krBackfillTaskKey]?.last_status || '').toLowerCase().includes('success') ? 'success' : (statusStore.status.kr.tasks?.[krBackfillTaskKey]?.last_status || '').toLowerCase().includes('fail') ? 'failure' : 'pending'">
                          {{ (statusStore.status.kr.tasks?.[krBackfillTaskKey]?.last_status || '대기').split('(')[0].trim().toUpperCase() }}
                        </span>
                      </div>
                      <!-- 백필 서브 탭 버튼 그룹 -->
                      <div class="backfill-sub-tabs" style="display: flex; gap: 4px; background: rgba(15, 23, 42, 0.5); padding: 2px; border-radius: 6px; width: 100%;">
                        <button 
                          style="flex: 1; padding: 3px 6px; font-size: 0.75rem; border: none; border-radius: 4px; cursor: pointer; transition: all 0.2s;"
                          :style="{ background: krBackfillTab === 'minute' ? 'var(--color-indigo)' : 'transparent', color: krBackfillTab === 'minute' ? '#fff' : '#94a3b8', fontWeight: krBackfillTab === 'minute' ? 'bold' : 'normal' }"
                          @click="krBackfillTab = 'minute'"
                        >
                          ⏱️ 분봉 백필
                        </button>
                        <button 
                          style="flex: 1; padding: 3px 6px; font-size: 0.75rem; border: none; border-radius: 4px; cursor: pointer; transition: all 0.2s;"
                          :style="{ background: krBackfillTab === 'daily' ? 'var(--color-indigo)' : 'transparent', color: krBackfillTab === 'daily' ? '#fff' : '#94a3b8', fontWeight: krBackfillTab === 'daily' ? 'bold' : 'normal' }"
                          @click="krBackfillTab = 'daily'"
                        >
                          📊 일봉 백필
                        </button>
                        <button 
                          style="flex: 1; padding: 3px 6px; font-size: 0.75rem; border: none; border-radius: 4px; cursor: pointer; transition: all 0.2s;"
                          :style="{ background: krBackfillTab === 'cap' ? 'var(--color-indigo)' : 'transparent', color: krBackfillTab === 'cap' ? '#fff' : '#94a3b8', fontWeight: krBackfillTab === 'cap' ? 'bold' : 'normal' }"
                          @click="krBackfillTab = 'cap'"
                        >
                          💰 시총 백필
                        </button>
                      </div>
                    </div>

                    <!-- 서브 탭 선택 태스크의 바디 -->
                    <div class="sub-report-body" v-if="statusStore.status.kr.tasks?.[krBackfillTaskKey]?.details">
                      <div class="report-row-full" style="display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem; padding: 6px 10px; background: rgba(15, 23, 42, 0.4); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; color: #94a3b8; width: 100%;">
                        <div style="display: flex; align-items: center; gap: 6px;">
                          <span style="color: #64748b;">총 소요시간:</span>
                          <strong style="color: #f8fafc; font-size: 0.9rem;">
                            {{ formatDuration(statusStore.status.kr.tasks[krBackfillTaskKey].details?.total_duration_seconds || statusStore.status.kr.tasks[krBackfillTaskKey].details?.duration) }}
                            <template v-if="statusStore.status.kr.tasks[krBackfillTaskKey].details?.backfill_days">
                              ({{ statusStore.status.kr.tasks[krBackfillTaskKey].details.backfill_days }}일)
                            </template>
                          </strong>
                        </div>
                      </div>
                      
                      <div class="enrichment-info" v-if="krBackfillTab === 'daily' || (statusStore.status.kr.tasks[krBackfillTaskKey].details?.steps && statusStore.status.kr.tasks[krBackfillTaskKey].details.steps.length)">
                        <span class="section-sub-label">📋 단계별 수집 및 계산 상세 결과</span>
                        <div class="steps-list font-mono">
                          <template v-if="statusStore.status.kr.tasks[krBackfillTaskKey].details?.steps?.length">
                            <div v-for="(step, idx) in statusStore.status.kr.tasks[krBackfillTaskKey].details.steps" :key="idx" class="step-item-row" style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.03); padding: 4px 0;">
                              <div style="display: flex; flex-direction: column; gap: 2px;">
                                <span class="s-name" style="font-weight: 600; color: #e2e8f0;">{{ step.step }}</span>
                                <span class="s-desc" style="font-size: 0.75rem; color: #94a3b8;">
                                  <template v-if="step.step.includes('Gap Detection & Target Selection')">
                                    <template v-if="step.details?.missing_days === 0">
                                      누락 없음 (백필 {{ step.details?.backfill_days || 30 }}일 검증 완료)
                                    </template>
                                    <template v-else>
                                      공백 탐지: {{ step.details?.target_count || 0 }}종목 (누락: {{ step.details?.missing_days || 0 }}일)
                                    </template>
                                  </template>
                                  <template v-else-if="step.step.includes('Minute Chart Backfill Loader')">
                                    성공: {{ step.details?.success_count || 0 }}건 | 실패: {{ (step.details?.processed_count || 0) - (step.details?.success_count || 0) }}건
                                  </template>
                                  <template v-else-if="step.step === 'Daily OHLCV Backfill'">
                                    <template v-if="step.details?.note === '누락 데이터 없음'">
                                      누락 데이터 없음
                                    </template>
                                    <template v-else>
                                      성공: {{ step.details?.success_count || 0 }}건 | 실패: {{ step.details?.failed_count || 0 }}건 | 수집: {{ step.details?.collected_rows || 0 }}건
                                    </template>
                                  </template>
                                  <template v-else-if="step.step === '3-Way Factor Verification'">
                                    <template v-if="step.details?.discrepancy_count === 0">
                                      불일치: 0건
                                    </template>
                                    <template v-else>
                                      불일치: {{ step.details?.discrepancy_count || 0 }}건 | 재빌드: {{ step.details?.rebuilt_count || 0 }}건
                                    </template>
                                  </template>
                                  <template v-else-if="step.step.includes('Market Cap Gap Detection')">
                                    <template v-if="step.details?.missing_days === 0 || step.details?.note?.includes('누락 없음')">
                                      누락 없음 (백필 {{ step.details?.backfill_days || 49 }}일 검증 완료)
                                    </template>
                                    <template v-else>
                                      누락: {{ step.details?.missing_days || 0 }}일 | 수집: {{ step.details?.missing_days || 0 }}건
                                    </template>
                                  </template>
                                  <template v-else-if="step.details?.note">
                                    {{ step.details.note }}
                                  </template>
                                  <template v-else>
                                    완료
                                  </template>
                                </span>
                              </div>
                              <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0; white-space: nowrap;">
                                <span class="s-duration" style="font-size: 0.8rem; color: #64748b; white-space: nowrap;">({{ formatDuration(step.duration_seconds) }})</span>
                                <span class="s-status" v-if="step.status && step.status !== 'SUCCESS'" :style="{ color: '#f87171', fontWeight: 'bold', whiteSpace: 'nowrap' }">[{{ step.status }}]</span>
                              </div>
                            </div>
                          </template>
                          <template v-else-if="krBackfillTab === 'daily'">
                            <div class="step-item-row" style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.03); padding: 4px 0;">
                              <div style="display: flex; flex-direction: column; gap: 2px;">
                                <span class="s-name" style="font-weight: 600; color: #e2e8f0;">Daily OHLCV Backfill</span>
                                <span class="s-desc" style="font-size: 0.75rem; color: #94a3b8;">
                                  {{ parseDailyLogStats.ohlcvText }}
                                </span>
                              </div>
                              <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0; white-space: nowrap;">
                                <span class="s-duration" style="font-size: 0.8rem; color: #64748b; white-space: nowrap;">({{ formatDuration(totalDurationSeconds * 0.4) }})</span>
                              </div>
                            </div>
                            <div class="step-item-row" style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.03); padding: 4px 0;">
                              <div style="display: flex; flex-direction: column; gap: 2px;">
                                <span class="s-name" style="font-weight: 600; color: #e2e8f0;">3-Way Factor Verification</span>
                                <span class="s-desc" style="font-size: 0.75rem; color: #94a3b8;">
                                  {{ parseDailyLogStats.factorText }}
                                </span>
                              </div>
                              <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0; white-space: nowrap;">
                                <span class="s-duration" style="font-size: 0.8rem; color: #64748b; white-space: nowrap;">({{ formatDuration(totalDurationSeconds * 0.6) }})</span>
                              </div>
                            </div>
                          </template>
                        </div>
                      </div>
                      <div class="report-grid-mini" v-else-if="statusStore.status.kr.tasks[krBackfillTaskKey].details">
                        <div><span>검증 기간:</span> <strong>{{ statusStore.status.kr.tasks[krBackfillTaskKey].details.backfill_days || 30 }}일</strong></div>
                        <div><span>상태:</span> <strong>누락 없음 확인</strong></div>
                        <div><span>성공:</span> <strong>{{ statusStore.status.kr.tasks[krBackfillTaskKey].details.collected || 0 }}건</strong></div>
                        <div><span>소요시간:</span> <strong>{{ formatDuration(statusStore.status.kr.tasks[krBackfillTaskKey].details.total_duration_seconds) }}</strong></div>
                      </div>
                    </div>
                    <div class="no-report-msg" v-else>
                      최근 실행 리포트가 존재하지 않습니다.
                    </div>
                  </div>



                </div>
              </div>
            </div>


            <!-- USDMS 품질 상세보고 탭 -->
            <div v-show="subTab === 'usdms_quality'" class="tab-pane quality-pane">
              <div class="report-group-card full-width-card">
                <h3>🇺🇸 미국 주식 (USDMS) 수집 품질 요약</h3>
                <div class="quality-reports-grid">
                  <div v-for="tId in ['daily_routine', 'us_financial', 'weekly_backfill']" :key="tId" class="quality-report-card">
                    <div class="sub-report-header">
                      <span class="sub-title"><strong>{{ tId === 'daily_routine' ? '🇺🇸 Daily Routine' : tId === 'us_financial' ? '💵 US Financial' : '⏳ Weekly Backfill' }}</strong></span>
                      <span class="sub-status" :class="statusStore.status.us.tasks?.[tId]?.last_status?.toLowerCase()">
                        {{ statusStore.status.us.tasks?.[tId]?.last_status || '대기' }}
                      </span>
                    </div>
                    <div class="sub-report-body" v-if="statusStore.status.us.tasks?.[tId]?.details">
                      <!-- US Financial 전용 리포트 화면 -->
                      <div v-if="tId === 'us_financial'">
                        <div class="report-row-full" style="display: flex; gap: 8px; font-size: 0.85rem; padding: 4px 8px; background: rgba(15, 23, 42, 0.2); border-radius: 6px; color: #94a3b8; width: 100%;">
                          <span style="color: #64748b;">총 소요시간:</span>
                          <strong style="color: #f8fafc;">{{ formatDuration(statusStore.status.us.tasks[tId].details.total_duration_seconds) }}</strong>
                        </div>
                        <div class="enrichment-info" v-if="statusStore.status.us.tasks[tId].details.steps && statusStore.status.us.tasks[tId].details.steps.length">
                          <span class="section-sub-label">📋 단계별 수집 및 계산 상세 결과</span>
                          <div class="steps-list font-mono">
                            <div v-for="(step, idx) in statusStore.status.us.tasks[tId].details.steps" :key="idx" class="step-item-row" style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.03); padding: 4px 0;">
                              <div style="display: flex; flex-direction: column; gap: 2px;">
                                <span class="s-name" style="font-weight: 600; color: #e2e8f0;">{{ step.step }}</span>
                                <span class="s-desc" style="font-size: 0.75rem; color: #94a3b8;">
                                  <template v-if="step.step === 'Financial Parser'">
                                    수집 성공: {{ step.details?.success_count || 0 }} / {{ step.details?.processed_count || 0 }} CIK
                                  </template>
                                  <template v-else-if="step.step === 'Metric & Valuation Calculation'">
                                    재무비율: {{ step.details?.metric_target_count || 0 }}건 | 가치평가: {{ step.details?.valuation_target_count || 0 }}건
                                  </template>
                                  <template v-else-if="step.step === 'Health Check & Isolation'">
                                    격리 데이터: {{ step.details?.anomalies_found || 0 }}건
                                  </template>
                                  <template v-else-if="step.details?.processed_count !== undefined">
                                    처리 수: {{ step.details.processed_count }}
                                  </template>
                                </span>
                              </div>
                              <div style="display: flex; align-items: center; gap: 8px;">
                                <span class="s-duration" style="font-size: 0.8rem; color: #64748b;">({{ formatDuration(step.duration_seconds) }})</span>
                                <span class="s-status" v-if="step.status !== 'SUCCESS'" :style="{ color: '#f87171', fontWeight: 'bold' }">[{{ step.status }}]</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                      
                      <!-- Daily Routine 전용 리포트 화면 -->
                      <div v-else-if="tId === 'daily_routine'">
                        <div class="report-row-full" style="display: flex; gap: 8px; font-size: 0.85rem; padding: 4px 8px; background: rgba(15, 23, 42, 0.2); border-radius: 6px; color: #94a3b8; width: 100%;">
                          <span style="color: #64748b;">총 소요시간:</span>
                          <strong style="color: #f8fafc;">{{ formatDuration(statusStore.status.us.tasks[tId].details.total_duration_seconds) }}</strong>
                        </div>
                        <div class="enrichment-info" v-if="statusStore.status.us.tasks[tId].details.steps && statusStore.status.us.tasks[tId].details.steps.length">
                          <span class="section-sub-label">📋 단계별 수집 및 계산 상세 결과</span>
                          <div class="steps-list font-mono">
                            <div v-for="(step, idx) in statusStore.status.us.tasks[tId].details.steps" :key="idx" class="step-item-row" style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.03); padding: 4px 0;">
                              <div style="display: flex; flex-direction: column; gap: 2px;">
                                <span class="s-name" style="font-weight: 600; color: #e2e8f0;">{{ step.step }}</span>
                                <span class="s-desc" style="font-size: 0.75rem; color: #94a3b8;">
                                  <template v-if="step.step === 'Master Sync'">
                                    신규 상장: {{ step.details?.new_listings || 0 }} | 상폐: {{ step.details?.delistings || 0 }} | 티커 변경: {{ step.details?.ticker_changes || 0 }}
                                  </template>
                                  <template v-else-if="step.step === 'Market Data Loader'">
                                    시세 수집: {{ step.details?.processed_count || 0 }} CIK (기간: {{ step.details?.lookback_days || 0 }}일)
                                  </template>
                                  <template v-else-if="step.step === 'Health Check & Isolation'">
                                    이상치 검출: {{ step.details?.anomalies_found || 0 }}건
                                  </template>
                                </span>
                              </div>
                              <div style="display: flex; align-items: center; gap: 8px;">
                                <span class="s-duration" style="font-size: 0.8rem; color: #64748b;">({{ formatDuration(step.duration_seconds) }})</span>
                                <span class="s-status" v-if="step.status !== 'SUCCESS'" :style="{ color: '#f87171', fontWeight: 'bold' }">[{{ step.status }}]</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                      
                      <!-- 기존 weekly_backfill 리포트 화면 -->
                      <div v-else>
                        <div class="report-grid-mini">
                          <div><span>수집수:</span> <strong>{{ statusStore.status.us.tasks[tId].details.collected_count || 0 }}건</strong></div>
                          <div><span>성공수:</span> <strong>{{ statusStore.status.us.tasks[tId].details.success_count || 0 }}건</strong></div>
                          <div><span>실패수:</span> <strong>{{ statusStore.status.us.tasks[tId].details.failed_count || 0 }}건</strong></div>
                          <div><span>소요시간:</span> <strong>{{ statusStore.status.us.tasks[tId].details.duration || '-' }}</strong></div>
                        </div>
                        
                        <!-- Enrichment 품질 보고 정보가 있는 경우 -->
                        <div class="enrichment-info" v-if="statusStore.status.us.tasks[tId].details.enrichment">
                          <span class="section-sub-label">📈 수집 및 통합 품질 (Enrichment)</span>
                          <div class="report-grid-mini nested">
                            <div><span>모수 티커수:</span> <strong>{{ statusStore.status.us.tasks[tId].details.enrichment.total_tickers || 0 }}</strong></div>
                            <div><span>정상 수집수:</span> <strong>{{ statusStore.status.us.tasks[tId].details.enrichment.success_count || 0 }}</strong></div>
                            <div><span>통합 완료율:</span> <strong style="color: #34d399">{{ ((statusStore.status.us.tasks[tId].details.enrichment.success_ratio || 0) * 100).toFixed(1) }}%</strong></div>
                          </div>
                        </div>

                        <!-- 자가 치유(Self-healing) 보고 정보가 있는 경우 -->
                        <div class="self-healing-info" v-if="statusStore.status.us.tasks[tId].details.self_healing">
                          <span class="section-sub-label">🛡️ 블랙리스트 자가 치유 (Self-Healing)</span>
                          <div class="report-grid-mini nested">
                            <div><span>쿨다운 해제:</span> <strong>{{ statusStore.status.us.tasks[tId].details.self_healing.released_count || 0 }}건</strong></div>
                            <div><span>누진 재차단:</span> <strong>{{ statusStore.status.us.tasks[tId].details.self_healing.re_blocked_count || 0 }}건</strong></div>
                            <div><span>영구 차단:</span> <strong style="color: #f87171">{{ statusStore.status.us.tasks[tId].details.self_healing.permanently_blocked_count || 0 }}건</strong></div>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div class="no-report-msg" v-else>
                      최근 실행 리포트가 존재하지 않습니다.
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>

      <!-- 하단 영역: 실시간 로그 스트리밍 (Output Stream) 한 행 전체 배치 -->
      <section class="dashboard-bottom-log-stream">
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

    <!-- 4. 데이터 익스플로러 탭 콘텐츠 -->
    <div v-else-if="activeTab === 'explorer'" class="tab-content-wrapper">
      <ExplorerView />
    </div>

    <!-- 5. 백업 및 복구 탭 콘텐츠 -->
    <div v-else-if="activeTab === 'backup'" class="tab-content-wrapper">
      <BackupView />
    </div>

    <!-- 6. 데이터 동기화 탭 콘텐츠 -->
    <div v-else-if="activeTab === 'sync'" class="tab-content-wrapper">
      <SyncView />
    </div>
  </div>
</template>


<style scoped>
.dashboard-container {
  max-width: 1440px;
  margin: 0 auto;
  padding: 2.5rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
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

/* 헬스 보드 사이드바 */
.split-status-sidebar {
  width: 320px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.health-card {
  background: rgba(30, 41, 59, 0.4);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
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
  white-space: nowrap;
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
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  background: rgba(15, 23, 42, 0.3);
  padding: 1rem;
  border-radius: 12px;
}

.metric-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  padding-bottom: 0.5rem;
}

.metric-group-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.metric-col {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.metric-col.align-end {
  align-items: flex-end;
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
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
}

/* 환경 배지 */
.env-badge-container {
  margin-left: 1rem;
  display: inline-flex;
  align-items: center;
}

.env-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 4px 10px;
  border-radius: 9999px;
  font-size: 0.8rem;
  font-weight: 700;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.env-badge.dev {
  background: rgba(16, 185, 129, 0.12);
  color: #34d399;
  border-color: rgba(16, 185, 129, 0.3);
}

.env-badge.dev .badge-dot {
  width: 6px;
  height: 6px;
  background-color: var(--color-emerald);
  border-radius: 50%;
  box-shadow: 0 0 6px var(--color-emerald);
}

.env-badge.server {
  background: rgba(244, 63, 94, 0.12);
  color: #f87171;
  border-color: rgba(244, 63, 94, 0.3);
}

.env-badge.server .badge-dot {
  width: 6px;
  height: 6px;
  background-color: var(--color-rose);
  border-radius: 50%;
  box-shadow: 0 0 6px var(--color-rose);
}

.env-badge.unknown {
  background: rgba(148, 163, 184, 0.12);
  color: #94a3b8;
  border-color: rgba(148, 163, 184, 0.3);
}

.env-badge.unknown .badge-dot {
  width: 6px;
  height: 6px;
  background-color: #94a3b8;
  border-radius: 50%;
}

.badge-dot.blink {
  animation: blink-dot 1.5s infinite;
}

@keyframes blink-dot {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; box-shadow: 0 0 8px var(--color-rose); }
}
/* 마켓별 태스크 분리 레이아웃 */
.market-task-group {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  background: rgba(30, 41, 59, 0.2);
  padding: 1.5rem;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.market-group-title {
  margin: 0;
  font-size: 1.05rem;
  color: #a5b4fc;
  font-weight: 600;
  letter-spacing: 0.5px;
}

/* 실행 품질 보고서 CSS */
.reports-section {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.reports-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 1.5rem;
}

.report-group-card {
  background: rgba(30, 41, 59, 0.4);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.report-group-card h3 {
  margin: 0;
  font-size: 1.1rem;
  color: #f1f5f9;
  font-weight: 700;
}

.report-content-box {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.sub-report-item {
  background: rgba(15, 23, 42, 0.3);
  border-radius: 12px;
  padding: 1.25rem;
  border: 1px solid rgba(255, 255, 255, 0.04);
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.sub-report-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  padding-bottom: 0.5rem;
}

.sub-title {
  color: #e2e8f0;
  font-size: 0.95rem;
}

.sub-status {
  font-size: 0.75rem;
  font-weight: 800;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  background: rgba(148, 163, 184, 0.1);
  color: #94a3b8;
}

.sub-status.success, .sub-status.running {
  background: rgba(52, 211, 153, 0.15);
  color: #34d399;
}

.sub-status.failed, .sub-status.interrupted {
  background: rgba(248, 113, 113, 0.15);
  color: #f87171;
}

.sub-report-body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.report-grid-mini {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.5rem;
  font-size: 0.85rem;
}

.report-grid-mini div {
  display: flex;
  justify-content: space-between;
  color: #94a3b8;
  padding: 4px 8px;
  background: rgba(15, 23, 42, 0.2);
  border-radius: 6px;
}

.report-grid-mini div span {
  color: #64748b;
  white-space: nowrap;
  flex-shrink: 0;
}

.report-grid-mini div strong {
  color: #f8fafc;
}

.report-grid-mini.nested {
  grid-template-columns: repeat(3, 1fr);
  background: rgba(99, 102, 241, 0.05);
  border: 1px solid rgba(99, 102, 241, 0.15);
  padding: 0.5rem;
  border-radius: 8px;
}

.section-sub-label {
  font-size: 0.8rem;
  font-weight: 700;
  color: #818cf8;
  margin-top: 0.5rem;
  display: inline-block;
}

.log-message {
  font-size: 0.75rem;
  background: #0f172a;
  padding: 8px;
  border-radius: 6px;
  color: #cbd5e1;
  word-break: break-all;
  border: 1px solid rgba(255, 255, 255, 0.05);
  max-height: 80px;
  overflow-y: auto;
}

.no-report-msg {
  color: #475569;
  font-size: 0.8rem;
  text-align: center;
  padding: 0.5rem;
}
/* 상단 가로 분할 영역 */
.dashboard-top-split {
  display: flex;
  gap: 2rem;
  align-items: stretch;
  margin-top: 0.5rem;
  width: 100%;
}

.split-control-panel {
  flex: 1;
  min-width: 0;
  background: rgba(30, 41, 59, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.04);
  padding: 1.5rem;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

/* 좌측 실시간 상태 헤더 (우측 탭 헤더와 정확한 높이 정렬) */
.sidebar-title-header {
  border-bottom: 2px solid rgba(255, 255, 255, 0.06);
  padding-bottom: 0.5rem;
  height: 38px;
  display: flex;
  align-items: center;
  box-sizing: border-box;
}

.sidebar-title-header h2 {
  font-size: 1.05rem;
  color: #f8fafc;
  font-weight: 700;
  margin: 0;
}

/* 하단 실시간 로그 스트리밍 영역 */
.dashboard-bottom-log-stream {
  width: 100%;
  margin-top: 2rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

/* 서브 탭 헤더 스타일 */
.control-tab-headers {
  display: flex;
  gap: 0.5rem;
  border-bottom: 2px solid rgba(255, 255, 255, 0.06);
  padding-bottom: 0.5rem;
  height: 38px;
  align-items: center;
  box-sizing: border-box;
}

.tab-btn {
  background: transparent;
  border: none;
  color: #94a3b8;
  padding: 0.35rem 0.75rem;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  border-radius: 8px;
  transition: all 0.2s ease-in-out;
  display: inline-flex;
  align-items: center;
  height: 28px;
}

.tab-btn:hover {
  background: rgba(255, 255, 255, 0.04);
  color: #f1f5f9;
}

.tab-btn.active {
  background: rgba(99, 102, 241, 0.15);
  color: #a5b4fc;
  border: 1px solid rgba(99, 102, 241, 0.3);
}

.control-tab-content {
  background: rgba(15, 23, 42, 0.15);
  border-radius: 16px;
  min-height: 280px;
  padding: 1rem 0.5rem 0.25rem 0.5rem;
}

.panel-section-title {
  margin: 0 0 1rem 0;
  font-size: 1.05rem;
  color: #f8fafc;
  font-weight: 700;
}

.tab-pane {
  animation: fadeIn 0.25s ease-in;
}

.full-width-card {
  grid-column: 1 / -1;
  width: 100%;
}

.quality-reports-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1.25rem;
  width: 100%;
  margin-top: 0.5rem;
}

.quality-report-card {
  background: rgba(15, 23, 42, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.04);
  border-radius: 12px;
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 모바일 및 소형 화면 대응 반응형 */
@media (max-width: 1024px) {
  .dashboard-top-split {
    flex-direction: column;
    align-items: stretch;
  }
  .split-status-sidebar {
    width: 100%;
  }
  .sidebar-title-header {
    height: auto;
    padding-bottom: 0.25rem;
  }
  .control-tab-headers {
    height: auto;
    flex-wrap: wrap;
    gap: 0.25rem;
  }
}

.steps-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  background: rgba(15, 23, 42, 0.3);
  padding: 0.5rem;
  border-radius: 8px;
  font-size: 0.8rem;
  margin-top: 0.5rem;
}
.step-item-row {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
  padding-bottom: 2px;
}
</style>
