import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


async def extract_and_save_feature_list(
    requirement: str,
    generated_files: List[Dict],
    domain: str = ""
) -> Optional[Dict]:
    try:
        from app.agent.project_metadata import ProjectMetadataManager
        pm = ProjectMetadataManager()

        files_dict = {}
        for gf in generated_files:
            path = gf.get("path", gf.get("file_path", ""))
            content = gf.get("content", gf.get("code", ""))
            if path and content:
                files_dict[path] = content

        result = await pm.extract_and_save(
            requirement, files_dict, domain=domain
        )

        domain_projects = pm.get_projects_by_domain(domain)
        if len(domain_projects) >= 15:
            try:
                await pm.trigger_template_extraction(domain)
            except Exception as e:
                logger.warning(f"模板自动萃取失败: {e}")

        return result
    except Exception as e:
        logger.warning(f"功能清单提取失败: {e}")
        return None
