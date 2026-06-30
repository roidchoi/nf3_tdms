<script setup lang="ts">
import { computed, ref } from 'vue'
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
  if (props.status?.is_running) return 'var(--color-indigo)'   // 실행 중
  if (props.status?.last_status === 'success') return 'var(--color-emerald)' // 완료
  if (props.status?.last_status === 'failed') return 'var(--color-rose)'    // 에러
  return 'var(--color-slate)'                                   // 대기
})

const statusText = computed(() => {
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
</script>

<template>
  <div class="card" :style="{ '--glow-color': themeColor }" :class="{ 'warning-border': market === 'kr' && !isTestMode && isKoreanMarketOpen() }">
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
      <div class="status-summary">
        <span class="label">마지막 상태</span>
        <span class="value" :style="{ color: themeColor }">{{ status?.last_status || '-' }}</span>
      </div>

      <div class="status-summary">
        <span class="label">마지막 실행 시간</span>
        <span class="value font-mono">{{ status?.last_run_time ? new Date(status.last_run_time).toLocaleString() : '-' }}</span>
      </div>

      <!-- 태스크 기동 시 흘러가는 바 애니메이션 -->
      <div class="loading-bar-container" v-if="status?.is_running">
        <div class="loading-bar-fill"></div>
      </div>
    </div>

    <div class="card-footer">
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
</style>
