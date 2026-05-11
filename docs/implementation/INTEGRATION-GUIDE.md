# 集成指南

## 概述

本指南说明如何将各模块集成到 CodingMatrix 平台。

## 后端集成

### 1. 创建 API 路由

在 `app/api/v1/` 或 `app/api/v2/` 下创建新的路由文件:

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/my-feature")
async def my_feature():
    return {"message": "hello"}
```

### 2. 注册路由

在 `app/main.py` 中注册:

```python
from app.api.v1.my_feature import router as my_feature_router

app.include_router(my_feature_router, prefix="/api/v1", tags=["MyFeature"])
```

### 3. 创建 Schema

在 `app/schema/` 下定义请求/响应模型:

```python
from pydantic import BaseModel

class MyFeatureRequest(BaseModel):
    name: str
    value: int

class MyFeatureResponse(BaseModel):
    result: str
```

### 4. 创建工具函数

在 `app/utils/` 下添加业务逻辑:

```python
# app/utils/my_feature.py
async def process_feature(data: dict) -> str:
    return "processed"
```

### 5. 创建测试

在 `tests/integration/` 下添加集成测试:

```python
async def test_my_feature():
    response = await client.get("/api/v1/my-feature")
    assert response.status_code == 200
```

## 前端集成

### 1. 创建组件

在 `src/components/` 下创建 Vue 组件:

```vue
<script setup>
import { ref } from 'vue'
import { api } from '@/utils/api'

const result = ref('')

async function fetchData() {
  const res = await api.get('/api/v1/my-feature')
  result.value = res.data.result
}
</script>

<template>
  <div>{{ result }}</div>
</template>
```

### 2. 注册路由

在 `src/router/index.js` 中添加路由:

```javascript
{
  path: '/my-feature',
  component: () => import('@/components/MyFeature.vue')
}
```

### 3. 添加导航

在 `MainLayout.vue` 中添加导航项:

```vue
<el-menu-item index="/my-feature">
  新功能
</el-menu-item>
```
