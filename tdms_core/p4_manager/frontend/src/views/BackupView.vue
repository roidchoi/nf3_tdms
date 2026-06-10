<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useBackupStore } from '@/stores/backupStore'

const backupStore = useBackupStore()
const backupTag = ref('manual')
const createSuccessMsg = ref<string | null>(null)
const createErrorMsg = ref<string | null>(null)

const loadBackupData = async () => {
  await backupStore.fetchEnv()
  await backupStore.fetchBackups()
}

onMounted(() => {
  loadBackupData()
})

const handleCreateBackup = async () => {
  createSuccessMsg.value = null
  createErrorMsg.value = null
  try {
    const res = await backupStore.createBackup(backupTag.value)
    createSuccessMsg.value = `백업 성공: ${res.filename} (${formatBytes(res.size_bytes)})`
    backupTag.value = 'manual'
  } catch (err: any) {
    createErrorMsg.value = err.message || '백업 생성에 실패했습니다.'
  }
}

// 바이트 변환 헬퍼
const formatBytes = (bytes: number, decimals = 2) => {
  if (!bytes) return '0 Bytes'
  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i]
}

// 날짜 변환 헬퍼
const formatDate = (isoStr: string) => {
  if (!isoStr) return '-'
  try {
    const d = new Date(isoStr)
    return d.toLocaleString('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  } catch {
    return isoStr
  }
}
</script>

<template>
  <div class="backup-view-container">
    <!-- 1. 환경별 정보 배너 및 경고 시스템 -->
    <div 
      v-if="backupStore.currentEnv === 'server'" 
      class="warning-banner server-banner"
    >
      <span class="warning-icon">⚠️</span>
      <div class="banner-body">
        <h3>서버 PC 환경 (스냅샷 생성 비활성화)</h3>
        <p>
          본 장비는 실서버 환경(운영계)으로 감지되었습니다. 실서버 I/O 과부하 및 정합성 교란을 차단하기 위해 
          <strong>서버 PC에서의 물리 스냅샷 직접 백업 기능은 강제 비활성화</strong>됩니다.
          서버 DB 백업은 개발 PC의 수시 Pull 동기화를 이용해 안전하게 진행하십시오.
        </p>
      </div>
    </div>

    <div 
      v-else-if="backupStore.currentEnv === 'dev'" 
      class="info-banner dev-banner"
    >
      <span class="info-icon">ℹ️</span>
      <div class="banner-body">
        <h3>개발 PC 환경 (백업 허브 활성화)</h3>
        <p>
          개발 PC 환경으로 감지되었습니다. 로컬 TimescaleDB 데이터 볼륨 물리 압축(tar.gz) 기반의 
          물리 볼륨 백업을 생성할 수 있습니다.
        </p>
      </div>
    </div>

    <div class="backup-grid">
      <!-- 2. 백업 기동 카드 (개발 전용) -->
      <section class="control-card card-glassmorphism">
        <h2>⚡ 물리 볼륨 스냅샷 생성</h2>
        <p class="card-desc">로컬에 마운트된 DB 파일 시스템 전체를 타르볼(tar.gz)로 아카이빙합니다.</p>
        
        <div class="form-group">
          <label for="backup-tag">백업 식별 태그</label>
          <input 
            id="backup-tag"
            type="text" 
            v-model="backupTag" 
            placeholder="예: milestone_1, daily_routine" 
            :disabled="backupStore.currentEnv === 'server' || backupStore.loading"
          />
        </div>

        <button 
          class="btn-primary" 
          @click="handleCreateBackup" 
          :disabled="backupStore.currentEnv === 'server' || backupStore.loading || !backupTag.trim()"
        >
          <span v-if="backupStore.loading" class="spinner"></span>
          <span v-else>💾 스냅샷 백업 실행</span>
        </button>

        <!-- 피드백 메시지 -->
        <transition name="fade">
          <div v-if="createSuccessMsg" class="feedback-msg success">
            {{ createSuccessMsg }}
          </div>
        </transition>
        <transition name="fade">
          <div v-if="createErrorMsg" class="feedback-msg error">
            {{ createErrorMsg }}
          </div>
        </transition>
      </section>

      <!-- 3. 백업 보관소 이력 카드 -->
      <section class="history-card card-glassmorphism">
        <div class="history-header">
          <h2>📁 로컬 백업 스냅샷 이력</h2>
          <button class="btn-refresh" @click="loadBackupData" :disabled="backupStore.loading">
            🔄 새로고침
          </button>
        </div>

        <div v-if="backupStore.loading && backupStore.backups.length === 0" class="loading-placeholder">
          <span class="spinner"></span>
          <span>스냅샷 목록 조회 중...</span>
        </div>

        <div v-else-if="backupStore.backups.length === 0" class="empty-placeholder">
          <span>보관소에 백업 스냅샷이 존재하지 않습니다.</span>
        </div>

        <div v-else class="table-responsive">
          <table class="backup-table">
            <thead>
              <tr>
                <th>생성일시</th>
                <th>식별 태그</th>
                <th>파일명</th>
                <th>용량</th>
                <th>검증 상태</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in backupStore.backups" :key="item.path">
                <td class="cell-date">{{ formatDate(item.created_at) }}</td>
                <td><span class="tag-badge">{{ item.tag }}</span></td>
                <td class="cell-filename" :title="item.path">{{ item.filename }}</td>
                <td class="cell-size">{{ formatBytes(item.size_bytes) }}</td>
                <td>
                  <span 
                    class="verify-badge" 
                    :class="{ verified: item.verified }"
                  >
                    {{ item.verified ? 'Verified' : 'Invalid' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.backup-view-container {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  width: 100%;
}

/* 배너 공통 */
.warning-banner, .info-banner {
  display: flex;
  gap: 1.25rem;
  padding: 1.25rem 1.5rem;
  border-radius: 16px;
  line-height: 1.5;
  text-align: left;
}

.server-banner {
  background: rgba(244, 63, 94, 0.1);
  border: 1px solid rgba(244, 63, 94, 0.3);
  border-left: 5px solid var(--color-rose);
}

.server-banner h3 {
  color: #fda4af;
  margin: 0 0 0.5rem 0;
  font-size: 1.1rem;
}

.server-banner p {
  color: #fecdd3;
  margin: 0;
  font-size: 0.95rem;
}

.dev-banner {
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.3);
  border-left: 5px solid var(--color-emerald);
}

.dev-banner h3 {
  color: #a7f3d0;
  margin: 0 0 0.5rem 0;
  font-size: 1.1rem;
}

.dev-banner p {
  color: #d1fae5;
  margin: 0;
  font-size: 0.95rem;
}

.warning-icon, .info-icon {
  font-size: 2rem;
  display: flex;
  align-items: center;
}

/* 그리드 */
.backup-grid {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 1.5rem;
}

@media (max-width: 1024px) {
  .backup-grid {
    grid-template-columns: 1fr;
  }
}

/* 글라스모피즘 카드 */
.card-glassmorphism {
  background: rgba(30, 41, 59, 0.45);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 20px;
  padding: 2rem;
  text-align: left;
  display: flex;
  flex-direction: column;
}

.control-card h2, .history-card h2 {
  font-size: 1.35rem;
  color: #f1f5f9;
  margin: 0 0 0.5rem 0;
}

.card-desc {
  color: #94a3b8;
  font-size: 0.9rem;
  margin: 0 0 1.5rem 0;
}

/* 폼 그룹 */
.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
}

.form-group label {
  color: #cbd5e1;
  font-size: 0.85rem;
  font-weight: 600;
}

.form-group input {
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  color: #f8fafc;
  padding: 10px 14px;
  font-size: 0.95rem;
  outline: none;
  transition: all 0.2s;
}

.form-group input:focus {
  border-color: var(--color-indigo);
  box-shadow: 0 0 8px rgba(99, 102, 241, 0.4);
}

.form-group input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 버튼 */
.btn-primary {
  background: linear-gradient(135deg, var(--color-indigo) 0%, #4f46e5 100%);
  border: none;
  border-radius: 12px;
  color: #ffffff;
  padding: 12px;
  font-size: 0.95rem;
  font-weight: 700;
  cursor: pointer;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 0.5rem;
  transition: all 0.2s;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4);
}

.btn-primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  box-shadow: none;
}

.btn-refresh {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #cbd5e1;
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-refresh:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #f8fafc;
}

/* 로딩 스피너 */
.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  border-top-color: #fff;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 피드백 피드 */
.feedback-msg {
  margin-top: 1.25rem;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.85rem;
  line-height: 1.4;
  text-align: left;
}

.feedback-msg.success {
  background: rgba(16, 185, 129, 0.15);
  border: 1px solid rgba(16, 185, 129, 0.3);
  color: #34d399;
}

.feedback-msg.error {
  background: rgba(244, 63, 94, 0.15);
  border: 1px solid rgba(244, 63, 94, 0.3);
  color: #f87171;
}

/* 테이블 보관함 */
.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.loading-placeholder, .empty-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding: 4rem 2rem;
  color: #64748b;
  font-size: 0.95rem;
  background: rgba(15, 23, 42, 0.2);
  border-radius: 12px;
  border: 1px dashed rgba(255, 255, 255, 0.05);
}

.table-responsive {
  width: 100%;
  overflow-x: auto;
}

.backup-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}

.backup-table th {
  padding: 12px 16px;
  color: #94a3b8;
  font-size: 0.85rem;
  font-weight: 700;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  text-transform: uppercase;
}

.backup-table td {
  padding: 14px 16px;
  color: #cbd5e1;
  font-size: 0.9rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.backup-table tbody tr:hover {
  background: rgba(255, 255, 255, 0.02);
}

.cell-date {
  font-family: monospace;
  color: #a5b4fc;
}

.cell-filename {
  font-family: monospace;
  max-width: 200px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #94a3b8;
}

.cell-size {
  font-weight: 600;
  color: #f1f5f9;
}

.tag-badge {
  background: rgba(99, 102, 241, 0.15);
  border: 1px solid rgba(99, 102, 241, 0.3);
  color: #a5b4fc;
  border-radius: 6px;
  padding: 2px 8px;
  font-size: 0.75rem;
  font-weight: 600;
}

.verify-badge {
  border-radius: 6px;
  padding: 2px 8px;
  font-size: 0.75rem;
  font-weight: 700;
  background: rgba(244, 63, 94, 0.15);
  border: 1px solid rgba(244, 63, 94, 0.3);
  color: #f87171;
  display: inline-block;
}

.verify-badge.verified {
  background: rgba(16, 185, 129, 0.15);
  border: 1px solid rgba(16, 185, 129, 0.3);
  color: #34d399;
}

/* 트랜지션 */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>
