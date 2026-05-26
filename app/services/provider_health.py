"""
供应商健康检查

测试 API Key 是否有效：
- 使用简单的模型推理测试
- 5 秒超时
- 返回成功/失败及错误信息
"""
import logging
from typing import Optional, Tuple
import httpx

logger = logging.getLogger(__name__)

# 测试超时时间（秒）
TEST_TIMEOUT = 5

# 测试提示
TEST_PROMPT = "1+1=?"
TEST_EXPECTED = "2"

# 各供应商配置
PROVIDER_CONFIGS = {
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "THUDM/glm-4-9b-chat",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-3.5-turbo",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com",
        "model": "claude-3-haiku-20240307",
    },
    "bailian": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-turbo",
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
}


class ProviderHealthChecker:
    """供应商健康检查器"""
    
    async def check(self, provider: str, api_key: str) -> Tuple[bool, str]:
        """
        检查供应商 API Key 是否有效
        
        Args:
            provider: 供应商名称
            api_key: API Key
            
        Returns:
            (success, message)
        """
        config = PROVIDER_CONFIGS.get(provider)
        if config is None:
            return False, f"不支持的供应商：{provider}"
        
        checker = getattr(self, f"_check_{provider}", None)
        if checker is not None:
            return await checker(api_key, config)
        
        # 默认使用 OpenAI 兼容接口检查
        return await self._check_openai_compatible(api_key, config)
    
    async def _check_siliconflow(self, api_key: str, config: dict) -> Tuple[bool, str]:
        """检查硅基流动"""
        return await self._check_openai_compatible(api_key, config)
    
    async def _check_openai(self, api_key: str, config: dict) -> Tuple[bool, str]:
        """检查 OpenAI"""
        return await self._check_openai_compatible(api_key, config)
    
    async def _check_bailian(self, api_key: str, config: dict) -> Tuple[bool, str]:
        """检查阿里百炼"""
        return await self._check_openai_compatible(api_key, config)
    
    async def _check_glm(self, api_key: str, config: dict) -> Tuple[bool, str]:
        """检查智谱 GLM"""
        return await self._check_openai_compatible(api_key, config)
    
    async def _check_deepseek(self, api_key: str, config: dict) -> Tuple[bool, str]:
        """检查 DeepSeek"""
        return await self._check_openai_compatible(api_key, config)
    
    async def _check_anthropic(self, api_key: str, config: dict) -> Tuple[bool, str]:
        """检查 Anthropic"""
        url = f"{config['base_url']}/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": config["model"],
            "max_tokens": 10,
            "messages": [
                {"role": "user", "content": TEST_PROMPT}
            ],
        }
        
        try:
            async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
                response = await client.post(url, headers=headers, json=payload)
                
                if response.status_code == 200:
                    return True, "连接成功"
                elif response.status_code == 401:
                    return False, "API Key 无效"
                elif response.status_code == 403:
                    return False, "权限不足"
                else:
                    return False, f"HTTP {response.status_code}: {response.text[:100]}"
        except httpx.TimeoutException:
            return False, "请求超时"
        except Exception as e:
            return False, f"连接失败：{str(e)}"
    
    async def _check_openai_compatible(self, api_key: str, config: dict) -> Tuple[bool, str]:
        """检查 OpenAI 兼容接口"""
        url = f"{config['base_url']}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config["model"],
            "messages": [
                {"role": "user", "content": TEST_PROMPT}
            ],
            "max_tokens": 10,
        }
        
        try:
            async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
                response = await client.post(url, headers=headers, json=payload)
                
                if response.status_code == 200:
                    return True, "连接成功"
                elif response.status_code == 401:
                    return False, "API Key 无效"
                elif response.status_code == 403:
                    return False, "权限不足"
                elif response.status_code == 429:
                    return False, "请求频率过高"
                else:
                    return False, f"HTTP {response.status_code}: {response.text[:100]}"
        except httpx.TimeoutException:
            return False, "请求超时"
        except Exception as e:
            return False, f"连接失败：{str(e)}"


# 全局单例
_health_checker: Optional[ProviderHealthChecker] = None


def get_health_checker() -> ProviderHealthChecker:
    """获取全局 ProviderHealthChecker 实例"""
    global _health_checker
    if _health_checker is None:
        _health_checker = ProviderHealthChecker()
    return _health_checker
