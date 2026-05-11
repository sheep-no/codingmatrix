#!/bin/bash
# 预览功能集成验证脚本

echo "========================================"
echo "预览功能集成验证"
echo "========================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查计数
PASSED=0
FAILED=0

# 检查函数
check_file() {
    local file=$1
    local description=$2
    
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $description"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC} $description"
        echo "  文件不存在：$file"
        ((FAILED++))
        return 1
    fi
}

check_content() {
    local file=$1
    local pattern=$2
    local description=$3
    
    if grep -q "$pattern" "$file" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $description"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC} $description"
        echo "  未找到匹配内容：$pattern"
        ((FAILED++))
        return 1
    fi
}

echo "1. 检查核心组件文件"
echo "----------------------------------------"
check_file "src/components/tools/FilePreviewCenter.vue" "FilePreviewCenter 组件存在"
check_file "app/api/v1/preview.py" "预览 API 存在"
check_file "src/components/tools/PPTGenerator.vue" "PPTGenerator 组件存在"
check_file "src/components/tools/ProjectGenerator.vue" "ProjectGenerator 组件存在"
check_file "app/api/v1/AiProjectCode.py" "AIProjectCode API 存在"
echo ""

echo "2. 检查 PPTGenerator 集成"
echo "----------------------------------------"
check_content "src/components/tools/PPTGenerator.vue" "import FilePreviewCenter" "PPTGenerator 导入 FilePreviewCenter"
check_content "src/components/tools/PPTGenerator.vue" "showPreview" "PPTGenerator 添加预览状态"
check_content "src/components/tools/PPTGenerator.vue" "openPPTPreview" "PPTGenerator 添加预览方法"
check_content "src/components/tools/PPTGenerator.vue" "closePreview" "PPTGenerator 添加关闭方法"
check_content "src/components/tools/PPTGenerator.vue" "<FilePreviewCenter" "PPTGenerator 模板包含预览组件"
echo ""

echo "3. 检查 ProjectGenerator 集成"
echo "----------------------------------------"
check_content "src/components/tools/ProjectGenerator.vue" "import FilePreviewCenter" "ProjectGenerator 导入 FilePreviewCenter"
check_content "src/components/tools/ProjectGenerator.vue" "showPreview" "ProjectGenerator 添加预览状态"
check_content "src/components/tools/ProjectGenerator.vue" "previewProject" "ProjectGenerator 添加预览方法"
check_content "src/components/tools/ProjectGenerator.vue" "closePreview" "ProjectGenerator 添加关闭方法"
check_content "src/components/tools/ProjectGenerator.vue" "<FilePreviewCenter" "ProjectGenerator 模板包含预览组件"
echo ""

echo "4. 检查 AIProjectCode API 增强"
echo "----------------------------------------"
check_content "app/api/v1/AiProjectCode.py" "get_project_files" "添加项目文件列表端点"
check_content "app/api/v1/AiProjectCode.py" "/generate/files" "定义文件列表路由"
check_content "app/api/v1/AiProjectCode.py" "file_type" "支持文件类型识别"
check_content "app/api/v1/AiProjectCode.py" "安全检查" "包含安全检查逻辑"
echo ""

echo "5. 检查 FilePreviewCenter 增强"
echo "----------------------------------------"
check_content "src/components/tools/FilePreviewCenter.vue" "file: { type: Object" "添加 file prop 支持"
check_content "src/components/tools/FilePreviewCenter.vue" "watch(() => props.file" "监听 file prop 变化"
echo ""

echo "6. Python 语法检查"
echo "----------------------------------------"
if python3 -m py_compile app/api/v1/AiProjectCode.py 2>/dev/null; then
    echo -e "${GREEN}✓${NC} AiProjectCode.py 语法正确"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} AiProjectCode.py 语法错误"
    ((FAILED++))
fi
echo ""

echo "7. 检查文档"
echo "----------------------------------------"
check_file "INTEGRATION-COMPLETE.md" "集成完成报告"
check_file "PREVIEW-FEATURE-ENHANCEMENTS.md" "预览功能增强方案"
check_file "PREVIEW-ENHANCEMENT-SUMMARY.md" "预览增强总结"
check_file "OPTIMIZATION-REPORT.md" "优化报告"
echo ""

echo "========================================"
echo "验证结果汇总"
echo "========================================"
echo -e "通过：${GREEN}$PASSED${NC}"
echo -e "失败：${RED}$FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ 所有检查通过！集成完成。${NC}"
    exit 0
else
    echo -e "${RED}❌ 部分检查失败，请查看详细信息。${NC}"
    exit 1
fi
