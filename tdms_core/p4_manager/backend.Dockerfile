FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# uv 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uv/bin/uv
ENV PATH="/uv/bin:${PATH}"

# 패키지 복사
COPY tdms_core/p1_shared /app/tdms_core/p1_shared
COPY tdms_core/p4_manager /app/tdms_core/p4_manager

# 의존성 및 editable 설치 (System Python 사용)
WORKDIR /app/tdms_core/p4_manager
RUN uv pip install --system -r requirements.txt && uv pip install --system -e .

EXPOSE 8010

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010"]
