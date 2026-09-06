from app.agent.context_assembler import ContextAssembler, MCPToolDescriptor
from app.agent.memory import MemoryEntry
from app.agent.retrieval.models import RetrievalChunk, RetrievalResult


def test_context_assembler_orders_sources_redacts_secrets_and_hashes():
    assembler = ContextAssembler(max_chars=1000)
    envelope = assembler.assemble(
        task_id="task-1",
        stage="generating",
        items=[
            {"source": "memory", "source_id": "m1", "content": "token=private-value", "priority": 20},
            {"source": "requirement", "source_id": "r1", "content": "build API", "priority": 100},
        ],
    )

    assert [item.source.value for item in envelope.items] == ["requirement", "memory"]
    assert "private-value" not in envelope.items[1].content
    assert envelope.redacted_count == 1
    assert len(envelope.context_hash) == 64


def test_context_assembler_injects_scoped_rag_and_deduplicates_content():
    retrieval = RetrievalResult(chunks=[
        RetrievalChunk(content="known contract", source_type="rag", source_id="a", score=0.9),
        RetrievalChunk(content="known contract", source_type="memory", source_id="b", score=0.8),
    ])

    envelope = ContextAssembler().assemble(
        task_id="task-1", stage="planning", retrieval=retrieval
    )

    assert len(envelope.items) == 1
    assert envelope.items[0].metadata["source_type"] == "rag"


def test_mcp_descriptor_enforces_read_write_scope():
    descriptor = MCPToolDescriptor(
        name="workspace_reader", capability="workspace", read_scopes=("project",),
        write_scopes=(), project_scope="project-1",
    )

    assert descriptor.allows("read", "project") is True
    assert descriptor.allows("write", "project") is False


def test_context_assembler_adds_memory_and_mcp_metadata():
    envelope = ContextAssembler().assemble(
        task_id="task-1", stage="generating",
        memory_entries=[MemoryEntry(id="m1", content="remember this", importance=0.8)],
        mcp_tools={"reader": {"kind": "skill", "capability": "workspace", "priority": 70}},
    )

    assert {item.source.value for item in envelope.items} == {"memory", "skill"}
    assert envelope.items[0].content_hash
