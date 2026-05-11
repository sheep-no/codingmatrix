# 文件预览功能

## 概述

CodingMatrix 提供了多格式文件预览功能，支持 PDF、Word、Excel、图片、文本、代码等多种文件格式的在线预览。

## 路由端点

**前缀**: `/api/v1/preview`

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| GET | `/api/v1/preview/{file_id}` | 文件预览 | normal |
| GET | `/api/v1/preview/{file_id}/raw` | 原始文件下载 | normal |
| GET | `/api/v1/preview/{file_id}/thumbnail` | 缩略图 | normal |
| POST | `/api/v1/preview/batch` | 批量预览 | normal |

## 支持的格式

### 图片格式
- JPEG, PNG, GIF, WebP, SVG, BMP, ICO
- 支持缩略图生成 (最大 200x200)

### 文档格式
- PDF (直接浏览器渲染)
- Word (DOCX → HTML 转换)
- Excel (XLSX → HTML 表格)

### 代码和文本
- 纯文本文件 (TXT, MD, LOG 等)
- 代码文件 (JS, TS, PY, GO, Java, C/C++, Rust 等)
- 支持语法高亮 (Highlight.js)

### 其他
- CSV (表格预览)
- JSON (格式化显示)
- XML (树形显示)

## 前端实现

### 组件结构

```
components/
└── FilePreview.vue
    ├── ImagePreview.vue      # 图片预览
    ├── PdfPreview.vue        # PDF 预览
    ├── DocumentPreview.vue   # Word/Excel 预览
    ├── CodePreview.vue       # 代码预览
    └── TextPreview.vue       # 文本预览
```

### 使用方式

```vue
<template>
  <FilePreview :file-id="fileId" :file-type="fileType" />
</template>
```

### 预览模式

1. **内联预览**: 在页面内嵌入预览
2. **弹窗预览**: 使用 Dialog 弹窗显示
3. **新标签页**: 打开新标签页全屏预览

## 后端实现

### 核心逻辑

```python
# app/api/preview.py
@router.get("/preview/{file_id}")
async def preview_file(file_id: str, request: Request, db: Session = ...):
    # 1. 验证文件存在性和权限
    # 2. 根据文件类型选择预览方式
    # 3. 返回预览结果
    pass
```

### Office 文档转换

使用 `python-docx` 和 `openpyxl` 库将 Office 文档转换为 HTML:

```python
# DOCX 转换
doc = Document(file_path)
html_content = convert_docx_to_html(doc)

# XLSX 转换
wb = openpyxl.load_workbook(file_path)
html_content = convert_xlsx_to_html(wb)
```

### 缩略图生成

```python
from PIL import Image

def generate_thumbnail(image_path, size=(200, 200)):
    img = Image.open(image_path)
    img.thumbnail(size)
    return img
```

## 安全考虑

1. **文件类型验证**: 检查 MIME 类型和文件扩展名
2. **大小限制**: 最大预览文件大小 50MB
3. **XSS 防护**: HTML 内容使用 DOMPurify 清理
4. **权限控制**: 用户只能预览自己有权限的文件
5. **路径遍历防护**: 严格验证 file_id 格式

## 性能优化

1. **缓存**: 预览结果缓存 1 小时
2. **懒加载**: 大文件分页加载
3. **压缩**: 图片缩略图使用 WebP 格式
4. **CDN**: 静态资源使用 CDN 加速

## 错误处理

| 错误码 | 说明 |
|--------|------|
| 404 | 文件不存在 |
| 403 | 无权限访问 |
| 413 | 文件过大 |
| 415 | 不支持的文件类型 |
| 500 | 转换失败 |

## 使用示例

### 预览图片

```javascript
const previewUrl = `/api/v1/preview/${fileId}`
window.open(previewUrl, '_blank')
```

### 获取缩略图

```javascript
const thumbnailUrl = `/api/v1/preview/${fileId}/thumbnail`
<img :src="thumbnailUrl" alt="缩略图" />
```

### 批量预览

```javascript
const response = await api.post('/preview/batch', {
  file_ids: ['id1', 'id2', 'id3']
})
```
