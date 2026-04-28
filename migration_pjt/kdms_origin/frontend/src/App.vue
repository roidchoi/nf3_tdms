<script setup lang="ts">
import { RouterView } from 'vue-router'
import MainLayout from '@/components/layout/MainLayout.vue'
</script>

<template>
  <MainLayout>
    <RouterView />
  </MainLayout>
</template>

<style>
/* 전역 스타일 리셋 (기존 내용 유지) */
html, body {
  margin: 0;
  padding: 0;
  font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif;
  background-color: #f1f5f9;
  height: 100%;
}
</style>