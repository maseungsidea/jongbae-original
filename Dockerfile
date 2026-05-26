# 단일 스테이지 Python 런타임
# Next.js 정적 파일은 로컬 빌드(npm run build) 후 frontend_build/ 디렉터리에 포함
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 + 사전 빌드된 프론트엔드(frontend_build/)
COPY . .

CMD ["python", "-u", "start.py"]
