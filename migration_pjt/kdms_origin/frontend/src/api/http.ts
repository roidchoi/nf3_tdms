// src/api/http.ts
import axios from 'axios'

// Vite 프록시(/api)를 타도록 설정
const instance = axios.create({
  baseURL: '/api/v1', // API 프리픽스 (백엔드 router prefix와 일치)
  timeout: 180000, // 180초 타임아웃
  headers: {
    'Content-Type': 'application/json',
  }
})

// 응답 인터셉터 (에러 처리 공통화)
instance.interceptors.response.use(
  (response) => response,
  (error) => {
    const msg = error.response?.data?.detail || error.message
    console.error(`[API Error] ${msg}`)
    return Promise.reject(error)
  }
)

export default instance