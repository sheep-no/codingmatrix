import logging
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_
from sqlalchemy.orm import selectinload
from app.db.user_sql_server import *
from app.db.database import get_db
from app.schema.token import Token
from app.schema.user import *
from app.utils.security import *
from app.db.search_history import *
from app.schema.history import *
from app.core.config import settings
from app.db.permission_service import *
from app.models.Permission import Permission
from app.models.user import User
from app.models.history import History
from sqlalchemy.exc import SQLAlchemyError
from app.utils.cache import invalidate_user_cache
from app.utils.cache_decorator import cache_response, invalidate_cache_by_prefix
from app.middleware.rate_limiter import check_login_rate_limit, record_login_failure, record_login_success
from app.utils.csrf import get_csrf_token, csrf_protect, csrf_protect_optional
from app.utils.encryption import get_public_key_for_client, decrypt_sensitive_data

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/public-key", summary="获取 RSA 公钥")
async def get_public_key():
    """
    获取 RSA 公钥

    前端使用此公钥加密 AES 密钥
    """
    public_key = await get_public_key_for_client()
    return {
        "public_key": public_key,
        "algorithm": "RSA-OAEP",
        "key_size": 2048
    }


@router.get("/csrf-token", summary="获取 CSRF Token")
async def get_csrf_token_endpoint():
    """
    获取 CSRF Token
    
    用于前端在敏感操作前获取 CSRF Token
    同时在 Cookie 中设置 Token（双重提交模式）
    """
    from fastapi import Response
    from app.core.config import settings
    
    token = await get_csrf_token()
    
    # 创建响应
    response = Response(
        content=f'{{"csrf_token": "{token}", "expires_in": 3600}}',
        media_type="application/json"
    )
    
    # 设置 CSRF Token Cookie（JavaScript 可读取）
    response.set_cookie(
        key="csrf_token",
        value=token,
        httponly=False,  # JavaScript 需要读取
        secure=settings.ENV != "development",
        samesite="lax",
        max_age=3600,
        path="/"
    )
    
    return response



@router.post("/login", response_model=Token, summary="用户登陆")
async def login(
    request: Request, 
    body: dict,  # 使用 dict 接收原始请求体
    db: AsyncSession = Depends(get_db),
    csrf: str = Depends(csrf_protect)  # 添加 CSRF 验证
):
    """
    用户登录（支持明文和加密两种模式）
    
    - 加密模式：发送 encrypted_data 和 encrypted_key
    - 明文模式：直接发送 email 和 password（兼容旧版）
    """
    # 加密模式验证
    encrypted_body = None
    plain_body = None
    
    # 判断是加密还是明文模式
    if "encrypted_data" in body and "encrypted_key" in body:
        encrypted_body = body
    elif "email" in body and "password" in body:
        plain_body = body
    
    # 解密或直接使用数据
    if encrypted_body:
        try:
            from app.schema.user import UserLoginEncrypted
            encrypted_model = UserLoginEncrypted(**encrypted_body)
            # 解密数据
            decrypted_data = await decrypt_sensitive_data({
                "encrypted_data": encrypted_model.encrypted_data,
                "encrypted_key": encrypted_model.encrypted_key
            })
            email = decrypted_data["email"]
            password = decrypted_data["password"]
            logger.info(f"用户登录请求（加密模式）| email={email[:3]}***@***")
        except Exception as e:
            logger.warning(f"登录数据解密失败：{e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="数据解密失败"
            )
    elif plain_body:
        # 明文模式（应该被弃用）
        email = plain_body["email"]
        password = plain_body["password"]
        logger.warning(f"用户使用明文登录（建议升级加密）| email={email[:3]}***@***")
    else:
        logger.warning("登录请求格式错误：缺少 email/password 或 encrypted_data/encrypted_key")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="登录数据格式错误"
        )
    
    # 获取客户端标识用于限流
    client_ip = request.client.host
    identifier = f"{client_ip}:{email}"
    
    # 检查登录尝试限流
    if not check_login_rate_limit(identifier):
        logger.warning(f"登录被限流 | email={email} | ip={client_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试过于频繁，请 5 分钟后再试"
        )
    
    user = await get_user_by_email(db, email)
    if not user:
        logger.warning(f"登录失败：用户不存在 | email={email}")
        record_login_failure(identifier)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )
    
    logger.debug(f"用户验证成功 | email={email} | user_id={user.id}")
    
    permission_level = "normal"
    if user.permission:
        permission_level = user.permission.permission_level
        logger.debug(f"用户已有权限记录 | user_id={user.id} | permission_level={permission_level}")
    else:
        logger.info(f"用户无权限记录，创建默认权限 | user_id={user.id}")
        perm_service = PermissionService(db)
        permission = await perm_service.create_permission_if_not_exists(
            user_id=user.id, level="normal"
        )
        permission_level = permission.permission_level
    
    if not verify_password(password, user.hashed_password):
        logger.warning(f"登录失败：密码错误 | email={email} | user_id={user.id}")
        record_login_failure(identifier)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )
    
    logger.info(f"用户登录成功 | email={email} | user_id={user.id} | permission_level={permission_level}")
    
    # 登录成功，清除失败记录
    record_login_success(identifier)
    
    # 根据权限级别确定用户角色
    role = "user"
    if permission_level == "superadmin":
        role = "superadmin"
    elif permission_level == "admin":
        role = "admin"
    
    # 生成 Access Token（短期，30 分钟）
    access_token = create_access_token(sub=str(user.id), permission_level=permission_level, role=role)
    
    # 生成 Refresh Token（长期，7 天）- 用于 HttpOnly Cookie
    refresh_token = create_refresh_token(sub=str(user.id))
    
    # 生成 CSRF Token
    csrf_token = await get_csrf_token()
    
    # 创建响应
    response = JSONResponse(content={
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
        "permission_level": permission_level,
        "encryption_enabled": encrypted_body is not None  # 告知前端是否使用了加密
    })
    
    # 设置 HttpOnly Cookie - Refresh Token
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.ENV != "development",
        samesite="lax",
        max_age=7*24*60*60,
        path="/api/v1"
    )
    
    # 设置 CSRF Token Cookie（JavaScript 可读取）
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=settings.ENV != "development",
        samesite="lax",
        max_age=3600,
        path="/"
    )
    
    return response


@router.post("/register", response_model=Token, summary="用户注册")
async def register(
    body: UserRegister, 
    db: AsyncSession = Depends(get_db),
    csrf: str = Depends(csrf_protect)  # 添加 CSRF 验证
):
    logger.info(f"用户注册请求 | email={body.email} | username={body.username}")

    # 验证密码强度
    is_valid, message = validate_password_strength(body.password)
    if not is_valid:
        logger.warning(f"注册失败：密码强度不足 | email={body.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )

    if await check_email_exists(db, body.email):
        logger.warning(f"注册失败：邮箱已存在 | email={body.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已存在"
        )

    new_user = User(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
        created_at=datetime.now(timezone.utc)
    )
    db.add(new_user)
    await db.flush()
    logger.debug(f"用户创建成功 | email={body.email} | user_id={new_user.id}")

    perm_service = PermissionService(db)
    permission = await perm_service.create_permission(
        user_id=new_user.id, level="normal"
    )
    logger.info(f"权限创建成功 | user_id={new_user.id} | permission_level=normal")

    await db.commit()
    await db.refresh(new_user)

    # 新用户默认角色为user
    access_token = create_access_token(sub=str(new_user.id), permission_level=permission.permission_level, role="user")

    logger.info(f"用户注册成功 | email={body.email} | user_id={new_user.id}")

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": new_user.username,
        "permission_level": permission.permission_level
    }


@router.post("/history")
@cache_response(ttl=60, key_prefix="history")
async def get_history(
        request: HistoryRequest,
        db: AsyncSession = Depends(get_db),
        token: dict = Depends(verify_token)
):
    user_id = token.get("sub")
    logger.info(
        f"查询历史记录 | user_id={user_id} | prompt_keyword={request.prompt_keyword} | limit={request.limit} | offset={request.offset}")

    try:
        histories = await search_history_to_db(
            db=db,
            user_id=user_id,
            prompt_keyword=request.prompt_keyword,
            limit=request.limit,
            offset=request.offset
        )

        total = await get_distinct_conversation_count(
            db=db,
            user_id=user_id,
            prompt_keyword=request.prompt_keyword
        )

        logger.debug(f"历史记录查询完成 | user_id={user_id} | total={total} | returned={len(histories)}")

        return {
            "items": histories,
            "total": total,
            "limit": request.limit,
            "offset": request.offset
        }
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"查询历史记录异常 | user_id={user_id} | error={str(e)}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="查询历史记录失败")


@router.post("/conversation/history")
async def get_conversation_detail(
        request: ConversationHistoryRequest,
        db: AsyncSession = Depends(get_db),
        token: dict = Depends(verify_token)
):
    user_id = token.get("sub")
    logger.info(
        f"查询对话详情 | user_id={user_id} | conversation_id={request.conversation_id} | last_history_id={request.last_history_id}")

    try:
        histories = await get_conversation_history(
            db=db,
            user_id=user_id,
            conversation_id=request.conversation_id,
            last_history_id=request.last_history_id,
            limit=request.limit
        )

        logger.debug(
            f"对话详情查询完成 | user_id={user_id} | conversation_id={request.conversation_id} | returned={len(histories)}")

        return {
            "items": histories,
            "conversation_id": request.conversation_id
        }
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"查询对话详情异常 | user_id={user_id} | error={str(e)}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="查询对话详情失败")


@router.post("/refresh", summary="刷新 access_token")
async def refresh_token(
    request: Request, 
    db: AsyncSession = Depends(get_db),
    csrf: str = Depends(csrf_protect)  # 添加 CSRF 验证
):
    # 从 HttpOnly Cookie 中读取 Refresh Token
    refresh_token = request.cookies.get("refresh_token")
    
    if not refresh_token:
        logger.warning("Token 刷新失败：缺少 Refresh Token Cookie")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少刷新令牌，请重新登录"
        )
    
    logger.info("Token 刷新请求 | 从 Cookie 读取 Refresh Token")
    
    try:
        # 验证 Refresh Token
        payload = verify_refresh_token(refresh_token)
        user_id_str = payload.get("sub")
        
        if not user_id_str:
            logger.warning("Token 刷新失败：sub 字段缺失")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Refresh Token 无效"
            )
        
        logger.info(f"Refresh Token 验证通过 | user_id={user_id_str}")
        
        # 查询用户信息和权限
        perm_service = PermissionService(db)
        permission = await perm_service.get_permission(user_id=int(user_id_str))
        permission_level = permission.permission_level if permission else "normal"
        
        # 根据权限级别确定用户角色
        role = "user"
        if permission_level == "superadmin":
            role = "superadmin"
        elif permission_level == "admin":
            role = "admin"
        
        # 生成新的 Access Token
        new_access_token = create_access_token(sub=user_id_str, permission_level=permission_level, role=role)
        
        # 生成新的 CSRF Token
        csrf_token = await get_csrf_token()
        
        # 创建响应
        response = JSONResponse(content={
            "access_token": new_access_token,
            "token_type": "bearer",
            "username": permission.user.username if permission and permission.user else "unknown",
            "permission_level": permission_level,
            "csrf_token": csrf_token  # 返回新的 CSRF token
        })
        
        # 更新 CSRF Token Cookie
        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            httponly=False,
            secure=settings.ENV != "development",
            samesite="lax",
            max_age=3600,
            path="/"
        )
        
        logger.info(f"Token 刷新成功 | user_id={user_id_str}")
        return response
        
    except HTTPException as e:
        logger.error(f"Token 刷新业务异常 | error={str(e)}")
        raise
    except (ValueError, TypeError, RuntimeError, OSError) as e:
        logger.error(f"Token 刷新系统异常 | error={str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Refresh Token 无效，请重新登录"
        )


@router.get("/user/profile")
@cache_response(ttl=300, key_prefix="profile")
async def get_user_profile(
        db: AsyncSession = Depends(get_db),
        token: dict = Depends(verify_token)
):
    user_id = token.get("sub")
    logger.info(f"查询用户信息 | user_id={user_id}")

    try:
        result = await db.execute(
            select(User)
            .options(selectinload(User.permission))
            .where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "permission_level": user.permission.permission_level if user.permission else "normal",
            "created_at": str(user.created_at),
            "updated_at": str(user.updated_at) if user.updated_at else None,
        }
    except HTTPException:
        raise
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"查询用户信息异常 | user_id={user_id} | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询用户信息失败")


@router.get("/conversations")
@cache_response(ttl=120, key_prefix="conversations")
async def get_conversations(
        limit: int = 50,
        offset: int = 0,
        db: AsyncSession = Depends(get_db),
        token: dict = Depends(verify_token)
):
    user_id = token.get("sub")
    logger.info(f"查询会话列表 | user_id={user_id} | limit={limit} | offset={offset}")

    try:
        subquery = (
            select(
                History.conversation_id,
                func.max(History.id).label("max_id"),
                func.count(History.id).label("msg_count")
            )
            .where(History.user_id == user_id)
            .group_by(History.conversation_id)
            .subquery()
        )

        count_stmt = select(func.count()).select_from(subquery)
        total_result = await db.execute(count_stmt)
        total = total_result.scalar() or 0

        conversations_stmt = (
            select(History, subquery.c.msg_count)
            .join(subquery, History.id == subquery.c.max_id)
            .where(History.user_id == user_id)
            .order_by(desc(History.id))
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(conversations_stmt)
        rows = result.all()

        items = []
        for conv, msg_count in rows:
            items.append({
                "conversation_id": conv.conversation_id,
                "title": conv.title,
                "prompt": conv.prompt[:100] if conv.prompt else "",
                "created_at": str(conv.created_at),
                "message_count": msg_count,
            })

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"查询会话列表异常 | user_id={user_id} | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询会话列表失败")