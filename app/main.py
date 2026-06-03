import logging
import os
import sys
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

# =============================================================================
# 跨平台环境变量加载（支持 Windows 和 Linux）
# =============================================================================

# 尝试使用 python-dotenv 加载 .env 文件
try:
    from dotenv import load_dotenv
    
    # 获取项目根目录（兼容不同平台）
    if getattr(sys, 'frozen', False):
        # 打包后的可执行文件
        BASE_DIR_PATH = Path(sys.executable).parent
    else:
        # 开发环境
        BASE_DIR_PATH = Path(__file__).resolve().parent.parent
    
    # 加载 .env 文件（自动查找项目根目录）
    env_path = BASE_DIR_PATH / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
        logging.getLogger(__name__).info(f"已加载环境变量：{env_path}")
    else:
        logging.getLogger(__name__).warning(f"未找到.env 文件：{env_path}")
except ImportError:
    # 未安装 python-dotenv，依赖 pydantic-settings 自动加载
    pass
except Exception as e:
    logging.getLogger(__name__).error(f"加载.env 文件失败：{e}")

from sqlalchemy import delete
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from app.models.history import History
from app.models.saved_project import SavedProject
from app.utils.async_enhanced_guard import AsyncSmartGuardian
from fastapi import FastAPI
from starlette.datastructures import State
# Alembic 迁移导入
from migrations.runner import run_async_migrations

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.core.graceful_shutdown import shutdown_manager, GracefulShutdownManager
from app.utils.rate_limiter import init_rate_limit
from app.utils.cache import get_cache, get_cache_manager
from app.utils.performance_monitor import setup_performance_monitoring
from app.api.v1.health import router as healthRouter

from app.models.base import Base
from app.api.v1.auth import router as userRouter
from app.api.v1.Aicode import router as codeRouter
from app.api.v1.GirlAi import router as GirlAiRouter
from app.api.v1.aiGeneratorPptx import router as pptxRouter
from app.api.v1.file_upload import router as fileUploadRouter
from app.api.v1.task_queue import router as taskQueueRouter
from app.api.v1.kolors_api import router as kolorsRouter
from app.api.v1.kolors_history import router as kolorsHistoryRouter
from app.api.v1.aicloud import router as aicloudRouter
from app.api.v1.aicloud_knowledge import router as aicloudKnowledgeRouter
from app.api.v1.workflow import router as workflowRouter
from app.api.v1.ai_agent import router as agentRouter
from app.api.v2.admin_config import router as adminConfigRouter
from app.api.v1.vision_api import router as visionRouter
from app.api.v2.nginx_api import router as nginxRouter
from app.api.v2.Controller import router as sysRouter
from app.api.v2.user_manage import router as userManageRouter
from app.api.v2.guardian_router import router as guardian_router
from app.api.v1.github import router as githubRouter
from app.api.v1.apikey import router as apikeyRouter
from app.api.v1.providers import router as providersRouter
from app.api.v1.model_manager import router as modelManagerRouter
from app.api.v2.model_admin import router as modelAdminRouter
from app.db.database import engine, async_session
from app.db.scheduler import start_scheduler
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from fastapi import Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from app.middleware.rate_limiter import RateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.feature_switch import FeatureSwitchMiddleware
from app.middleware.input_validator import InputValidatorMiddleware
from app.utils.error_handler import register_exception_handlers
from app.utils.logging import RequestLoggingMiddleware

logger = logging.getLogger(__name__)
setup_logging()


@asynccontextmanager
async def lifespan(App: FastAPI):
    shutdown_manager.setup_signal_handlers()

    # 确保用户项目上传目录存在
    user_uploads_dir = Path("./projects/user_uploads")
    user_uploads_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"用户上传目录已就绪: {user_uploads_dir.resolve()}")

    init_rate_limit(App)

    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        cache = await get_cache_manager(redis_url=redis_url)
        logger.info(f"Redis 缓存已初始化 | backend={cache.backend}")
    else:
        cache = await get_cache_manager()
        logger.info(f"内存缓存已初始化（Redis 未配置）| backend={cache.backend}")
    App.state.cache = cache

    await _warm_up_database_pool()

    guardian = AsyncSmartGuardian(check_interval=10)
    await guardian.scan_and_learn(auto_enable_trusted=True)
    await guardian.start_monitoring_enabled_services()
    App.state.guardian = guardian
    App.state.shutdown_manager = shutdown_manager

    yield

    await guardian.shutdown()
    await shutdown_manager.shutdown_async()
    await _cleanup_http_client()

    try:
        from app.utils.cache import _cache_manager
        if _cache_manager:
            await _cache_manager.close()
            logger.info("缓存管理器已关闭")
    except Exception as e:
        logger.warning(f"缓存管理器关闭失败: {e}")


async def _warm_up_database_pool():
    """预热数据库连接池"""
    try:
        async with async_session() as db:
            from sqlalchemy import text
            await db.execute(text("SELECT 1"))
        logger.info("数据库连接池预热完成")
    except Exception as e:
        logger.warning(f"数据库连接池预热失败: {e}")


async def _cleanup_http_client():
    """清理 HTTP 客户端连接"""
    try:
        from app.utils.http_client import close_http_client
        await close_http_client()
        logger.info("HTTP 客户端连接已关闭")
    except Exception as e:
        logger.warning(f"HTTP 客户端清理失败: {e}")

app = FastAPI(lifespan=lifespan, docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json")

# 注册统一异常处理器
register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_origin_regex=settings.ALLOWED_HOSTS.replace(",", "|"),
)

# 请求日志中间件（生成 request_id、记录请求耗时）
app.add_middleware(RequestLoggingMiddleware)

# 输入验证中间件（SQL注入/XSS检测、请求体大小限制）
app.add_middleware(InputValidatorMiddleware)

# 速率限制中间件（防止暴力破解和 DDoS）
app.add_middleware(RateLimitMiddleware)

# 功能开关中间件（禁用未启用的功能模块）
app.add_middleware(FeatureSwitchMiddleware)

# 安全响应头中间件（防止 XSS、点击劫持等攻击）
app.add_middleware(SecurityHeadersMiddleware)

# Gzip 压缩中间件（减少传输数据量，提升加载速度）
# 压缩大于 500 字节的响应，预计减少 70-80% 传输量
app.add_middleware(GZipMiddleware, minimum_size=500)

# 性能监控中间件
setup_performance_monitoring(app, slow_threshold=1.0)


@app.middleware("http")
async def drain_mode_middleware(request, call_next):
    """Draining 模式下拒绝新请求"""
    if shutdown_manager.is_draining:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={
                "error": "服务正在关闭",
                "detail": "服务器正在优雅关闭中，请稍后重试",
                "retry_after": 30
            },
            headers={"Retry-After": "30"}
        )
    shutdown_manager.increment_connections()
    try:
        response = await call_next(request)
        return response
    finally:
        shutdown_manager.decrement_connections()
async def clear_history_table():
    """清空 history 表（使用异步引擎）"""
    # 需要导入: from sqlalchemy import delete
    # 需要导入: from app.models.history import History
    async with async_session() as db:
        try:
            await db.execute(delete(History))
            await db.commit()
            print("History 表已清空")
        except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
            await db.rollback()
            print(f" 清空失败: {e}")

async def create_tables():
    """保留此函数以备不时之需"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)


async def _restore_user_providers():
    """从 Redis 恢复用户 API Key 对应的供应商模型列表（重启后重建 CustomProvider）"""
    from app.services.apikey_manager import get_apikey_manager
    from app.services.custom_provider_manager import get_custom_provider_manager
    from app.api.v1.apikey import _PROVIDER_BASE_URLS, _OPENAI_COMPAT_PROVIDERS, _sync_provider_models
    
    try:
        apikey_manager = get_apikey_manager()
        all_keys = apikey_manager.get_all_enabled_keys()
        
        if not all_keys:
            return
        
        # 按供应商分组，只取每个供应商最新的一个 Key
        provider_keys = {}
        for user_id, token, provider, api_key in all_keys:
            if provider in _OPENAI_COMPAT_PROVIDERS and provider not in provider_keys:
                provider_keys[provider] = api_key
        
        if not provider_keys:
            return
        
        logger.info(f"恢复 {len(provider_keys)} 个用户供应商模型列表...")
        for provider, api_key in provider_keys.items():
            await _sync_provider_models(provider, api_key)
        
    except Exception as e:
        logger.warning(f"恢复用户供应商模型失败：{e}")



# 启动事件
@app.on_event("startup")
async def on_startup():
    # await clear_history_table()
    # await create_tables()  # 已注释，改用 Alembic

    # 调用 Alembic 迁移
    try:
        await run_async_migrations()
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"数据库迁移异常 | error={str(e)}")
    
    # 启动定时任务调度器
    try:
        start_scheduler()
        logger.info("定时任务调度器启动成功")
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"定时任务调度器启动失败 | error={str(e)}")
    
    # 恢复用户 API Key 对应的供应商模型列表
    try:
        await _restore_user_providers()
    except Exception as e:
        logger.warning(f"恢复用户供应商模型失败（不影响正常启动）：{e}")


# 业务路由
# @app.get("/")
# async def root(db: AsyncSession = Depends(get_db)):
#     return {"msg": "ok"}

app.include_router(userRouter, prefix="/api/v1", tags=["auth"])
app.include_router(codeRouter, prefix="/api/v1", tags=["code"])
app.include_router(GirlAiRouter, prefix="/api/v1", tags=["GirlAi"])
app.include_router(pptxRouter, prefix="/api/v1", tags=["pptx"])
app.include_router(fileUploadRouter, prefix="/api/v1", tags=["files"])
app.include_router(taskQueueRouter, prefix="/api/v1", tags=["tasks"])
app.include_router(kolorsRouter, prefix="/api/v1", tags=["kolors"])
app.include_router(kolorsHistoryRouter, tags=["kolors-history"])
app.include_router(aicloudRouter, prefix="/api/v1", tags=["aicloud"])
app.include_router(aicloudKnowledgeRouter, prefix="/api/v1", tags=["aicloud-knowledge"])
app.include_router(workflowRouter, tags=["workflow"])
app.include_router(agentRouter, prefix="/api/v1", tags=["agent"])
app.include_router(visionRouter, prefix="/api/v1", tags=["vision"])
app.include_router(nginxRouter, prefix="/api/v2", tags=["nginx"])
app.include_router(sysRouter, prefix="/api/v2", tags=["sys"])
app.include_router(userManageRouter, prefix="/api/v2", tags=["manage"])
app.include_router(adminConfigRouter, prefix="/api/v2", tags=["admin-config"])
app.include_router(guardian_router, prefix="/api/v2", tags=["guard"])
app.include_router(modelAdminRouter, prefix="/api/v2", tags=["model-admin"])
app.include_router(githubRouter, prefix="/api/v1", tags=["github"])
app.include_router(apikeyRouter)
app.include_router(providersRouter, tags=["providers"])
app.include_router(modelManagerRouter, prefix="/api/v1", tags=["models"])

# 健康检查路由（/api/v1/health）
app.include_router(healthRouter, prefix="/api/v1")

# 静态文件服务（Vue前端）----------
# 配置dist路径（与main.py同级的dist文件夹）
DIST_PATH = rf"{BASE_DIR_PATH}/dist"
os.makedirs(DIST_PATH, exist_ok=True)
# 挂载静态文件到/static路径（供Vue加载JS/CSS等资源）
STATIC_PATH = os.path.join(DIST_PATH, "static")
if os.path.isdir(STATIC_PATH):
    app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")
else:
    app.mount("/static", StaticFiles(directory=DIST_PATH), name="static")

# 根路径返回Vue首页
@app.get("/", response_class=FileResponse)
async def serve_vue():
    return FileResponse(os.path.join(DIST_PATH, "index.html"))


# 处理Vue Router的history模式路由
@app.get("/{full_path:path}")
async def serve_vue_routes(full_path: str):
    # 跳过 API 请求，返回 404
    if full_path.startswith("api/"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not Found")

    # 如果是真实存在的文件，直接返回
    file_path = os.path.join(DIST_PATH, full_path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)

    # 其他路径返回 index.html，让 Vue Router 处理
    return FileResponse(os.path.join(DIST_PATH, "index.html"))

# .\cloudflared.exe tunnel --config="C:\Users\admin\Downloads\cloudflared\cloudflared\config\config.yml" run 93dbf689-e460-4139-8318-cbd8f5956567