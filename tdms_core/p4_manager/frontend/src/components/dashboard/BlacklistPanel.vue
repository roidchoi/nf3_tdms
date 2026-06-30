<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useHealthStore } from '@/stores/healthStore'
import type { BlacklistItem } from '@/stores/healthStore'

const healthStore = useHealthStore()
const showConfirmModal = ref(false)
const selectedItem = ref<BlacklistItem | null>(null)
const submitting = ref(false)
const errorMessage = ref('')

onMounted(async () => {
  await healthStore.fetchBlacklist()
})

const triggerRelease = (item: BlacklistItem) => {
  selectedItem.value = item
  errorMessage.value = ''
  showConfirmModal.value = true
}

const handleConfirmRelease = async () => {
  if (!selectedItem.value) return
  
  submitting.value = true
  errorMessage.value = ''
  try {
    await healthStore.releaseBlacklist(selectedItem.value.cik)
    showConfirmModal.value = false
    selectedItem.value = null
  } catch (err: any) {
    errorMessage.value = err.message || '차단 해제 중 오류가 발생했습니다.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="blacklist-panel-container">
    <div class="header-row">
      <h3>🇺🇸 CIK 수집 차단 리스트 (Blacklist)</h3>
      <button class="refresh-btn" @click="healthStore.fetchBlacklist" :disabled="healthStore.loadingBlacklist">
        🔄 갱신
      </button>
    </div>

    <!-- 오프라인 상태일 때 -->
    <div v-if="healthStore.blacklistOffline" class="offline-warning">
      ⚠️ 미국 수집 서버(USDMS) 오프라인 상태로 블랙리스트 조회가 불가능합니다.
    </div>

    <!-- 로딩 상태 -->
    <div v-else-if="healthStore.loadingBlacklist" class="loading-state">
      <span class="spinner"></span> 블랙리스트 조회 중...
    </div>

    <!-- 데이터가 없을 때 -->
    <div v-else-if="healthStore.blacklist.length === 0" class="empty-state">
      현재 수집 차단된 종목(CIK)이 없습니다. 시스템이 정상 기동 중입니다.
    </div>

    <!-- 블랙리스트 테이블 테이블 -->
    <div v-else class="table-wrapper">
      <table class="blacklist-table">
        <thead>
          <tr>
            <th>CIK</th>
            <th>티커 (Ticker)</th>
            <th>차단 사유 코드</th>
            <th>상세 사유</th>
            <th>상태</th>
            <th>제어</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in healthStore.blacklist" :key="item.cik">
            <td class="cik-col">{{ item.cik }}</td>
            <td class="ticker-col">{{ item.ticker || '-' }}</td>
            <td>
              <span class="reason-badge">{{ item.reason_cd }}</span>
            </td>
            <td class="detail-col" :title="item.detail">{{ item.detail }}</td>
            <td>
              <span class="status-indicator-dot"></span> Blocked
            </td>
            <td>
              <button class="release-btn" @click="triggerRelease(item)">
                차단 해제
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 차단 해제 재컨펌 모달 -->
    <div v-if="showConfirmModal && selectedItem" class="modal-overlay">
      <div class="modal-card">
        <div class="modal-header">
          <span class="warn-icon">⚠️</span>
          <h3>수집 차단 해제 승인</h3>
        </div>
        <p class="warning-text">
          선택하신 CIK <strong>[{{ selectedItem.cik }}]</strong> (티커: {{ selectedItem.ticker || '-' }})의 수집 차단을 해제하시겠습니까?
        </p>
        <p class="sub-text">
          승인 시 다음 일일 데이터 수집 스케줄러 기동 시점에 해당 종목의 수집이 재시도됩니다. (실패 횟수가 0으로 초기화됩니다.)
        </p>

        <p v-if="errorMessage" class="error-msg">{{ errorMessage }}</p>

        <div class="modal-actions">
          <button 
            class="cancel-btn" 
            @click="showConfirmModal = false"
            :disabled="submitting"
          >
            취소
          </button>
          <button 
            class="confirm-btn danger" 
            @click="handleConfirmRelease"
            :disabled="submitting"
          >
            <span v-if="submitting" class="mini-spinner"></span>
            차단 해제 승인
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.blacklist-panel-container {
  background: var(--card-bg, rgba(30, 41, 59, 0.45));
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 24px;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-row h3 {
  margin: 0;
  font-size: 1.15rem;
  color: var(--color-light, #f8fafc);
}

.refresh-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #cbd5e1;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.refresh-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
}

.offline-warning {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: #f87171;
  border-radius: 8px;
  padding: 14px;
  font-size: 0.85rem;
  text-align: center;
}

.loading-state, .empty-state {
  text-align: center;
  padding: 40px;
  color: var(--color-muted, #94a3b8);
  font-size: 0.9rem;
}

.table-wrapper {
  overflow-x: auto;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.blacklist-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 0.85rem;
}

.blacklist-table th, .blacklist-table td {
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.blacklist-table th {
  background: rgba(255, 255, 255, 0.02);
  color: #94a3b8;
  font-weight: 500;
}

.blacklist-table tbody tr:hover {
  background: rgba(255, 255, 255, 0.02);
}

.cik-col {
  font-family: monospace;
  color: var(--color-indigo, #818cf8);
}

.ticker-col {
  font-weight: 600;
  color: #fff;
}

.reason-badge {
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid rgba(245, 158, 11, 0.2);
  color: var(--color-amber, #fbbf24);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
}

.detail-col {
  color: #94a3b8;
  max-width: 250px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-indicator-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #f87171;
  margin-right: 6px;
  vertical-align: middle;
  box-shadow: 0 0 6px #f87171;
}

.release-btn {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: #f87171;
  padding: 5px 12px;
  border-radius: 4px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.release-btn:hover {
  background: #ef4444;
  color: #fff;
}

/* 모달 양식 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(15, 23, 42, 0.7);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999;
}

.modal-card {
  background: rgba(30, 41, 59, 0.9);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 12px;
  padding: 28px;
  width: 440px;
  max-width: 90%;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
  animation: modalEnter 0.2s cubic-bezier(0.16, 1, 0.3, 1) both;
}

@keyframes modalEnter {
  from { transform: scale(0.95); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.warn-icon {
  font-size: 1.5rem;
}

.modal-card h3 {
  margin: 0;
  font-size: 1.15rem;
  color: #fff;
}

.warning-text {
  color: #f1f5f9;
  font-size: 0.9rem;
  line-height: 1.5;
  margin-bottom: 12px;
}

.sub-text {
  color: #94a3b8;
  font-size: 0.8rem;
  line-height: 1.4;
  margin-bottom: 20px;
}

.error-msg {
  color: #f87171;
  font-size: 0.8rem;
  margin-bottom: 16px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.cancel-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #cbd5e1;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 0.85rem;
  cursor: pointer;
}

.cancel-btn:hover {
  background: rgba(255, 255, 255, 0.1);
}

.confirm-btn.danger {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  border: none;
  color: #fff;
  padding: 8px 18px;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2);
}

.confirm-btn.danger:hover {
  filter: brightness(1.1);
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.2);
  border-radius: 50%;
  border-top-color: var(--color-indigo, #6366f1);
  animation: spin 0.8s linear infinite;
  vertical-align: middle;
  margin-right: 6px;
}

.mini-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255,255,255,0.2);
  border-radius: 50%;
  border-top-color: #fff;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
