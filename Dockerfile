# ── Stage 1: Next.js 정적 빌드 ──────────────────────────────
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --prefer-offline
COPY frontend/ ./
# output: 'export' 설정으로 정적 파일 생성 (Flask 가 서빙)
RUN npm run build

# ── Stage 2: Python 런타임 ────────────────────────────────────
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python 의존성
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY . .

# Next.js 빌드 결과를 frontend_build/ 로 복사
COPY --from=frontend-builder /app/frontend/out ./frontend_build

# Flask API + Scheduler 통합 진입점
CMD ["python", "-u", "start.py"]
