# 文件上传详细指南

## 概述

CodingMatrix 支持两种文件上传方式：单文件上传和分片上传。

## 单文件上传

### API
```
POST /api/v1/files/upload
Content-Type: multipart/form-data

file: (binary)
```

### 响应
```json
{
  "file_id": "uuid",
  "filename": "string",
  "size": 12345,
  "content_type": "image/png",
  "created_at": "2026-05-08T00:00:00Z"
}
```

### 下载
```
GET /api/v1/files/{file_id}/download
```

## 分片上传

适用于大文件 (建议 > 10MB)。

### 流程

1. **初始化**
```
POST /api/v1/files/upload/init
{"filename": "large.zip", "total_size": 104857600, "chunk_size": 5242880}
```
响应: `{"file_id": "uuid", "total_chunks": 20}`

2. **上传分片**
```
POST /api/v1/files/upload/chunk/{file_id}/{chunk_index}
Content-Type: application/octet-stream

(chunk binary data)
```

3. **合并**
```
POST /api/v1/files/upload/merge/{file_id}
```

### 前端组件

`FileUpload.vue` 组件提供：
- 拖拽上传
- 进度条
- 分片自动计算
- 断点续传
- 多文件队列

## 安全限制

| 限制 | 值 |
|------|-----|
| 单文件最大 | 100MB |
| 分片大小 | 5MB (推荐) |
| 允许类型 | 图片、文档、代码文件 |
| 存储位置 | `data/uploads/` |
