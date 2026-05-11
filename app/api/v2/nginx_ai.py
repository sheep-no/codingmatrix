import tempfile
import subprocess
from pathlib import Path
import logging

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from app.utils.security import *
from app.utils.AiCodeUtil import *
from app.schema.nginxConf import *
from app.core.config import settings
import shutil

# 初始化日志
logger = logging.getLogger(__name__)
router = APIRouter()

# 配置常量
NGINX_CHECK_TIMEOUT = 30  # 秒，大配置文件需要更长时间
DEFAULT_AI_MODEL = getattr(settings, 'NGINX_AI_MODEL', "Qwen/Qwen2.5-Coder-7B-Instruct")


@router.post("/nginx/check")
async def check_nginx(body: NginxConf):
    config_size = len(body.config) if body.config else 0
    logger.info(f"Nginx配置检查请求 | config_size={config_size} bytes")

    tmp_path = None
    try:
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix=".conf", delete=False) as f:
            f.write(body.config)
            tmp_path = Path(f.name)

        logger.debug(f"临时配置文件创建成功 | path={tmp_path}")

        # 执行 nginx 语法检查
        logger.debug(f"执行 nginx 语法检查 | cmd=nginx -t -c {tmp_path}")

        result = subprocess.run(
            ["nginx", "-t", "-c", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=NGINX_CHECK_TIMEOUT  # 使用配置化的超时时间
        )

        logger.debug(f"检查命令执行完成 | returncode={result.returncode}")

        # 检查通过
        if result.returncode == 0 and "syntax is ok" in result.stderr:
            logger.info(f"Nginx 配置语法检查通过 | path={tmp_path}")
            tmp_path.unlink()
            logger.debug(f"临时文件已删除 | path={tmp_path}")
            return {"status": "ok", "message": "配置语法正确"}

        # 配置错误，准备调用 AI 分析
        error_text = result.stderr.strip()
        logger.warning(f"Nginx 配置语法错误 | error={error_text[:200]}")  # 只记录前 200 字符，避免日志过长

        prompt = f"""下面是一个 Nginx 配置错误，请解释原因并给出正确配置片段：
{error_text}"""

        logger.info(f"调用 AI 服务分析错误 | model={DEFAULT_AI_MODEL}")

        stream_gen = await call_siliconflow(
            prompt=prompt,
            model=DEFAULT_AI_MODEL,
            stream=True,
        )

        logger.info(f"返回 AI 流式响应")

        return StreamingResponse(
            stream_gen,
            media_type="text/event-stream"
        )

    except subprocess.TimeoutExpired:
        logger.error(f"Nginx检查超时 | timeout=10s")
        raise HTTPException(status_code=500, detail="Nginx 检查超时")

    except FileNotFoundError:
        logger.error(f"nginx命令未找到 | 请确保nginx已安装并在PATH中")
        raise HTTPException(status_code=500, detail="nginx 命令未安装或不在 PATH 中")

    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"处理异常 | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # 清理临时文件
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
                logger.debug(f"临时文件清理完成 | path={tmp_path}")
            except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
                logger.warning(f"临时文件删除失败 | path={tmp_path} | error={str(e)}")
        else:
            logger.debug(f"无需清理临时文件")