<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useBackupStore } from '@/stores/backupStore'

const backupStore = useBackupStore()
const selectedMarket = ref<'kdms' | 'usdms'>('kdms')
const backupTag = ref('manual')
const createSuccessMsg = ref<string | null>(null)
const createErrorMsg = ref<string | null>(null)

// 복구 관련 반응형 변수들
const showRestoreModal = ref(false)
const selectedBackup = ref<any | null>(null)
const confirmInput = ref('')
const restoreSuccessMsg = ref<string | null>(null)
const restoreErrorMsg = ref<string | null>(null)
const restoreLoading = ref(false)
const validationReport = ref<any | null>(null)

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
    const res = await backupStore.createBackup(selectedMarket.value, backupTag.value)
    createSuccessMsg.value = `백업 성공: ${res.filename} (${formatBytes(res.size_bytes)})`
    backupTag.value = 'manual'
  } catch (err: any) {
    createErrorMsg.value = err.message || '백업 생성에 실패했습니다.'
  }
}

// 복구 모달 제어
const openRestoreModal = (item: any) => {
  selectedBackup.value = item
  confirmInput.value = ''
  restoreSuccessMsg.value = null
  restoreErrorMsg.value = null
  validationReport.value = null
  showRestoreModal.value = true
}

const closeRestoreModal = () => {
  if (restoreLoading.value) return
  showRestoreModal.value = false
  selectedBackup.value = null
}

const handleRestoreBackup = async () => {
  if (!selectedBackup.value) return
  if (confirmInput.value !== 'RESTORE LOCAL DB') return

  restoreLoading.value = true
  restoreSuccessMsg.value = null
  restoreErrorMsg.value = null
  validationReport.value = null

  try {
    const res = await backupStore.restoreBackup(
      selectedBackup.value.market,
      selectedBackup.value.tag,
      selectedBackup.value.filename,
      confirmInput.value
    )
    restoreSuccessMsg.value = '물리 볼륨 복구 및 컨테이너 재기동이 완료되었습니다.'
    validationReport.value = res.validation_results
    await loadBackupData()
  } catch (err: any) {
    restoreErrorMsg.value = err.message || '복구 중 오류가 발생했습니다.'
  } finally {
    restoreLoading.value = false
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

const formatNumber = (num: number) => {
  if (num === undefined || num === null) return '0'
  return num.toLocaleString()
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
          <strong>서버 PC에서의 물리 스냅샷 직접 백업 및 복구 기능은 강제 비활성화</strong>됩니다.
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
          물리 볼륨 백업 및 복구를 수행할 수 있습니다.
        </p>
      </div>
    </div>

    <div class="backup-grid">
      <!-- 2. 백업 기동 카드 (개발 전용) -->
      <section class="control-card card-glassmorphism">
        <h2>⚡ 물리 볼륨 스냅샷 생성</h2>
        <p class="card-desc">로컬에 마운트된 DB 파일 시스템 전체를 타르볼(tar.gz)로 아카이빙합니다.</p>
        
        <!-- 시장 선택 UI 추가 -->
        <div class="form-group">
          <label>대상 데이터베이스 시장</label>
          <div class="market-radio-group">
            <label class="radio-label">
              <input 
                type="radio" 
                v-model="selectedMarket" 
                value="kdms" 
                :disabled="backupStore.currentEnv === 'server' || backupStore.loading" 
              />
              <span class="radio-custom"></span>
              🇰🇷 KDMS (한국)
            </label>
            <label class="radio-label">
              <input 
                type="radio" 
                v-model="selectedMarket" 
                value="usdms" 
                :disabled="backupStore.currentEnv === 'server' || backupStore.loading" 
              />
              <span class="radio-custom"></span>
              🇺🇸 USDMS (미국)
            </label>
          </div>
        </div>

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
                <th>대상 시장</th>
                <th>식별 태그</th>
                <th>파일명</th>
                <th>용량</th>
                <th>검증 상태</th>
                <th>작업</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in backupStore.backups" :key="item.path">
                <td class="cell-date">{{ formatDate(item.created_at) }}</td>
                <td>
                  <span class="market-badge" :class="item.market">
                    {{ item.market?.toUpperCase() }}
                  </span>
                </td>
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
                <td>
                  <button 
                    class="btn-restore" 
                    @click="openRestoreModal(item)" 
                    :disabled="backupStore.currentEnv === 'server' || backupStore.loading || !item.verified"
                  >
                    🔄 복구 실행
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <!-- 4. 복구 확인 및 검증 결과 모달 -->
    <transition name="fade">
      <div v-if="showRestoreModal" class="modal-backdrop" @click.self="closeRestoreModal">
        <div class="modal-content card-glassmorphism">
          <div class="modal-header">
            <h3>⚠️ 로컬 DB 물리 볼륨 복구</h3>
            <button class="btn-close" @click="closeRestoreModal" :disabled="restoreLoading">✕</button>
          </div>
          
          <div class="modal-body">
            <p class="warning-text">
              선택한 백업 파일 <strong>{{ selectedBackup?.filename }}</strong> 으로 <strong>{{ selectedBackup?.market?.toUpperCase() }} DB</strong> 데이터를 복구합니다.<br/>
              복구 시 <strong>현재 {{ selectedBackup?.market?.toUpperCase() }} DB의 데이터가 완전히 덮어써지며, 작업 도중 관련 DB 및 API 백엔드 컨테이너들이 중지 및 재기동</strong>됩니다. 이 작업은 취소할 수 없습니다.
            </p>
            
            <div v-if="!validationReport && !restoreSuccessMsg" class="confirm-step">
              <p class="instruction">
                안전 장치 작동: 오작동 및 오제어 방지를 위해 아래 입력창에 정확히 <strong class="highlight">RESTORE LOCAL DB</strong>를 입력해 주십시오.
              </p>
              <input 
                id="confirm-input"
                type="text" 
                v-model="confirmInput" 
                placeholder="RESTORE LOCAL DB" 
                :disabled="restoreLoading"
                class="confirm-input"
              />
            </div>

            <!-- 로딩 상태 표시 -->
            <div v-if="restoreLoading" class="loading-status">
              <span class="spinner large"></span>
              <p>물리 스냅샷 복구 및 정합성 자가 진단 실행 중... (최대 1분이 소요될 수 있습니다)</p>
            </div>

            <!-- 에러 메시지 -->
            <div v-if="restoreErrorMsg" class="feedback-msg error">
              {{ restoreErrorMsg }}
            </div>

            <!-- 복구 성공 및 자가 진단 결과 리포트 -->
            <div v-if="validationReport" class="validation-report">
              <div class="feedback-msg success">
                {{ restoreSuccessMsg }}
              </div>
              
              <h4>🔍 DB 정합성 자가 진단 결과 리포트 (StartupValidator)</h4>
              <div class="report-grid-single">
                <!-- KDMS 리포트 -->
                <div v-if="validationReport.kdms" class="report-card" :class="{ healthy: validationReport.kdms?.is_healthy }">
                  <h5>🇰🇷 KDMS (TimescaleDB)</h5>
                  <ul>
                    <li>연결 상태: 
                      <span class="status-indicator" :class="{ ok: validationReport.kdms?.is_connected }">
                        {{ validationReport.kdms?.is_connected ? '연결 성공' : '연결 실패' }}
                      </span>
                    </li>
                    <li>무결성 통과: 
                      <span class="status-indicator" :class="{ ok: validationReport.kdms?.is_healthy }">
                        {{ validationReport.kdms?.is_healthy ? '정상 (Healthy)' : '이상 감지 (Unhealthy)' }}
                      </span>
                    </li>
                    <li>누락 테이블: 
                      <span class="table-list">{{ validationReport.kdms?.missing_tables?.length > 0 ? validationReport.kdms.missing_tables.join(', ') : '없음' }}</span>
                    </li>
                    <li>행 수 미달: 
                      <span v-if="Object.keys(validationReport.kdms?.low_row_tables || {}).length > 0" class="low-rows">
                        <span v-for="(v, k) in validationReport.kdms.low_row_tables" :key="k">
                          {{ k }} ({{ formatNumber(v.actual) }} / {{ formatNumber(v.expected) }}행)
                        </span>
                      </span>
                      <span v-else>없음</span>
                    </li>
                    <li>Hypertable 상태:
                      <span class="status-indicator" :class="{ ok: validationReport.kdms?.hypertable_ok }">
                        {{ validationReport.kdms?.hypertable_ok ? '정상' : '결함' }}
                      </span>
                    </li>
                  </ul>
                </div>

                <!-- USDMS 리포트 -->
                <div v-if="validationReport.usdms" class="report-card" :class="{ healthy: validationReport.usdms?.is_healthy }">
                  <h5>🇺🇸 USDMS (TimescaleDB)</h5>
                  <ul>
                    <li>연결 상태: 
                      <span class="status-indicator" :class="{ ok: validationReport.usdms?.is_connected }">
                        {{ validationReport.usdms?.is_connected ? '연결 성공' : '연결 실패' }}
                      </span>
                    </li>
                    <li>무결성 통과: 
                      <span class="status-indicator" :class="{ ok: validationReport.usdms?.is_healthy }">
                        {{ validationReport.usdms?.is_healthy ? '정상 (Healthy)' : '이상 감지 (Unhealthy)' }}
                      </span>
                    </li>
                    <li>누락 테이블: 
                      <span class="table-list">{{ validationReport.usdms?.missing_tables?.length > 0 ? validationReport.usdms.missing_tables.join(', ') : '없음' }}</span>
                    </li>
                    <li>행 수 미달: 
                      <span v-if="Object.keys(validationReport.usdms?.low_row_tables || {}).length > 0" class="low-rows">
                        <span v-for="(v, k) in validationReport.usdms.low_row_tables" :key="k">
                          {{ k }} ({{ formatNumber(v.actual) }} / {{ formatNumber(v.expected) }}행)
                        </span>
                      </span>
                      <span v-else>없음</span>
                    </li>
                    <li>Hypertable 상태:
                      <span class="status-indicator" :class="{ ok: validationReport.usdms?.hypertable_ok }">
                        {{ validationReport.usdms?.hypertable_ok ? '정상' : '결함' }}
                      </span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <button 
              v-if="!validationReport"
              id="confirm-btn"
              class="btn-danger" 
              :disabled="confirmInput !== 'RESTORE LOCAL DB' || restoreLoading"
              @click="handleRestoreBackup"
            >
              ⚠️ 물리 볼륨 덮어쓰기 복구 실행
            </button>
            <button 
              v-else
              class="btn-primary" 
              @click="closeRestoreModal"
            >
              확인 및 닫기
            </button>
            <button 
              v-if="!validationReport"
              class="btn-secondary" 
              :disabled="restoreLoading" 
              @click="closeRestoreModal"
            >
              취소
            </button>
          </div>
        </div>
      </div>
    </transition>
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

.btn-restore {
  background: rgba(16, 185, 129, 0.15);
  border: 1px solid rgba(16, 185, 129, 0.3);
  color: #34d399;
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-restore:hover:not(:disabled) {
  background: var(--color-emerald);
  color: #ffffff;
}

.btn-restore:disabled {
  opacity: 0.3;
  cursor: not-allowed;
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

/* 모달 스타일 */
.modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(15, 23, 42, 0.8);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 999;
}

.modal-content {
  max-width: 650px;
  width: 90%;
  max-height: 85vh;
  overflow-y: auto;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  padding-bottom: 1rem;
  margin-bottom: 1rem;
}

.modal-header h3 {
  color: #f8fafc;
  margin: 0;
  font-size: 1.25rem;
}

.btn-close {
  background: transparent;
  border: none;
  color: #94a3b8;
  font-size: 1.25rem;
  cursor: pointer;
}

.btn-close:hover {
  color: #f8fafc;
}

.warning-text {
  color: #fca5a5;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 8px;
  padding: 0.85rem 1.25rem;
  font-size: 0.9rem;
  line-height: 1.5;
  margin-bottom: 1.5rem;
}

.confirm-step {
  margin-bottom: 1.5rem;
}

.confirm-step .instruction {
  color: #cbd5e1;
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
}

.confirm-step .highlight {
  color: #f43f5e;
  font-weight: 700;
}

.confirm-input {
  width: 100%;
  background: rgba(15, 23, 42, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 8px;
  color: #ffffff;
  padding: 10px 14px;
  font-size: 1rem;
  text-align: center;
  letter-spacing: 1.5px;
  outline: none;
}

.confirm-input:focus {
  border-color: #f43f5e;
  box-shadow: 0 0 10px rgba(244, 63, 94, 0.3);
}

.loading-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  padding: 2rem 0;
  color: #a5b4fc;
}

.spinner.large {
  width: 32px;
  height: 32px;
  border-width: 3px;
}

/* 자가 진단 결과 리포트 */
.validation-report {
  margin-top: 1.5rem;
  text-align: left;
}

.validation-report h4 {
  font-size: 1.05rem;
  color: #e2e8f0;
  margin: 1.5rem 0 1rem 0;
}

.report-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

@media (max-width: 600px) {
  .report-grid {
    grid-template-columns: 1fr;
  }
}

.report-card {
  background: rgba(15, 23, 42, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 1.25rem;
  border-top: 4px solid var(--color-rose);
}

.report-card.healthy {
  border-top: 4px solid var(--color-emerald);
}

.report-card h5 {
  margin: 0 0 0.75rem 0;
  font-size: 0.95rem;
  color: #f8fafc;
}

.report-card ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  font-size: 0.85rem;
}

.report-card li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #cbd5e1;
}

.status-indicator {
  font-weight: 700;
  color: #f87171;
}

.status-indicator.ok {
  color: #34d399;
}

.table-list, .low-rows {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: monospace;
  color: #94a3b8;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  padding-top: 1rem;
  margin-top: 1.5rem;
}

.btn-danger {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  border: none;
  border-radius: 10px;
  color: #ffffff;
  padding: 10px 18px;
  font-size: 0.9rem;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 4px 10px rgba(239, 68, 68, 0.3);
  transition: all 0.2s;
}

.btn-danger:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 14px rgba(239, 68, 68, 0.4);
}

.btn-danger:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  box-shadow: none;
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: #cbd5e1;
  padding: 10px 18px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  color: #f8fafc;
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
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

/* 시장 구분 스타일 */
.market-radio-group {
  display: flex;
  gap: 1.5rem;
  margin-top: 0.25rem;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #cbd5e1;
  font-size: 0.95rem;
  cursor: pointer;
  user-select: none;
}

.radio-label input[type="radio"] {
  display: none;
}

.radio-custom {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  position: relative;
  display: inline-block;
  transition: all 0.2s;
}

.radio-label input[type="radio"]:checked + .radio-custom {
  border-color: var(--color-indigo);
  background: var(--color-indigo);
}

.radio-label input[type="radio"]:checked + .radio-custom::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 8px;
  height: 8px;
  background: #ffffff;
  border-radius: 50%;
}

.market-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
}

.market-badge.kdms {
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: #60a5fa;
}

.market-badge.usdms {
  background: rgba(245, 158, 11, 0.15);
  border: 1px solid rgba(245, 158, 11, 0.3);
  color: #fbbf24;
}

.report-grid-single {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}


/* 트랜지션 */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>
