import json
import time
import logging
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

VECTOR_INDEX_DIR = Path("./data/vector_index")
METADATA_PATH = VECTOR_INDEX_DIR / "project_metadata.json"
INDEX_PATH = VECTOR_INDEX_DIR / "faiss_index.bin"
IDS_PATH = VECTOR_INDEX_DIR / "id_map.json"

EMBEDDING_DIM = 768
SIMILARITY_THRESHOLD = 0.35
MAX_RESULTS = 10


class VectorIndexManager:

    def __init__(self):
        VECTOR_INDEX_DIR.mkdir(parents=True, exist_ok=True)
        self._index = None
        self._id_map: Dict[int, Dict] = {}
        self._next_id = 0
        self._loaded = False

    def load_or_create(self) -> bool:
        try:
            if INDEX_PATH.exists() and IDS_PATH.exists():
                import faiss
                self._index = faiss.read_index(str(INDEX_PATH))
                with open(IDS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._id_map = {int(k): v for k, v in data.get("id_map", {}).items()}
                self._next_id = data.get("next_id", 0)
                self._loaded = True
                logger.info(f"FAISS 索引加载完成: {self._index.ntotal} 条向量")
                return True
        except Exception as e:
            logger.warning(f"FAISS 索引加载失败: {e}, 创建新索引")

        self._create_empty_index()
        self._loaded = True
        return True

    def _create_empty_index(self):
        import faiss
        self._index = faiss.IndexFlatIP(EMBEDDING_DIM)
        self._id_map = {}
        self._next_id = 0

    async def build_from_metadata(self) -> int:
        from app.utils.AiCodeUtil import get_embedding

        if not METADATA_PATH.exists():
            logger.info("project_metadata.json 不存在，跳过索引构建")
            return 0

        self._create_empty_index()

        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            projects = json.load(f)

        count = 0
        for project in projects:
            feature_list = project.get("feature_list")
            if not feature_list:
                continue

            text = self._project_to_text(project)
            try:
                vector = await get_embedding(text)
                vec_np = np.array([vector], dtype=np.float32)
                faiss.normalize_L2(vec_np)
                self._index.add(vec_np)
                self._id_map[self._next_id] = {
                    "project_id": project.get("project_id", ""),
                    "requirement": project.get("requirement", ""),
                    "domain": project.get("domain", ""),
                    "feature_count": len(feature_list),
                }
                self._next_id += 1
                count += 1
            except Exception as e:
                logger.warning(f"项目 {project.get('project_id', '?')} embedding 失败: {e}")

        self._save_index()
        logger.info(f"FAISS 索引构建完成: {count} 条向量")
        return count

    async def add_project(self, project: Dict) -> bool:
        from app.utils.AiCodeUtil import get_embedding

        if not project.get("feature_list"):
            return False

        if not self._loaded:
            self.load_or_create()

        text = self._project_to_text(project)
        try:
            vector = await get_embedding(text)
            vec_np = np.array([vector], dtype=np.float32)
            faiss.normalize_L2(vec_np)
            self._index.add(vec_np)
            self._id_map[self._next_id] = {
                "project_id": project.get("project_id", ""),
                "requirement": project.get("requirement", ""),
                "domain": project.get("domain", ""),
                "feature_count": len(project.get("feature_list", [])),
            }
            self._next_id += 1
            self._save_index()
            return True
        except Exception as e:
            logger.warning(f"项目 embedding 失败: {e}")
            return False

    async def search(
        self, query: str, top_k: int = MAX_RESULTS
    ) -> List[Tuple[Dict, float]]:
        from app.utils.AiCodeUtil import get_embedding

        if not self._loaded:
            self.load_or_create()

        if self._index.ntotal == 0:
            return []

        try:
            vector = await get_embedding(query)
            vec_np = np.array([vector], dtype=np.float32)
            faiss.normalize_L2(vec_np)

            k = min(top_k, self._index.ntotal)
            distances, ids = self._index.search(vec_np, k)

            results = []
            for i in range(k):
                idx = int(ids[0][i])
                score = float(distances[0][i])
                if score >= SIMILARITY_THRESHOLD and idx in self._id_map:
                    results.append((self._id_map[idx], score))

            return results
        except Exception as e:
            logger.warning(f"向量检索失败: {e}")
            return []

    def total_count(self) -> int:
        if not self._loaded:
            return 0
        return self._index.ntotal

    def _project_to_text(self, project: Dict) -> str:
        parts = []
        if project.get("requirement"):
            parts.append(project["requirement"])
        if project.get("domain"):
            parts.append(f"领域: {project['domain']}")
        for feat in project.get("feature_list", [])[:30]:
            parts.append(feat)
        return " ".join(parts)

    def _save_index(self):
        try:
            import faiss
            faiss.write_index(self._index, str(INDEX_PATH))
            with open(IDS_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "id_map": {str(k): v for k, v in self._id_map.items()},
                    "next_id": self._next_id,
                }, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"FAISS 索引保存失败: {e}")