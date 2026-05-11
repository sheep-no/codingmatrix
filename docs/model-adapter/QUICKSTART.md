# 模型适配器快速开始

## 1. 获取 API Key

在 [SiliconFlow](https://siliconflow.cn) 注册并获取 API Key。

## 2. 设置环境变量

```bash
export SILICONFLOW_API_KEY=your-api-key
```

## 3. 使用模型

```python
from app.utils.AiCodeUtil import call_siliconflow

# 代码生成
result = await call_siliconflow(
    prompt="写一个快速排序",
    model="Qwen/Qwen2.5-Coder-7B-Instruct"
)

# 流式生成
async for chunk in await call_siliconflow(
    prompt="写一个快速排序",
    model="Qwen/Qwen2.5-Coder-7B-Instruct",
    stream=True
):
    print(chunk)
```

## 4. 验证

```bash
# 启动服务
python -m uvicorn app.main:app --reload

# 测试健康
curl http://localhost:8000/api/v1/health/models
```
