FROM python:3.12-slim

WORKDIR /app

# 필수 시스템 라이브러리 설치
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 의존성 복사 및 설치
COPY tdms_core/p3_usdms/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# p1_shared 및 p3_usdms 소스 복사
COPY tdms_core/p1_shared /app/tdms_core/p1_shared
COPY tdms_core/p3_usdms /app/tdms_core/p3_usdms

# 패키지 설치 (Editable 모드)
RUN pip install -e /app/tdms_core/p1_shared
RUN pip install -e /app/tdms_core/p3_usdms

# 작업 디렉토리 이동 및 실행
WORKDIR /app/tdms_core/p3_usdms
ENV PYTHONPATH="/app/tdms_core"
EXPOSE 8005

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8005"]
