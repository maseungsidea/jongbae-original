FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 (pykrx 빌드용)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# Railway 포트
ENV PORT=8000

# Gunicorn: Flask API + 스케줄러 백그라운드 실행
CMD sh -c "python scheduler.py &> /tmp/scheduler.log & gunicorn -b 0.0.0.0:$PORT --workers 1 --threads 4 app:app"