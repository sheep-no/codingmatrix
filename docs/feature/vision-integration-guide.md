# 视觉分析集成指南

## 概述

CodingMatrix 集成多模态视觉分析能力，支持图像理解、OCR、代码提取和安全检查。

## API 端点

| 端点 | 描述 | 权限 |
|------|------|------|
| POST /api/v1/vision/analyze | 图像分析 | normal |
| POST /api/v1/vision/ocr | OCR 文字识别 | normal |
| POST /api/v1/vision/code-from-image | 截图转代码 | normal |
| POST /api/v1/vision/check-safety | 图像安全检查 | normal |

## 图像分析

识别图片内容并返回文字描述。

**请求体**:
```json
{ "image": "base64_encoded_image", "prompt": "描述这张图片" }
```

## OCR 识别

提取图片中的文字。

**请求体**:
```json
{ "image": "base64_encoded_image", "language": "zh" }
```

## 代码提取

将 UI 截图转换为代码 (HTML/CSS)。

**请求体**:
```json
{ "image": "base64_encoded_image", "framework": "vue" }
```

## 安全检查

检测图片中的敏感/违规内容。

**请求体**:
```json
{ "image": "base64_encoded_image" }
```

## 技术实现

- **后端**: `app/utils/vision.py` 封装视觉分析逻辑
- **AI**: SiliconFlow 多模态模型
- **前端**: `vision_api.py` 提供 REST API

## 限制

| 限制 | 值 |
|------|-----|
| 最大图片大小 | 10MB |
| 支持格式 | JPEG, PNG, GIF, WebP |
| 最大分辨率 | 4096x4096 |
