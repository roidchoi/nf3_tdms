<script setup lang="ts">
import { ref } from 'vue'
import { useHealthStore } from '@/stores/healthStore'

const healthStore = useHealthStore()

// 기본값: 최근 1개월
const endDate = ref(new Date().toISOString().split('T')[0])
const startDate = ref(new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0])

const handleCheck = async () => {
  // [수정] 타입 가드 추가 (값이 없으면 실행하지 않음)
  if (!startDate.value || !endDate.value) {
    alert('시작일과 종료일을 모두 선택해주세요.')
    return
  }
  
  // 이제 TypeScript는 .value가 string임을 확신합니다.
  await healthStore.checkGaps(startDate.value, endDate.value)
}

const getGapColor = (count: number) => count > 0 ? 'text-red' : 'text-green'
</script>

<template>
  <div class="gap-inspector">
    <div class="panel-header">
      <h3>🔍 데이터 누락일 정밀 검사 (Market Gaps)</h3>
      <div class="controls">
        <input type="date" v-model="startDate" class="date-input">
        <span class="tilde">~</span>
        <input type="date" v-model="endDate" class="date-input">
        <button @click="handleCheck" :disabled="healthStore.isLoading" class="check-btn">
          {{ healthStore.isLoading ? '검사 중...' : '검사 실행' }}
        </button>
      </div>
    </div>

    <div class="panel-body">
      <div v-if="!healthStore.gapResult" class="empty-state">
        기간을 설정하고 '검사 실행' 버튼을 눌러주세요.
      </div>

      <div v-else class="result-grid">
        <div v-for="res in healthStore.gapResult.results" :key="res.market" class="market-card">
          <div class="market-header">
            <span class="market-name">{{ res.market }}</span>
            <span class="target-info">{{ res.target_quarter }} ({{ res.target_stocks_count }}종목)</span>
          </div>
          
          <div class="market-stats">
            <div class="stat-row">
              <span>총 거래일</span>
              <strong>{{ res.total_trading_days }}일</strong>
            </div>
            <div class="stat-row">
              <span>누락 발생일</span>
              <strong :class="getGapColor(res.missing_days_count)">
                {{ res.missing_days_count }}일
              </strong>
            </div>
          </div>

          <div v-if="res.missing_days_count > 0" class="missing-dates">
            <p>⚠️ 누락일 상세:</p>
            <div class="date-tags">
              <span v-for="day in res.missing_days" :key="day" class="date-tag">{{ day }}</span>
            </div>
          </div>
          <div v-else class="success-msg">
            ✅ 모든 데이터가 정상입니다.
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gap-inspector {
  background: white;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  overflow: hidden;
}

.panel-header {
  padding: 1.2rem;
  border-bottom: 1px solid #f1f5f9;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #f8fafc;
}

.panel-header h3 {
  margin: 0;
  font-size: 1rem;
  color: #334155;
}

.controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.date-input {
  padding: 0.4rem;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  font-family: inherit;
}

.check-btn {
  padding: 0.4rem 1rem;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
}

.check-btn:disabled {
  background: #94a3b8;
  cursor: wait;
}

.panel-body {
  padding: 1.5rem;
}

.empty-state {
  text-align: center;
  color: #94a3b8;
  padding: 2rem;
}

.result-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.market-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 1rem;
  flex-direction: column;
  justify-content: space-between;
}

.market-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  border-bottom: 1px solid #f1f5f9;
  padding-bottom: 0.5rem;
}

.market-name {
  font-weight: 700;
  font-size: 1.1rem;
  color: #1e293b;
}

.target-info {
  font-size: 0.85rem;
  color: #64748b;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.5rem;
  font-size: 0.95rem;
}

.text-red { color: #ef4444; }
.text-green { color: #10b981; }

.missing-dates {
  margin-top: 1rem;
  background: #fff1f2;
  padding: 0.8rem;
  border-radius: 6px;
}

.missing-dates p {
  margin: 0 0 0.5rem 0;
  font-size: 0.85rem;
  font-weight: 600;
  color: #be123c;
}

.date-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.date-tag {
  background: white;
  border: 1px solid #fecdd3;
  color: #be123c;
  font-size: 0.75rem;
  padding: 2px 6px;
  border-radius: 4px;
}

.success-msg {
  margin-top: 0.8rem;
  text-align: center;
  color: #10b981;
  font-weight: 500;
  background: #ecfdf5;
  padding: 0.5rem;
  border-radius: 6px;
  font-size: 0.9rem;
}

/* 반응형: 화면이 좁아지면 세로로 변경 */
@media (max-width: 768px) {
  .result-grid {
    grid-template-columns: 1fr;
  }
}
</style>