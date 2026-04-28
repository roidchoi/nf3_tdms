<script setup lang="ts">
import Sidebar from './AppSidebar.vue'
import Header from './AppHeader.vue'
</script>

<template>
  <div class="layout-wrapper">
    <Sidebar />
    <div class="main-container">
      <Header />
      <main class="content-area">
        <slot />
      </main>
    </div>
  </div>
</template>

<style scoped>
.layout-wrapper {
  display: flex;
  min-height: 100vh;
}

.main-container {
  flex: 1;
  margin-left: 200px; /* 사이드바 너비만큼 여백 */
  display: flex;
  flex-direction: column;
  background-color: #f1f5f9;
}

.content-area {
  flex: 1;
  padding: 2rem;
  overflow-y: auto;
  overflow-x: hidden; /* [추가] 페이지 전체가 가로로 밀리는 현상 방지 */
  max-width: 100%;    /* [추가] 너비 제한 */
}
</style>