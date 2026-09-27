"""AgentMemory 持久化往返回归测试（MEM8）。

save_to_storage/load_from_storage 曾把 async def 辅助函数传给 asyncio.to_thread：
工作线程只创建未被 await 的协程对象——save 不写文件却返回 True（报告≠实际），
load 拿到协程对象后 .get() 抛错恒返回 False。
"""
import json

from app.agent.memory import AgentMemory


class TestStorageRoundtrip:
    async def test_save_actually_writes_and_load_restores(self, tmp_path):
        path = tmp_path / "memory.json"

        memory = AgentMemory()
        memory.add_user_message("实现登录接口")
        memory.add_assistant_message("好的，正在实现")
        memory.add_knowledge("项目使用 FastAPI", key="stack", importance=0.9)
        memory.add_reflection("避免循环导入")

        assert await memory.save_to_storage(str(path)) is True

        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["session_id"] == memory.session_id
        assert [e["content"] for e in payload["conversation"]] == [
            "实现登录接口",
            "好的，正在实现",
        ]
        assert payload["knowledge"][0]["content"] == "项目使用 FastAPI"
        assert payload["reflections"][0]["content"] == "避免循环导入"

        restored = AgentMemory()
        assert await restored.load_from_storage(str(path)) is True

        assert [e.content for e in restored.conversation.get_recent(10)] == [
            "实现登录接口",
            "好的，正在实现",
        ]
        assert restored.knowledge.get("stack").importance == 0.9
        assert [e.content for e in restored.reflection.get_recent(10)] == ["避免循环导入"]

    async def test_load_missing_file_returns_false(self, tmp_path):
        assert await AgentMemory().load_from_storage(str(tmp_path / "absent.json")) is False

    async def test_load_reads_prewritten_file(self, tmp_path):
        path = tmp_path / "prewritten.json"
        path.write_text(
            json.dumps({
                "session_id": "session_123",
                "created_at": 123.0,
                "conversation": [{
                    "id": None,
                    "type": "user",
                    "content": "历史消息",
                    "metadata": {},
                    "timestamp": 1.0,
                    "importance": 1.0,
                }],
                "knowledge": [],
                "reflections": [],
            }),
            encoding="utf-8",
        )

        restored = AgentMemory()
        assert await restored.load_from_storage(str(path)) is True
        assert restored.session_id == "session_123"
        assert [e.content for e in restored.conversation.get_recent(10)] == ["历史消息"]
