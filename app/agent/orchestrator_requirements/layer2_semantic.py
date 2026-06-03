import re
import logging
from typing import List, Dict

from app.agent.orchestrator_requirements.constants import (
    MIN_HISTORY_PROJECTS,
    MIN_VECTOR_RESULTS,
    MIN_HISTORY_WITH_FEATURES,
)
from app.agent.orchestrator_requirements.data_models import AssociationItem

logger = logging.getLogger(__name__)


async def layer2_semantic_match(requirement: str) -> List[AssociationItem]:
    try:
        from app.agent.vector_index import VectorIndexManager
        vi = VectorIndexManager()
        vi.load_or_create()

        if vi.total_count() >= MIN_VECTOR_RESULTS:
            results = await vi.search(requirement, top_k=10)
            if results:
                items = []
                for project_meta, score in results:
                    feature_list = project_meta.get("feature_list", [])
                    if not feature_list:
                        try:
                            from app.agent.project_metadata import ProjectMetadataManager
                            pm = ProjectMetadataManager()
                            projects = pm.get_all_projects()
                            matching = [
                                p for p in projects
                                if p.get("project_id") == project_meta.get("project_id")
                            ]
                            if matching:
                                feature_list = matching[0].get("feature_list", [])
                        except Exception:
                            pass

                    for feature in feature_list[:8]:
                        items.append(AssociationItem(
                            content=feature,
                            category="functional",
                            source="history_project",
                            confidence=min(score + 0.1, 0.95),
                            sub_category="semantic_match"
                        ))

                logger.info(
                    f"FAISS 语义检索: {vi.total_count()} 条向量, "
                    f"命中 {len(results)} 项目"
                )
                return items
    except Exception as e:
        logger.warning(f"FAISS 语义检索异常, 降级到关键词匹配: {e}")

    return await layer2_keyword_fallback(requirement)


async def layer2_keyword_fallback(requirement: str) -> List[AssociationItem]:
    try:
        from app.agent.project_metadata import ProjectMetadataManager
        pm = ProjectMetadataManager()
        if pm.total_count() < MIN_HISTORY_PROJECTS:
            logger.info(
                f"历史项目数 {pm.total_count()} < {MIN_HISTORY_PROJECTS}, "
                f"Layer 2 静默降级"
            )
            return []

        history_projects = pm.get_all_projects()
        matched = keyword_match_history(requirement, history_projects)
    except Exception as e:
        logger.warning(f"关键词匹配异常: {e}")
        return []

    items = []
    for project in matched[:5]:
        for feature in project.get("feature_list", []):
            items.append(AssociationItem(
                content=feature,
                category="functional",
                source="history_project",
                confidence=project.get("similarity", 0.6),
                sub_category="keyword_match"
            ))

    return items


def check_history_data_available() -> bool:
    try:
        from app.agent.project_metadata import ProjectMetadataManager
        pm = ProjectMetadataManager()
        total = pm.total_count()
        with_features = pm.count_with_features()
        if total >= MIN_HISTORY_PROJECTS and with_features >= MIN_HISTORY_WITH_FEATURES:
            logger.info(f"历史项目数据充足: {total} 项目, {with_features} 有功能清单")
            return True
    except Exception:
        pass

    return False


def keyword_match_history(requirement: str, projects: List[Dict]) -> List[Dict]:
    req_words = set(re.findall(r'[\w]+', requirement.lower()))
    scored = []
    for project in projects:
        proj_words = set(re.findall(
            r'[\w]+',
            (project.get("requirement") or "").lower()
        ))
        overlap = len(req_words & proj_words)
        total = max(len(req_words | proj_words), 1)
        similarity = overlap / total
        if similarity > 0.15:
            scored.append({**project, "similarity": similarity})

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:10]
