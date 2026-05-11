from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, articles, categories, tags, comments, stats, settings
from fastapi.responses import JSONResponse
from fastapi.exceptions importstarlette_httpexceptions,starlette_exceptions
import logging

app = FastAPI(
    title="企业级在线博客内容管理系统（CMS）",
    description="这是一个功能完整的个人/团队博客平台，支持多用户、多角色、内容管理、评论互动、数据统计等功能。",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
)

# 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由注册
app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(articles.router, prefix="/api/articles", tags=["文章"])
app.include_router(categories.router, prefix="/api/categories", tags=["分类"])
app.include_router(tags.router, prefix="/api/tags", tags=["标签"])
app.include_router(comments.router, prefix="/api/comments", tags=["评论"])
app.include_router(stats.router, prefix="/api/stats", tags=["统计"])
app.include_router(settings.router, prefix="/api/settings", tags=["设置"])

# 错误处理
@app.exception_handler(starlette_httpexceptions.HTTPException)
async def custom_http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

@app.exception_handler(starlette_exceptions.RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )

@app.exception_handler(starlette_exceptions.AuthenticationCredentialsException)
async def auth_exception_handler(request, exc):
    return JSONResponse(
        status_code=401,
        content={"detail": "未授权，请登录。"},
    )

@app.exception_handler(starlette_exceptions.AuthorizationException)
async def auth_exception_handler(request, exc):
    return JSONResponse(
        status_code=403,
        content={"detail": "无权限。"},
    )