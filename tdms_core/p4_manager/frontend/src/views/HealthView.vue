<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useHealthStore } from '@/stores/healthStore'
import MilestoneTimeline from '@/components/dashboard/MilestoneTimeline.vue'
import BlacklistPanel from '@/components/dashboard/BlacklistPanel.vue'

const healthStore = useHealthStore()
const activeMarketTab = ref<'kr' | 'us'>('kr')

// 갭 검색 날짜 범위
const getTodayStr = () => new Date().toISOString().split('T')[0]
const krStartDate = ref(getTodayStr())
const krEndDate = ref(getTodayStr())
const usStartDate = ref(getTodayStr())
const usEndDate = ref(getTodayStr())

onMounted(async () => {
  // 신선도 초기 패치
  await Promise.all([
    healthStore.fetchFreshness('kr'),
    healthStore.fetchFreshness('us'),
    healthStore.fetchGaps('kr', krStartDate.value, krEndDate.value),
    healthStore.fetchGaps('us', usStartDate.value, usEndDate.value)
  ])
})

const handleSearchGaps = async (market: 'kr' | 'us') => {
  if (market === 'kr') {
    await healthStore.fetchGaps('kr', krStartDate.value, krEndDate.value)
  } else {
    await healthStore.fetchGaps('us', usStartDate.value, usEndDate.value)
  }
}

const handleRefreshAll = async () => {
  await Promise.all([
    healthStore.fetchFreshness('kr'),
    healthStore.fetchFreshness('us'),
    handleSearchGaps('kr'),
    handleSearchGaps('us')
  ])
}
</script>

<template>
  <div class="health-view-wrapper">
    <!-- 대시보드 도구 모음 -->
    <div class="dashboard-toolbar">
      <div class="toolbar-title">
        <h2>🏥 Integrated System Health Audit</h2>
        <span class="badge">Live Monitoring</span>
      </div>
      <button class="refresh-all-btn" @click="handleRefreshAll">
        🔄 전체 새로고침
      </button>
    </div>

    <!-- 1. 최상단 신선도 카드 레이아웃 -->
    <section class="freshness-grid">
      <!-- 한국 시장 신선도 -->
      <div 
        class="freshness-card" 
        :class="[
          healthStore.krFreshness?.status.toLowerCase() || 'red',
          { 'is-offline': healthStore.krFreshness?.offline }
        ]"
      >
        <div class="card-header">
          <div class="market-info">
            <span class="flag">🇰🇷</span>
            <span>South Korea (KDMS)</span>
          </div>
          <span class="status-indicator">
            {{ healthStore.krFreshness?.offline ? 'OFFLINE' : (healthStore.krFreshness?.status || 'RED') }}
          </span>
        </div>
        <div class="card-body" v-if="healthStore.krFreshness">
          <div class="metric-row">
            <span class="label">최종 거래정리일</span>
            <span class="value">{{ healthStore.krFreshness.latest_trading_date || '-' }}</span>
          </div>
          <div class="metric-row">
            <span class="label">수집 대상 종목</span>
            <span class="value">{{ healthStore.krFreshness.total_active_stocks || 0 }}개</span>
          </div>
          <div class="metric-row">
            <span class="label">수집 완료율</span>
            <span class="value">
              {{ ((healthStore.krFreshness.daily_coverage_ratio || 0) * 100).toFixed(2) }}%
            </span>
          </div>
          <div class="progress-bar">
            <div 
              class="progress-fill" 
              :style="{ width: `${(healthStore.krFreshness.daily_coverage_ratio || 0) * 100}%` }"
            ></div>
          </div>
        </div>
      </div>

      <!-- 미국 시장 신선도 -->
      <div 
        class="freshness-card" 
        :class="[
          healthStore.usFreshness?.status.toLowerCase() || 'red',
          { 'is-offline': healthStore.usFreshness?.offline }
        ]"
      >
        <div class="card-header">
          <div class="market-info">
            <span class="flag">🇺🇸</span>
            <span>United States (USDMS)</span>
          </div>
          <span class="status-indicator">
            {{ healthStore.usFreshness?.offline ? 'OFFLINE' : (healthStore.usFreshness?.status || 'RED') }}
          </span>
        </div>
        <div class="card-body" v-if="healthStore.usFreshness">
          <div class="metric-row">
            <span class="label">최종 거래정리일</span>
            <span class="value">{{ healthStore.usFreshness.latest_trading_date || '-' }}</span>
          </div>
          <div class="metric-row">
            <span class="label">수집 대상 종목</span>
            <span class="value">{{ healthStore.usFreshness.total_active_stocks || 0 }}개</span>
          </div>
          <div class="metric-row">
            <span class="label">수집 완료율</span>
            <span class="value">
              {{ ((healthStore.usFreshness.daily_coverage_ratio || 0) * 100).toFixed(2) }}%
            </span>
          </div>
          <div class="progress-bar">
            <div 
              class="progress-fill" 
              :style="{ width: `${(healthStore.usFreshness.daily_coverage_ratio || 0) * 100}%` }"
            ></div>
          </div>
        </div>
      </div>
    </section>

    <!-- 2. 시장별 탭 네비게이션 -->
    <div class="market-tabs">
      <button 
        class="market-tab-btn"
        :class="{ active: activeMarketTab === 'kr' }"
        @click="activeMarketTab = 'kr'"
      >
        🇰🇷 대한민국 (KDMS)
      </button>
      <button 
        class="market-tab-btn"
        :class="{ active: activeMarketTab === 'us' }"
        @click="activeMarketTab = 'us'"
      >
        🇺🇸 미국 (USDMS)
      </button>
    </div>

    <!-- 3. 탭별 상세 패널 콘텐츠 -->
    <div class="market-panel-content">
      <!-- [1] 한국 시장 모니터링 패널 -->
      <div v-if="activeMarketTab === 'kr'" class="sub-panel">
        <div class="audit-grid">
          <!-- 갭 검출 정보 -->
          <div class="gap-audit-box">
            <div class="box-header">
              <h4>🔍 수집 누락 갭 (Gaps) 정밀 분석</h4>
              <div class="date-selector">
                <input type="date" v-model="krStartDate" />
                <span>~</span>
                <input type="date" v-model="krEndDate" />
                <button class="search-btn" @click="handleSearchGaps('kr')">검색</button>
              </div>
            </div>

            <!-- 오프라인 상태 -->
            <div v-if="healthStore.krGaps?.offline" class="error-state">
              한국 수집 서버(KDMS)와의 통신이 원활하지 않습니다. (오프라인 상태)
            </div>
            
            <!-- 로딩 상태 -->
            <div v-else-if="healthStore.loadingGaps" class="loading-state">
              <span class="spinner"></span> 갭 목록 검색 중...
            </div>

            <!-- 갭 테이블 -->
            <div v-else class="table-wrapper">
              <table class="gap-table">
                <thead>
                  <tr>
                    <th>날짜</th>
                    <th>상태</th>
                    <th>총 대상</th>
                    <th>유효 대상</th>
                    <th>누락 수</th>
                    <th>누락 종목 (티커)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(gap, idx) in healthStore.krGaps?.gaps" :key="idx">
                    <td>{{ gap.date }}</td>
                    <td>
                      <span class="status-dot" :class="gap.status.toLowerCase()"></span>
                      {{ gap.status }}
                    </td>
                    <td>{{ gap.total_targets }}</td>
                    <td>{{ gap.valid_targets }}</td>
                    <td :class="{ 'has-gaps': gap.missing_count > 0 }">
                      {{ gap.missing_count }}
                    </td>
                    <td class="missing-items-col">
                      <template v-if="gap.missing_items.length > 0">
                        <span 
                          v-for="item in gap.missing_items.slice(0, 5)" 
                          :key="item" 
                          class="missing-ticker"
                        >
                          {{ item }}
                        </span>
                        <span v-if="gap.missing_items.length > 5" class="more-badge">
                          +{{ gap.missing_items.length - 5 }}
                        </span>
                      </template>
                      <template v-else>-</template>
                    </td>
                  </tr>
                  <tr v-if="!healthStore.krGaps?.gaps.length">
                    <td colspan="6" class="no-data">조회된 기간 내 갭 검출 데이터가 없습니다.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- 한국 마일스톤 -->
          <div class="milestone-box">
            <MilestoneTimeline />
          </div>
        </div>
      </div>

      <!-- [2] 미국 시장 모니터링 패널 -->
      <div v-else class="sub-panel">
        <div class="audit-grid">
          <!-- 갭 검출 정보 -->
          <div class="gap-audit-box">
            <div class="box-header">
              <h4>🔍 수집 누락 갭 (Gaps) 정밀 분석</h4>
              <div class="date-selector">
                <input type="date" v-model="usStartDate" />
                <span>~</span>
                <input type="date" v-model="usEndDate" />
                <button class="search-btn" @click="handleSearchGaps('us')">검색</button>
              </div>
            </div>

            <!-- 오프라인 상태 -->
            <div v-if="healthStore.usGaps?.offline" class="error-state">
              미국 수집 서버(USDMS)와의 통신이 원활하지 않습니다. (오프라인 상태)
            </div>

            <!-- 로딩 상태 -->
            <div v-else-if="healthStore.loadingGaps" class="loading-state">
              <span class="spinner"></span> 갭 목록 검색 중...
            </div>

            <!-- 갭 테이블 -->
            <div v-else class="table-wrapper">
              <table class="gap-table">
                <thead>
                  <tr>
                    <th>날짜</th>
                    <th>상태</th>
                    <th>총 대상</th>
                    <th>유효 대상</th>
                    <th>누락 수</th>
                    <th>누락 종목 (티커)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(gap, idx) in healthStore.usGaps?.gaps" :key="idx">
                    <td>{{ gap.date }}</td>
                    <td>
                      <span class="status-dot" :class="gap.status.toLowerCase()"></span>
                      {{ gap.status }}
                    </td>
                    <td>{{ gap.total_targets }}</td>
                    <td>{{ gap.valid_targets }}</td>
                    <td :class="{ 'has-gaps': gap.missing_count > 0 }">
                      {{ gap.missing_count }}
                    </td>
                    <td class="missing-items-col">
                      <span class="info-badge">티커 목록 미지원 (블랙리스트 조회 필요)</span>
                    </td>
                  </tr>
                  <tr v-if="!healthStore.usGaps?.gaps.length">
                    <td colspan="6" class="no-data">조회된 기간 내 갭 검출 데이터가 없습니다.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- 미국 블랙리스트 제어 패널 -->
          <div class="blacklist-box">
            <BlacklistPanel />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.health-view-wrapper {
  color: #f8fafc;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.dashboard-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  padding-bottom: 16px;
}

.toolbar-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-title h2 {
  margin: 0;
  font-size: 1.4rem;
  font-weight: 600;
  background: linear-gradient(to right, #fff, #94a3b8);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.badge {
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.2);
  color: var(--color-emerald, #10b981);
  font-size: 0.75rem;
  padding: 2px 8px;
  border-radius: 9999px;
  font-weight: 500;
}

.refresh-all-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #f1f5f9;
  font-size: 0.85rem;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.refresh-all-btn:hover {
  background: rgba(255, 255, 255, 0.1);
}

/* 1. 신선도 그리드 */
.freshness-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 20px;
}

.freshness-card {
  background: rgba(30, 41, 59, 0.45);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: relative;
  overflow: hidden;
  transition: all 0.3s ease;
}

.freshness-card::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
}

.freshness-card.green::after { background-color: var(--color-emerald); }
.freshness-card.yellow::after { background-color: var(--color-amber); }
.freshness-card.red::after { background-color: var(--color-rose); }
.freshness-card.is-offline::after { background-color: var(--color-slate); }

.freshness-card.is-offline {
  opacity: 0.65;
  filter: grayscale(40%);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.market-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: #fff;
  font-size: 1.05rem;
}

.status-indicator {
  font-size: 0.75rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
}

.green .status-indicator { background: rgba(16, 185, 129, 0.12); color: var(--color-emerald); }
.yellow .status-indicator { background: rgba(245, 158, 11, 0.12); color: var(--color-amber); }
.red .status-indicator { background: rgba(244, 63, 94, 0.12); color: var(--color-rose); }
.is-offline .status-indicator { background: rgba(100, 116, 139, 0.12); color: var(--color-slate); }

.card-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.metric-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
}

.metric-row .label {
  color: #94a3b8;
}

.metric-row .value {
  color: #fff;
  font-weight: 500;
}

.progress-bar {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 4px;
  height: 6px;
  overflow: hidden;
  margin-top: 4px;
}

.progress-fill {
  height: 100%;
  border-radius: 4px;
}

.green .progress-fill { background-color: var(--color-emerald); }
.yellow .progress-fill { background-color: var(--color-amber); }
.red .progress-fill { background-color: var(--color-rose); }
.is-offline .progress-fill { background-color: var(--color-slate); }

/* 2. 시장 탭 */
.market-tabs {
  display: flex;
  gap: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  padding-bottom: 1px;
  margin-top: 10px;
}

.market-tab-btn {
  background: none;
  border: none;
  color: #94a3b8;
  font-size: 0.95rem;
  font-weight: 500;
  padding: 10px 20px;
  cursor: pointer;
  position: relative;
  transition: all 0.2s ease;
}

.market-tab-btn:hover {
  color: #fff;
}

.market-tab-btn.active {
  color: #fff;
  font-weight: 600;
}

.market-tab-btn.active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 0;
  width: 100%;
  height: 2px;
  background-color: var(--color-indigo);
}

/* 3. 상세 패널 */
.audit-grid {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.gap-audit-box {
  background: rgba(30, 41, 59, 0.45);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 24px;
}

.box-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 20px;
}

.box-header h4 {
  margin: 0;
  font-size: 1.1rem;
  color: #fff;
}

.date-selector {
  display: flex;
  align-items: center;
  gap: 10px;
}

.date-selector input[type="date"] {
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  padding: 6px 12px;
  color: #fff;
  font-size: 0.85rem;
}

.date-selector input[type="date"]:focus {
  outline: none;
  border-color: var(--color-indigo);
}

.search-btn {
  background: var(--color-indigo);
  border: none;
  color: #fff;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.search-btn:hover {
  filter: brightness(1.1);
}

.error-state {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: #f87171;
  border-radius: 8px;
  padding: 14px;
  font-size: 0.85rem;
  text-align: center;
}

.loading-state {
  text-align: center;
  padding: 30px;
  color: #94a3b8;
  font-size: 0.9rem;
}

.table-wrapper {
  overflow-x: auto;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.gap-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 0.85rem;
}

.gap-table th, .gap-table td {
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.gap-table th {
  background: rgba(255, 255, 255, 0.02);
  color: #94a3b8;
  font-weight: 500;
}

.gap-table tbody tr:hover {
  background: rgba(255, 255, 255, 0.02);
}

.gap-table .no-data {
  text-align: center;
  color: #94a3b8;
  padding: 30px;
}

.status-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}

.status-dot.green { background: var(--color-emerald); box-shadow: 0 0 6px var(--color-emerald); }
.status-dot.yellow { background: var(--color-amber); box-shadow: 0 0 6px var(--color-amber); }
.status-dot.red { background: var(--color-rose); box-shadow: 0 0 6px var(--color-rose); }

.has-gaps {
  color: var(--color-rose);
  font-weight: 700;
}

.missing-items-col {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.missing-ticker {
  background: rgba(244, 63, 94, 0.12);
  border: 1px solid rgba(244, 63, 94, 0.2);
  color: #f43f5e;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-family: monospace;
}

.more-badge {
  background: rgba(255, 255, 255, 0.08);
  color: #cbd5e1;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.75rem;
}

.info-badge {
  background: rgba(255, 255, 255, 0.05);
  color: #94a3b8;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.2);
  border-radius: 50%;
  border-top-color: var(--color-indigo);
  animation: spin 0.8s linear infinite;
  vertical-align: middle;
  margin-right: 6px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
