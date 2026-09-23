# =============================================================================
# Dockerfile - Multi-stage Build
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Frontend Build
# -----------------------------------------------------------------------------
FROM node:20-alpine AS frontend-builder

WORKDIR /app/src

COPY src/package.json src/package-lock.json ./

RUN npm ci

COPY src/ .

RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2: Backend Dependencies
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS backend-deps

WORKDIR /app

COPY configs/requirements.txt configs/requirements-test.txt ./

RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# Stage 3: Production Runtime
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENV=production

WORKDIR /app

# Install system dependencies and create non-root user
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -r appuser && \
    useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy backend dependencies from deps stage
COPY --from=backend-deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend-deps /usr/local/bin /usr/local/bin

# Copy backend source code
COPY app/ ./app/
COPY configs/alembic.ini ./
# 系统配置默认值随镜像分发；/app/configs 不是挂载点，不会被数据卷遮蔽。
# 生产如需持久化运行期覆盖，可在编排中把该文件挂到同一路径。
COPY configs/system_config.json ./configs/
COPY migrations/ ./migrations/
COPY pyproject.toml ./

# Copy frontend build artifacts from frontend stage
COPY --from=frontend-builder /app/src/dist ./src/dist

# Install nginx
RUN apt-get update && \
    apt-get install -y --no-install-recommends nginx && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /var/log/nginx /var/lib/nginx /etc/nginx/conf.d /workspace/src /workspace/logs /workspace/data && \
    ln -sfn /app/src/dist /workspace/src/dist && \
    ln -sf /app/logs /workspace/logs && \
    ln -sf /app/data /workspace/data

# Copy nginx configuration after the package creates its runtime directories.
COPY configs/nginx.conf /etc/nginx/nginx.conf
COPY configs/nginx-upstream-local.conf /etc/nginx/conf.d/upstream.conf

# Create necessary directories and set permissions
# 必须覆盖 compose 中所有 appuser 需要写入的挂载点：Docker 为缺失的挂载路径
# 创建 root 属主的目录，若不预建并 chown，非 root 的 appuser 将无法写入
# 上传目录与生成物目录。
RUN mkdir -p /app/logs /app/data /app/keys /app/uploads /app/pptx_output /app/generated_images /app/projects && \
    chown -R appuser:appuser /app && \
    chown -R nginx:nginx /var/log/nginx /var/lib/nginx /var/run

# Expose ports
EXPOSE 80 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/api/v1/health || exit 1

# Start command
# Nginx needs a root master for port 80, while the API runs as appuser.
CMD ["sh", "-c", "nginx && exec su -s /bin/sh appuser -c 'exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 2'"]
