import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


async def extract_and_save_feature_list(
    requirement: str,
    generated_files: Dict[str, str],
    domain: str = ""
) -> Optional[Dict]:
    try:
        from app.agent.project_metadata import ProjectMetadataManager
        pm = ProjectMetadataManager()

        # 调用方持有的是 {路径: 内容} 映射（从磁盘读回）；此前按 List[Dict] 解析
        # 且只认 content/code 键，而生成条目只有 path/size，导致 files_dict 恒空。
        files_dict = {
            path: content
            for path, content in (generated_files or {}).items()
            if path and content
        }

        result = await pm.extract_and_save(
            requirement, files_dict, domain=domain
        )

        # 阈值判定收敛到 trigger_template_extraction 内部，避免双处硬编码 15
        try:
            await pm.trigger_template_extraction(domain)
        except Exception as e:
            logger.warning(f"模板自动萃取失败: {e}")

        return result
    except Exception as e:
        logger.warning(f"功能清单提取失败: {e}")
        return None
