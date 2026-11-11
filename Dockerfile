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
# alembic.ini 必须落在 configs/ 下：其 script_location 与 prepend_sys_path 均以
# %(here)s（ini 所在目录）相对定位，放在 /app/configs 时解析为 /app/migrations 与 /app
COPY configs/alembic.ini ./configs/
# 系统配置默认值随镜像分发；/app/configs 不是挂载点，不会被数据卷遮蔽。
# 生产如需持久化运行期覆盖，可在编排中把该文件挂到同一路径。
COPY configs/system_config.json ./configs/
COPY migrations/ ./migrations/
COPY pyproject.toml ./

# Copy frontend build artifacts from frontend stage
COPY --from=frontend-builder /app/src/dist ./src/dist

# 运行镜像只承载 FastAPI。Nginx 在基础 Compose 与生产 Compose 中都是独立服务，
# 由 configs/nginx-upstream-compose.conf 代理到 api:8080。
RUN mkdir -p /workspace/src /workspace/logs /workspace/data && \
    ln -sfn /app/src/dist /workspace/src/dist && \
    ln -sf /app/logs /workspace/logs && \
    ln -sf /app/data /workspace/data

# 文档转换工具链：PPT 转 PDF 调用 libreoffice（app/api/v1/aiGeneratorPptx.py），
# PDF 转 PNG 预览与成品质量复审调用 pdftoppm（app/services/ppt_quality_orchestrator.py、
# app/services/ppt_template_samples.py），中文 PPT 渲染依赖 CJK 字体。
# 缺任一项时 PDF 导出返回 501、质量视觉复审抛错。该层使镜像增大约 0.7-1 GB。
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libreoffice-impress \
        poppler-utils \
        fonts-noto-cjk && \
    rm -rf /var/lib/apt/lists/*

# Create necessary directories and set permissions
# 必须覆盖 compose 中所有 appuser 需要写入的挂载点：Docker 为缺失的挂载路径
# 创建 root 属主的目录，若不预建并 chown，非 root 的 appuser 将无法写入
# 上传目录与生成物目录。
RUN mkdir -p /app/logs /app/data /app/keys /app/uploads /app/pptx_output /app/generated_images /app/projects && \
    chown -R appuser:appuser /app

# Expose ports
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/api/v1/health || exit 1

# Start command
CMD ["sh", "-c", "exec su -s /bin/sh appuser -c 'exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 2'"]
