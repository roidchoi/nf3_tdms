<script setup lang="ts">
defineProps<{
  title: string;
  icon: string;
  value: string | number;
  subValue?: string;
  status?: 'good' | 'warning' | 'danger' | 'neutral'; // 상태별 색상
}>()
</script>

<template>
  <div class="stat-card">
    <div class="icon-wrapper" :class="status || 'neutral'">
      {{ icon }}
    </div>
    <div class="content">
      <h3 class="title">{{ title }}</h3>
      <div class="value">{{ value }}</div>
      <div v-if="subValue" class="sub-value">{{ subValue }}</div>
    </div>
  </div>
</template>

<style scoped>
.stat-card {
  background: white;
  padding: 1.5rem;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  display: flex;
  align-items: center;
  gap: 1.2rem;
  border: 1px solid #e2e8f0;
}

.icon-wrapper {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
}

.icon-wrapper.neutral { background: #f1f5f9; color: #64748b; }
.icon-wrapper.good { background: #ecfdf5; color: #10b981; }
.icon-wrapper.warning { background: #fffbeb; color: #f59e0b; }
.icon-wrapper.danger { background: #fef2f2; color: #ef4444; }

.content {
  display: flex;
  flex-direction: column;
}

.title {
  margin: 0;
  font-size: 0.85rem;
  color: #64748b;
  font-weight: 500;
}

.value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #1e293b;
  margin-top: 2px;
}

.sub-value {
  font-size: 0.8rem;
  color: #94a3b8;
  margin-top: 2px;
}
</style>