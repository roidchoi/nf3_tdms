<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAdminStore } from '@/stores/adminStore'
import type { TaskStatus, ScheduleItem } from '@/types/admin'

// 부모로부터 받을 데이터 정의
const props = defineProps<{
  taskId: string
  title: string
  icon: string
  status: TaskStatus | undefined
  schedule: ScheduleItem | undefined
}>()

const adminStore = useAdminStore()

// 안전을 위해 기본값을 'true' (테스트 모드)로 설정
const isTestMode = ref(true)

// 상태 색상
const statusColor = computed(() => {
  if (props.status?.is_running) return '#2563eb'
  if (props.status?.last_status === 'failure') return '#dc2626'
  if (props.status?.last_status === 'success') return '#10b981'
  return '#64748b'
})

const statusText = computed(() => {
  if (props.status?.is_running) return '실행 중...'
  if (props.status?.last_status === 'success') return '완료됨'
  if (props.status?.last_status === 'failure') return '오류 발생'
  return '대기 중'
})

// 날짜 포맷팅 헬퍼 (다음 실행 시간)
const formatTime = (isoString?: string | null) => {
  if (!isoString) return '-'
  // 오늘/내일 등의 상대적 표현보다는 명확한 날짜/시간 표시
  const date = new Date(isoString)
  const month = date.getMonth() + 1
  const day = date.getDate()
  const hour = String(date.getHours()).padStart(2, '0')
  const minute = String(date.getMinutes()).padStart(2, '0')
  return `${month}/${day} ${hour}:${minute}`
}

// [수정] 트리거 문자열 직관적으로 변환
// 입력 예: cron[day_of_week='mon-fri', hour='16', minute='25']
const formatTrigger = (trigger?: string) => {
  if (!trigger) return '수동 실행 전용'

  // 정규식으로 요일, 시간 추출
  const dayMatch = trigger.match(/day_of_week='([^']+)'/)
  const hourMatch = trigger.match(/hour='([^']+)'/)
  const minuteMatch = trigger.match(/minute='([^']+)'/)

  // [수정] match 결과뿐만 아니라 캡처 그룹([1])이 존재하는지까지 확인해야 TypeScript 에러가 사라집니다.
  if (
    dayMatch && dayMatch[1] &&
    hourMatch && hourMatch[1] &&
    minuteMatch && minuteMatch[1]
  ) {
    const rawDay = dayMatch[1]
    const hour = hourMatch[1].padStart(2, '0')
    const minute = minuteMatch[1].padStart(2, '0')

    // 요일 한글 매핑
    const dayMap: Record<string, string> = {
      'mon-fri': '평일(월~금)',
      'mon': '매주 월요일',
      'tue': '매주 화요일',
      'wed': '매주 수요일',
      'thu': '매주 목요일',
      'fri': '매주 금요일',
      'sat': '매주 토요일',
      'sun': '매주 일요일'
    }

    // rawDay가 string임이 보장되므로 인덱스 에러 해결됨
    const kDay = dayMap[rawDay] || rawDay 
    return `${kDay} ${hour}:${minute}`
  }

  // 매칭되지 않는 경우
  return trigger.replace('cron', '스케줄')
}

// 실행 핸들러 (안전장치 강화)
const handleRun = async () => {
  const now = new Date()
  const hour = now.getHours()
  const minute = now.getMinutes()
  
  // 장 운영 시간(09:00 ~ 15:30) 체크
  const isMarketOpen = (hour > 9 || (hour === 9 && minute >= 0)) && (hour < 15 || (hour === 15 && minute <= 30))
  
  let message = `[${props.title}] 작업을 정말 실행하시겠습니까?\n\n`
  message += `▶ 실행 모드: ${isTestMode.value ? '🧪 테스트 모드' : '⚠️ 운영 모드 (실제 데이터 변경)'}\n`
  
  if (!isTestMode.value && isMarketOpen) {
    message += `\n🚨 [주의] 현재 장 거래 시간입니다!\n운영 모드 실행 시 DB 데이터 오염 위험이 있습니다.\n정말 진행하시겠습니까?`
  } else if (!isTestMode.value) {
    message += `\n⚠️ 운영 모드는 실제 DB 데이터를 변경합니다.`
  }

  if (!confirm(message)) return
  
  await adminStore.runTask(props.taskId, isTestMode.value)
}
</script>

<template>
  <div class="card">
    <div class="card-header">
      <div class="title-group">
        <span class="icon">{{ icon }}</span>
        <h3>{{ title }}</h3>
      </div>
      <span class="badge" :style="{ backgroundColor: statusColor }">
        {{ statusText }}
      </span>
    </div>

    <div class="card-body">
      <div class="progress-section">
        <div class="progress-info">
          <span class="phase">{{ status?.phase_name || '대기 중' }}</span>
          <span class="percent">{{ status?.progress?.toFixed(1) || 0 }}%</span>
        </div>
        <div class="progress-bar-bg">
          <div 
            class="progress-bar-fill" 
            :style="{ width: `${status?.progress || 0}%`, backgroundColor: statusColor }"
          ></div>
        </div>
      </div>

      <div class="details-grid">
        <div class="detail-item">
          <span class="label">처리 현황</span>
          <span class="value">{{ status?.stocks_processed || 0 }} / {{ status?.total_stocks || 0 }}</span>
        </div>
        <div class="detail-item">
          <span class="label">마지막 상태</span>
          <span class="value" :style="{ color: statusColor }">{{ status?.last_status || '-' }}</span>
        </div>
        
        <div class="detail-item schedule-info">
          <span class="label">실행 주기</span>
          <span class="value highlight" :title="schedule?.trigger">
            {{ formatTrigger(schedule?.trigger) }}
          </span>
        </div>
        <div class="detail-item schedule-info">
          <span class="label">다음 실행</span>
          <span class="value highlight">{{ formatTime(schedule?.next_run) }}</span>
        </div>
      </div>

      <div class="log-area">
        <p class="last-log" :title="status?.last_log">
          {{ status?.last_log || '로그 대기 중...' }}
        </p>
      </div>
    </div>

    <div class="card-footer">
      <label class="checkbox">
        <input type="checkbox" v-model="isTestMode" :disabled="status?.is_running">
        <span class="checkbox-label">테스트 모드</span>
      </label>
      <button 
        class="run-btn" 
        @click="handleRun" 
        :disabled="status?.is_running"
        :class="{ running: status?.is_running }"
      >
        {{ status?.is_running ? '실행 중...' : '즉시 실행' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.card {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #e2e8f0;
  transition: transform 0.2s;
}

.card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 6px rgba(0,0,0,0.08);
}

.card-header {
  padding: 1rem 1.2rem;
  border-bottom: 1px solid #f1f5f9;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #f8fafc;
}

.title-group {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.title-group h3 {
  margin: 0;
  font-size: 1rem;
  color: #334155;
  font-weight: 600;
}

.badge {
  padding: 0.25rem 0.6rem;
  border-radius: 6px;
  color: white;
  font-size: 0.75rem;
  font-weight: 600;
}

.card-body {
  padding: 1.2rem;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.4rem;
  font-size: 0.85rem;
  color: #64748b;
}

.progress-bar-bg {
  height: 6px;
  background: #e2e8f0;
  border-radius: 3px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  transition: width 0.5s ease;
}

.details-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.8rem;
  background: #f8fafc;
  padding: 0.8rem;
  border-radius: 8px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.detail-item .label {
  font-size: 0.75rem;
  color: #94a3b8;
}

.detail-item .value {
  font-size: 0.85rem;
  color: #334155;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.highlight {
  color: #2563eb;
  font-weight: 600;
}

.log-area {
  background: #1e293b;
  padding: 0.6rem;
  border-radius: 6px;
}

.last-log {
  margin: 0;
  font-size: 0.75rem;
  color: #cbd5e1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: monospace;
}

.card-footer {
  padding: 0.8rem 1.2rem;
  background: white;
  border-top: 1px solid #f1f5f9;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.checkbox {
  font-size: 0.85rem;
  color: #475569;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  cursor: pointer;
  user-select: none;
}

.run-btn {
  padding: 0.4rem 0.8rem;
  background: #334155;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.run-btn:hover:not(:disabled) {
  background: #1e293b;
}

.run-btn:disabled {
  background: #94a3b8;
  cursor: not-allowed;
  opacity: 0.7;
}
</style>