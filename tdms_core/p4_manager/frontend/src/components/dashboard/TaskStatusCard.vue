<script setup lang="ts">
import { computed, ref, reactive } from 'vue'
import { useStatusStore } from '@/stores/statusStore'
import type { MarketTaskSummary } from '@/types/admin'

const props = defineProps<{
  market: 'kr' | 'us'
  taskId: string
  title: string
  icon: string
  status: MarketTaskSummary | null | undefined
}>()

const statusStore = useStatusStore()

// 안전을 위해 기본값 'true' (테스트 모드)
const isTestMode = ref(true)

// 상태 색상 및 쉐도우 (HSL)
const themeColor = computed(() => {
  if (props.taskId === 'backfill_minute_data') {
    const minRun = statusStore.status.kr.tasks?.backfill_minute_data?.is_running
    const dailyRun = statusStore.status.kr.tasks?.backfill_daily_data?.is_running
    const capRun = statusStore.status.kr.tasks?.backfill_market_cap?.is_running
    
    if (minRun || dailyRun || capRun) return 'var(--color-indigo)' // 실행 중
    
    const minStat = statusStore.status.kr.tasks?.backfill_minute_data?.last_status
    const dailyStat = statusStore.status.kr.tasks?.backfill_daily_data?.last_status
    const capStat = statusStore.status.kr.tasks?.backfill_market_cap?.last_status
    
    if (minStat === 'failed' || dailyStat === 'failed' || capStat === 'failed') return 'var(--color-rose)'
    if (minStat === 'success' || dailyStat === 'success' || capStat === 'success') return 'var(--color-emerald)'
    return 'var(--color-slate)'
  }

  if (props.status?.is_running) return 'var(--color-indigo)'   // 실행 중
  if (props.status?.last_status === 'success') return 'var(--color-emerald)' // 완료
  if (props.status?.last_status === 'failed') return 'var(--color-rose)'    // 에러
  return 'var(--color-slate)'                                   // 대기
})

const statusText = computed(() => {
  if (props.taskId === 'backfill_minute_data') {
    const minRun = statusStore.status.kr.tasks?.backfill_minute_data?.is_running
    const dailyRun = statusStore.status.kr.tasks?.backfill_daily_data?.is_running
    const capRun = statusStore.status.kr.tasks?.backfill_market_cap?.is_running
    
    if (minRun || dailyRun || capRun) return '실행 중...'
    
    const minStat = statusStore.status.kr.tasks?.backfill_minute_data?.last_status
    const dailyStat = statusStore.status.kr.tasks?.backfill_daily_data?.last_status
    const capStat = statusStore.status.kr.tasks?.backfill_market_cap?.last_status
    
    if (minStat === 'success' && dailyStat === 'success' && capStat === 'success') return '완료됨'
    return '대기 중'
  }

  if (props.status?.is_running) return '실행 중...'
  if (props.status?.last_status === 'success') return '완료됨'
  if (props.status?.last_status === 'failed') return '오류 발생'
  return '대기 중'
})

// 장 운영 시간대 판별 (한국 정규 거래 시간: 09:00 ~ 15:30)
const isKoreanMarketOpen = () => {
  const now = new Date()
  const hour = now.getHours()
  const minute = now.getMinutes()
  return (hour > 9 || (hour === 9 && minute >= 0)) && (hour < 15 || (hour === 15 && minute <= 30))
}

// 미국 장 운영 시간대 판별 (뉴욕 시간: 09:30 ~ 16:00, 월~금)
const isUSMarketOpen = () => {
  try {
    const options: Intl.DateTimeFormatOptions = {
      timeZone: 'America/New_York',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      weekday: 'short'
    }
    const formatter = new Intl.DateTimeFormat('en-US', options)
    const parts = formatter.formatToParts(new Date())
    const partMap = Object.fromEntries(parts.map(p => [p.type, p.value]))
    
    const weekday = partMap.weekday
    const hour = parseInt(partMap.hour || '0', 10)
    const minute = parseInt(partMap.minute || '0', 10)
    
    if (weekday === 'Sat' || weekday === 'Sun') return false
    
    const totalMinutes = hour * 60 + minute
    const startMinutes = 9 * 60 + 30
    const endMinutes = 16 * 60
    
    return totalMinutes >= startMinutes && totalMinutes < endMinutes
  } catch (e) {
    return false
  }
}

const isWarningActive = computed(() => {
  if (props.market === 'kr') {
    return !isTestMode.value && isKoreanMarketOpen()
  } else if (props.market === 'us') {
    return isUSMarketOpen()
  }
  return false
})

const formatDate24h = (dateStr: string | number | Date) => {
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return '-'
  const pad = (n: number) => n.toString().padStart(2, '0')
  const Y = d.getFullYear()
  const M = pad(d.getMonth() + 1)
  const D = pad(d.getDate())
  const h = pad(d.getHours())
  const m = pad(d.getMinutes())
  const s = pad(d.getSeconds())
  return `${Y}-${M}-${D} ${h}:${m}:${s}`
}

const latestRunTimeText = computed(() => {
  if (props.taskId === 'backfill_minute_data') {
    const times = [
      statusStore.status.kr.tasks?.backfill_minute_data?.last_run_time,
      statusStore.status.kr.tasks?.backfill_daily_data?.last_run_time,
      statusStore.status.kr.tasks?.backfill_market_cap?.last_run_time
    ].filter(Boolean).map(t => new Date(t!).getTime())
    
    if (times.length > 0) {
      return formatDate24h(Math.max(...times))
    }
    return '-'
  }
  return props.status?.last_run_time ? formatDate24h(props.status.last_run_time) : '-'
})

const handleRun = async () => {
  let message = `[${props.title}] 작업을 실행하시겠습니까?\n\n`
  
  if (props.market === 'kr') {
    message += `▶ 실행 모드: ${isTestMode.value ? '🧪 테스트 모드' : '⚠️ 운영 모드 (실제 데이터 변경)'}\n`
    
    // 장 거래 시간 중에 운영 모드로 기동하려고 하는 경우 추가 경고
    if (!isTestMode.value && isKoreanMarketOpen()) {
      message += `\n🚨 [경고] 현재 한국 주식시장 장중 거래 시간입니다!\n운영 모드 실행 시 실시간 DB 데이터 오염 위험이 매우 높습니다.\n정말 진행하시겠습니까?`
    }
  } else {
    message += `▶ 실행 모드: ⚠️ 운영 수집 모드\n`
    
    if (isUSMarketOpen()) {
      message += `\n🚨 [경고] 현재 미국 주식시장 장중 거래 시간(09:30~16:00 EST)입니다!\n실시간 수집 시 데이터 정합성 충돌 및 API 호출 초과 위험이 매우 높습니다.\n정말 진행하시겠습니까?`
    }
  }

  if (!confirm(message)) return

  try {
    const isTest = props.market === 'kr' ? isTestMode.value : false
    await statusStore.runTask(props.market, props.taskId, isTest)
    alert('태스크 수동 실행 요청 완료')
  } catch (error: any) {
    alert(`태스크 실행 실패: ${error?.response?.data?.detail || error.message}`)
  }
}

const backfillDays = reactive({
  backfill_minute_data: 30,
  backfill_daily_data: 30,
  backfill_market_cap: 30
})

const handleRunCustom = async (subTaskId: 'backfill_minute_data' | 'backfill_daily_data' | 'backfill_market_cap') => {
  let subTitle = ''
  if (subTaskId === 'backfill_minute_data') subTitle = '분봉 백필'
  else if (subTaskId === 'backfill_daily_data') subTitle = '일봉 백필'
  else if (subTaskId === 'backfill_market_cap') subTitle = '시가총액 백필'

  const days = backfillDays[subTaskId] ?? 30
  let message = `[${subTitle} (${days === 0 ? '전기간(2017~)' : days + '일'})] 작업을 실행하시겠습니까?\n\n`
  message += `▶ 실행 모드: ⚠️ 운영 모드 (실제 데이터 변경)\n`
  if (days === 0) {
    if (subTaskId === 'backfill_market_cap') {
      message += `▶ 백필 지정 기간: 0일 (2017-01-02 기준 시총+매매동향 전기간 백필)\n`
    } else {
      message += `▶ 백필 지정 기간: 0일 (2017-01-02 기준 전기간 전수 백필)\n`
    }
  } else {
    message += `▶ 백필 지정 기간: ${days}일\n`
  }

  if (isKoreanMarketOpen()) {
    message += `\n🚨 [경고] 현재 한국 주식시장 장중 거래 시간입니다!\n운영 모드 실행 시 실시간 DB 데이터 오염 위험이 매우 높습니다.\n정말 진행하시겠습니까?`
  }

  if (!confirm(message)) return

  try {
    await statusStore.runTask(props.market, subTaskId, false, days)
    alert(`${subTitle} (${days === 0 ? '2017-01-02 기준 전기간' : days + '일'}) 수동 실행 요청 완료`)
  } catch (error: any) {
    alert(`태스크 실행 실패: ${error?.response?.data?.detail || error.message}`)
  }
}

const latestBackfillStatusText = computed(() => {
  const minTask = statusStore.status.kr.tasks?.backfill_minute_data
  const dailyTask = statusStore.status.kr.tasks?.backfill_daily_data
  const capTask = statusStore.status.kr.tasks?.backfill_market_cap

  const tasks = [
    { name: '분봉', task: minTask },
    { name: '일봉', task: dailyTask },
    { name: '시총', task: capTask }
  ]

  const validTasks: Array<{ name: string; daysStr: string; status: string; time: number }> = []

  for (const t of tasks) {
    if (t.task && t.task.last_run_time) {
      const rawDays = (t.task as any).details?.backfill_days ?? (t.task as any).backfill_days
      const days = rawDays !== undefined ? rawDays : 30
      validTasks.push({
        name: t.name,
        daysStr: days === 0 ? '전기간(2017~)' : `${days}일`,
        status: t.task.last_status || 'none',
        time: new Date(t.task.last_run_time).getTime()
      })
    }
  }

  if (validTasks.length === 0) {
    return '-'
  }

  validTasks.sort((a, b) => b.time - a.time)
  return `${validTasks[0].name} - ${validTasks[0].daysStr} - ${validTasks[0].status}`
})
</script>

<template>
  <div class="card" :style="{ '--glow-color': themeColor }" :class="{ 'warning-border': isWarningActive }">
    <div class="card-header">
      <div class="title-group">
        <span class="icon">{{ icon }}</span>
        <h3>{{ title }}</h3>
      </div>
      <span class="badge" :style="{ backgroundColor: themeColor }">
        {{ statusText }}
      </span>
    </div>

    <div class="card-body">
      <div class="status-summary" v-if="taskId !== 'backfill_minute_data'">
        <span class="label">최종 상태</span>
        <span class="value" :style="{ color: themeColor }">{{ status?.last_status || '-' }}</span>
      </div>
      <div class="status-summary" v-else>
        <span class="label">최종 상태</span>
        <span class="value" :style="{ color: themeColor }">{{ latestBackfillStatusText }}</span>
      </div>

      <div class="status-summary">
        <span class="label">최종 실행</span>
        <span class="value font-mono">{{ latestRunTimeText }}</span>
      </div>

      <!-- 태스크 기동 시 흘러가는 바 애니메이션 -->
      <div class="loading-bar-container" v-if="taskId === 'backfill_minute_data' ? (statusStore.status.kr.tasks?.backfill_minute_data?.is_running || statusStore.status.kr.tasks?.backfill_daily_data?.is_running || statusStore.status.kr.tasks?.backfill_market_cap?.is_running) : status?.is_running">
        <div class="loading-bar-fill"></div>
      </div>
    </div>

    <div class="card-footer">
      <template v-if="taskId === 'backfill_minute_data'">
        <div class="backfill-controls-grid">
          <div class="backfill-control-item">
            <div class="input-wrap">
              <input 
                type="number" 
                min="1" 
                max="365"
                v-model.number="backfillDays.backfill_minute_data" 
                class="days-input" 
                placeholder="30"
                :disabled="statusStore.status.kr.tasks?.backfill_minute_data?.is_running || statusStore.status.kr.tasks?.backfill_daily_data?.is_running || statusStore.status.kr.tasks?.backfill_market_cap?.is_running"
              />
              <span class="unit-text">일</span>
            </div>
            <button 
              class="run-btn mini" 
              @click="handleRunCustom('backfill_minute_data')" 
              :disabled="statusStore.status.kr.tasks?.backfill_minute_data?.is_running || statusStore.status.kr.tasks?.backfill_daily_data?.is_running || statusStore.status.kr.tasks?.backfill_market_cap?.is_running"
            >
              {{ statusStore.status.kr.tasks?.backfill_minute_data?.is_running ? '실행 중' : '분봉' }}
            </button>
          </div>

          <div class="backfill-control-item">
            <div class="input-wrap">
              <input 
                type="number" 
                min="0" 
                max="3650"
                v-model.number="backfillDays.backfill_daily_data" 
                class="days-input" 
                placeholder="30"
                :disabled="statusStore.status.kr.tasks?.backfill_minute_data?.is_running || statusStore.status.kr.tasks?.backfill_daily_data?.is_running || statusStore.status.kr.tasks?.backfill_market_cap?.is_running"
              />
              <span class="unit-text">일</span>
            </div>
            <button 
              class="run-btn mini" 
              @click="handleRunCustom('backfill_daily_data')" 
              :disabled="statusStore.status.kr.tasks?.backfill_minute_data?.is_running || statusStore.status.kr.tasks?.backfill_daily_data?.is_running || statusStore.status.kr.tasks?.backfill_market_cap?.is_running"
            >
              {{ statusStore.status.kr.tasks?.backfill_daily_data?.is_running ? '실행 중' : '일봉' }}
            </button>
          </div>

          <div class="backfill-control-item">
            <div class="input-wrap">
              <input 
                type="number" 
                min="0" 
                max="3650"
                v-model.number="backfillDays.backfill_market_cap" 
                class="days-input" 
                placeholder="30"
                :disabled="statusStore.status.kr.tasks?.backfill_minute_data?.is_running || statusStore.status.kr.tasks?.backfill_daily_data?.is_running || statusStore.status.kr.tasks?.backfill_market_cap?.is_running"
              />
              <span class="unit-text">일</span>
            </div>
            <button 
              class="run-btn mini" 
              @click="handleRunCustom('backfill_market_cap')" 
              :disabled="statusStore.status.kr.tasks?.backfill_minute_data?.is_running || statusStore.status.kr.tasks?.backfill_daily_data?.is_running || statusStore.status.kr.tasks?.backfill_market_cap?.is_running"
            >
              {{ statusStore.status.kr.tasks?.backfill_market_cap?.is_running ? '실행 중' : '시총' }}
            </button>
          </div>
        </div>
      </template>
      <template v-else>
        <!-- 한국(kr) 전용 테스트 모드 Switch UI -->
        <div class="switch-container" v-if="market === 'kr'">
          <span class="switch-label">테스트 모드</span>
          <label class="switch-btn">
            <input type="checkbox" v-model="isTestMode" :disabled="status?.is_running">
            <span class="slider"></span>
          </label>
        </div>

        <button 
          class="run-btn" 
          @click="handleRun" 
          :disabled="status?.is_running"
          :class="{ running: status?.is_running }"
        >
          {{ status?.is_running ? '실행 중' : '즉시 실행' }}
        </button>
      </template>
    </div>
  </div>
</template>

<style scoped>
.card {
  background: rgba(30, 41, 59, 0.7);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
}

.card:hover {
  transform: translateY(-4px);
  border-color: var(--glow-color);
  box-shadow: 0 0 20px -3px var(--glow-color);
}

/* 장중 정규 운영 기동 경고 시 붉은 보더 */
.card.warning-border {
  border-color: var(--color-rose) !important;
  box-shadow: 0 0 20px -3px var(--color-rose) !important;
}

.card-header {
  padding: 1.25rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: rgba(15, 23, 42, 0.4);
}

.title-group {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.icon {
  font-size: 1.25rem;
}

.title-group h3 {
  margin: 0;
  font-size: 1.05rem;
  color: #f1f5f9;
  font-weight: 600;
}

.badge {
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  color: #ffffff;
  font-size: 0.75rem;
  font-weight: 700;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

.card-body {
  padding: 1.5rem;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.status-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.875rem;
}

.label {
  color: #94a3b8;
}

.value {
  color: #f8fafc;
  font-weight: 500;
  white-space: nowrap;
}

.font-mono {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 0.8rem;
}

.loading-bar-container {
  height: 6px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 9999px;
  overflow: hidden;
  position: relative;
  margin-top: 0.5rem;
}

.loading-bar-fill {
  height: 100%;
  width: 50%;
  background: linear-gradient(90deg, transparent, var(--color-indigo), transparent);
  border-radius: 9999px;
  position: absolute;
  animation: loadingSlide 1.5s infinite linear;
}

@keyframes loadingSlide {
  0% { left: -50%; }
  100% { left: 100%; }
}

.card-footer {
  padding: 1.25rem;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: rgba(15, 23, 42, 0.2);
}

/* Custom Switch UI */
.switch-container {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.switch-label {
  font-size: 0.8rem;
  color: #94a3b8;
}

.switch-btn {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 22px;
}

.switch-btn input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #475569;
  transition: .4s;
  border-radius: 34px;
}

.slider:before {
  position: absolute;
  content: "";
  height: 16px;
  width: 16px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: .4s;
  border-radius: 50%;
}

input:checked + .slider {
  background-color: var(--color-indigo);
  box-shadow: 0 0 8px var(--color-indigo);
}

input:checked + .slider:before {
  transform: translateX(22px);
}

input:disabled + .slider {
  opacity: 0.5;
  cursor: not-allowed;
}

.run-btn {
  background: #334155;
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #f8fafc;
  padding: 0.5rem 1.25rem;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.run-btn:hover:not(:disabled) {
  background: var(--color-indigo);
  border-color: var(--color-indigo);
  box-shadow: 0 0 12px rgba(99, 102, 241, 0.4);
  transform: scale(1.03);
}

.run-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-group-horizontal {
  display: flex;
  gap: 0.5rem;
  width: 100%;
}

.btn-group-horizontal .run-btn.mini {
  flex: 1;
  padding: 0.4rem 0.5rem;
  font-size: 0.8rem;
  text-align: center;
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.btn-group-horizontal .run-btn.mini:hover:not(:disabled) {
  background: var(--color-indigo);
  border-color: var(--color-indigo);
  color: #fff;
  box-shadow: 0 0 8px rgba(99, 102, 241, 0.4);
}

.backfill-controls-grid {
  display: flex;
  gap: 8px;
  width: 100%;
}

.backfill-control-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.backfill-control-item .run-btn.mini {
  width: 100%;
  padding: 0.4rem 0.2rem;
  font-size: 0.8rem;
  text-align: center;
  background: rgba(30, 41, 59, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 6px;
}

.backfill-control-item .run-btn.mini:hover:not(:disabled) {
  background: var(--color-indigo);
  border-color: var(--color-indigo);
  color: #fff;
  box-shadow: 0 0 8px rgba(99, 102, 241, 0.4);
}

.input-wrap {
  display: flex;
  align-items: center;
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 6px;
  padding: 3px 6px;
  transition: border-color 0.2s;
}

.input-wrap:focus-within {
  border-color: var(--color-indigo);
  box-shadow: 0 0 6px rgba(99, 102, 241, 0.3);
}

.days-input {
  width: 100%;
  background: transparent;
  border: none;
  color: #f8fafc;
  font-size: 12px;
  font-weight: 600;
  font-family: inherit;
  text-align: center;
  outline: none;
  -moz-appearance: textfield;
}

.days-input::-webkit-outer-spin-button,
.days-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.unit-text {
  font-size: 11px;
  color: #94a3b8;
  white-space: nowrap;
}

</style>

