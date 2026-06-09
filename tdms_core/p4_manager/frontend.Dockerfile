# 1. Builder Stage
FROM node:20-alpine AS builder

WORKDIR /app

# 의존성 정의 파일 복사 및 설치
COPY tdms_core/p4_manager/frontend/package*.json ./
RUN npm ci

# 소스 복사 및 빌드
COPY tdms_core/p4_manager/frontend/ ./
RUN npm run build

# 2. Production Stage
FROM nginx:1.25-alpine

# Nginx 설정 파일 복사
COPY tdms_core/p4_manager/nginx/nginx.conf /etc/nginx/nginx.conf

# Builder stage의 빌드 아티팩트를 nginx 서빙 폴더로 복사
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

