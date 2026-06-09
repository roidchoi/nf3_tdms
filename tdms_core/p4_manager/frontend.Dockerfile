FROM nginx:1.25-alpine

# Nginx 설정 파일 복사
COPY tdms_core/p4_manager/nginx/nginx.conf /etc/nginx/nginx.conf

# MVP용 임시 정적 페이지 (Stub)
RUN echo '<!DOCTYPE html><html><head><title>TDMS Manager</title><meta charset="utf-8"></head><body><h1>TDMS Manager Dashboard MVP</h1></body></html>' > /usr/share/nginx/html/index.html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
