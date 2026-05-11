# Skills 迁移报告

## 迁移日期: 2026-04

## 概述

将 AI Agent Skills 从 `/root/.claude/skills/` 迁移到 `/workspace/.claude/skills/`。

## 迁移内容

| Skill | 描述 |
|-------|------|
| deploy-website | 部署网站预览 |
| feature-design | 需求文档生成 |
| feature-implementer | 功能实施 |
| implementation-planner | 实施计划生成 |
| project-wiki | 项目文档生成 |

## 迁移步骤

1. 复制 skill 文件到新位置
2. 更新技能引用路径
3. 验证技能正常工作
4. Git 跟踪新位置

## 验证结果

所有 skills 迁移后功能正常。
