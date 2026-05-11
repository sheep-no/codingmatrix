#!/bin/bash
# 批量替换硬编码颜色为主题变量

for file in src/components/*.vue src/components/**/*.vue 2>/dev/null; do
  [ -f "$file" ] || continue
  
  # 替换白色背景
  sed -i 's/background:\s*#fff\([;\"]\)/background: var(--bg-primary)\1/g' "$file"
  sed -i 's/background:\s*#ffffff\([;\"]\)/background: var(--bg-primary)\1/g' "$file"
  sed -i 's/background:\s*#fafafa\([;\"]\)/background: var(--bg-secondary)\1/g' "$file"
  sed -i 's/background:\s*#f8f9fa\([;\"]\)/background: var(--bg-secondary)\1/g' "$file"
  sed -i 's/background:\s*#f8fafc\([;\"]\)/background: var(--bg-secondary)\1/g' "$file"
  sed -i 's/background:\s*#f1f5f9\([;\"]\)/background: var(--bg-tertiary)\1/g' "$file"
  
  # 替换深色背景
  sed -i 's/background:\s*#1e293b\([;\"]\)/background: var(--bg-primary)\1/g' "$file"
  sed -i 's/background:\s*#0f172a\([;\"]\)/background: var(--bg-primary)\1/g' "$file"
  
  # 替换文字颜色
  sed -i 's/color:\s*#0f172a\([;\"]\)/color: var(--text-primary)\1/g' "$file"
  sed -i 's/color:\s*#1e293b\([;\"]\)/color: var(--text-primary)\1/g' "$file"
  sed -i 's/color:\s*#475569\([;\"]\)/color: var(--text-secondary)\1/g' "$file"
  sed -i 's/color:\s*#64748b\([;\"]\)/color: var(--text-tertiary)\1/g' "$file"
  sed -i 's/color:\s*#94a3b8\([;\"]\)/color: var(--text-tertiary)\1/g' "$file"
  sed -i 's/color:\s*#ffffff\([;\"]\)/color: var(--bg-primary)\1/g' "$file"
  
  # 替换边框颜色
  sed -i 's/border:\s*1px solid #e2e8f0\([;\"]\)/border: 1px solid var(--border-color)\1/g' "$file"
  sed -i 's/border:\s*1px solid #cbd5e1\([;\"]\)/border: 1px solid var(--border-color)\1/g' "$file"
done

echo "Done"
