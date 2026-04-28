<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useHealthStore } from '@/stores/healthStore'
import StatCard from '@/components/health/StatCard.vue'
import GapInspector from '@/components/health/GapInspector.vue'
import MilestoneTimeline from '@/components/health/MilestoneTimeline.vue'

const healthStore = useHealthStore()

onMounted(() => {
  healthStore.fetchDashboardData()
})

// 상태값 계산 (Freshness)
const freshnessStatus = computed(() => {
  if (healthStore.freshness?.is_daily_fresh) return 'good'
  return 'danger'
})
</script>

<template>
  <div class="health-view">
    <div class="stats-grid">
      <StatCard
        title="시세 데이터 최신성"
        icon="⚡"
        :value="healthStore.freshness?.last_daily_dt || '-'"
        :sub-value="`지연: ${healthStore.freshness?.daily_lag_days ?? '-'}일`"
        :status="freshnessStatus"
      />
      <StatCard
        title="재무정보 (PIT)"
        icon="📊"
        :value="healthStore.financials?.latest_stac_yymm || '-'"
        :sub-value="`총 ${healthStore.financials?.distinct_stocks_count.toLocaleString() ?? 0} 종목`"
        status="neutral"
      />
      <StatCard
        title="수정계수 이벤트"
        icon="🔧"
        :value="`${healthStore.factors?.total_events_count.toLocaleString() ?? 0}건`"
        :sub-value="`최근: ${healthStore.factors?.latest_event_dt || '-'}`"
        status="neutral"
      />
    </div>

    <div class="middle-section">
      <GapInspector class="flex-2" />
      <MilestoneTimeline class="flex-1" />
    </div>
  </div>
</template>

<style scoped>
.health-view {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  max-width: 1400px;
  margin: 0 auto;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.5rem;
}

/* [신규] 중단 레이아웃 (Gap:Timeline = 2:1 비율) */
.middle-section {
  display: flex;
  gap: 1.5rem;
  align-items: flex-start;
}

.flex-2 { flex: 2; }
.flex-1 { flex: 1; min-width: 300px; }

/* 반응형 처리 */
@media (max-width: 1024px) {
  .middle-section {
    flex-direction: column;
  }
  .flex-1, .flex-2 { width: 100%; }
}
</style>