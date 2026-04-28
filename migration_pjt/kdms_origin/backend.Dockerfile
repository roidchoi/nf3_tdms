# backend.Dockerfile (변경 없음, 재확인용)
FROM python:3.12-slim

WORKDIR /app

# 필수 라이브러리 설치 (PostgreSQL 어댑터 빌드용)
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# uv로 추출한 requirements.txt 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]