"""
数据库服务单元测试

测试范围:
    - 用户服务 (获取用户、邮箱检查)
    - 权限服务 (获取权限、创建权限)
    - 聊天记录服务 (保存对话、获取历史)
    - 历史记录服务 (保存历史、搜索历史)

标记:
    @pytest.mark.unit - 单元测试
    @pytest.mark.database - 数据库相关测试
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Tuple

from app.models.user import User
from app.models.Permission import Permission
from app.models.history import History
from app.models.chat_history import ChatHistory
from app.db.user_sql_server import get_user_by_email, check_email_exists
from app.db.permission_service import PermissionService
from app.db.chat_history_service import ChatHistoryService
from app.db.add_history import save_history_to_db
from app.db.search_history import search_history_to_db, get_conversation_history


# =============================================================================
# 用户服务测试
# =============================================================================

@pytest.mark.unit
@pytest.mark.database
class TestUserService:
    """用户数据库服务测试"""

    @pytest.mark.asyncio
    async def test_get_user_by_email_success(
        self,
        test_db: AsyncSession,
        test_user: User
    ):
        """测试通过邮箱成功获取用户"""
        user = await get_user_by_email(test_db, "test@example.com")
        
        assert user is not None
        assert user.email == "test@example.com"
        assert user.username == "testuser"
        assert user.id == test_user.id

    @pytest.mark.asyncio
    async def test_get_user_by_email_not_found(self, test_db: AsyncSession):
        """测试获取不存在的用户"""
        user = await get_user_by_email(test_db, "nonexistent@example.com")
        
        assert user is None

    @pytest.mark.asyncio
    async def test_get_user_by_email_case_sensitive(
        self,
        test_db: AsyncSession,
        test_user: User
    ):
        """测试邮箱查询大小写敏感"""
        user = await get_user_by_email(test_db, "TEST@EXAMPLE.COM")
        
        # SQLite 默认大小写敏感
        assert user is None

    @pytest.mark.asyncio
    async def test_check_email_exists_true(
        self,
        test_db: AsyncSession,
        test_user: User
    ):
        """测试检查邮箱存在返回 True"""
        exists = await check_email_exists(test_db, "test@example.com")
        
        assert exists is True

    @pytest.mark.asyncio
    async def test_check_email_exists_false(self, test_db: AsyncSession):
        """测试检查邮箱不存在返回 False"""
        exists = await check_email_exists(test_db, "nonexistent@example.com")
        
        assert exists is False

    @pytest.mark.asyncio
    async def test_check_email_exists_performance(
        self,
        test_db: AsyncSession,
        test_user: User
    ):
        """测试邮箱检查性能 (只查询 ID)"""
        exists = await check_email_exists(test_db, "test@example.com")
        
        assert exists is True


# =============================================================================
# 权限服务测试
# =============================================================================

@pytest.mark.unit
@pytest.mark.database
class TestPermissionService:
    """权限服务测试"""

    @pytest.mark.asyncio
    async def test_get_permission_success(
        self,
        test_db: AsyncSession,
        test_user: User
    ):
        """测试成功获取用户权限"""
        perm_service = PermissionService(test_db)
        permission = await perm_service.get_permission(test_user.id)
        
        assert permission is not None
        assert permission.permission_level == "normal"
        assert permission.user_id == test_user.id

    @pytest.mark.asyncio
    async def test_get_permission_not_found(self, test_db: AsyncSession):
        """测试获取不存在的权限"""
        perm_service = PermissionService(test_db)
        permission = await perm_service.get_permission(99999)
        
        assert permission is None

    @pytest.mark.asyncio
    async def test_create_permission_success(
        self,
        test_db: AsyncSession,
        test_user: User
    ):
        """测试创建权限成功"""
        perm_service = PermissionService(test_db)
        permission = await perm_service.create_permission(
            user_id=test_user.id + 1,
            level="super"
        )
        
        assert permission is not None
        assert permission.permission_level == "super"
        assert permission.user_id == test_user.id + 1

    @pytest.mark.asyncio
    async def test_create_permission_if_not_exists(
        self,
        test_db: AsyncSession
    ):
        """测试权限不存在时创建"""
        user = User(
            username="temp_user",
            email="temp@example.com",
            hashed_password="hashed"
        )
        test_db.add(user)
        await test_db.flush()
        
        perm_service = PermissionService(test_db)
        permission = await perm_service.create_permission_if_not_exists(
            user_id=user.id,
            level="normal"
        )
        
        assert permission is not None
        assert permission.permission_level == "normal"
        
        await test_db.delete(user)
        await test_db.commit()

    @pytest.mark.asyncio
    async def test_create_permission_existing_returns_existing(
        self,
        test_db: AsyncSession,
        test_user: User
    ):
        """测试权限已存在时返回已有记录"""
        perm_service = PermissionService(test_db)
        permission1 = await perm_service.create_permission_if_not_exists(
            user_id=test_user.id,
            level="normal"
        )
        
        permission2 = await perm_service.create_permission_if_not_exists(
            user_id=test_user.id,
            level="super"
        )
        
        assert permission1.id == permission2.id
        assert permission1.permission_level == "normal"


# =============================================================================
# 聊天记录服务测试
# =============================================================================

@pytest.mark.unit
@pytest.mark.database
class TestChatHistoryService:
    """聊天记录服务测试"""

    @pytest.mark.asyncio
    async def test_save_conversation_turn_success(
        self,
        test_db: AsyncSession,
        test_user: User
    ):
        """测试保存一轮对话"""
        history_service = ChatHistoryService(test_db)
        
        await history_service.save_conversation_turn(
            user_id=test_user.id,
            user_content="你好",
            assistant_content="你好，有什么可以帮助你的？",
            model="Qwen/Qwen2.5-7B-Instruct",
            tokens_used=100
        )
        
        result = await test_db.execute(
            select(ChatHistory).where(ChatHistory.user_id == test_user.id)
        )
        records = result.scalars().all()
        
        assert len(records) >= 2  # 用户消息 + 助手回复

    @pytest.mark.asyncio
    async def test_get_user_history_pagination(
        self,
        test_db: AsyncSession,
        test_user: User
    ):
        """测试获取用户历史记录分页"""
        history_service = ChatHistoryService(test_db)
        
        for i in range(15):
            await history_service.save_conversation_turn(
                user_id=test_user.id,
                user_content=f"测试{i}",
                assistant_content=f"回复{i}",
                model="test_model",
                tokens_used=50
            )
        
        records, total = await history_service.get_user_history(
            user_id=test_user.id,
            limit=10,
            offset=0
        )
        
        assert len(records) == 10
        assert total >= 15

    @pytest.mark.asyncio
    async def test_get_lightweight_context(
        self,
        test_db: AsyncSession,
        test_user: User
    ):
        """测试获取轻量级上下文"""
        history_service = ChatHistoryService(test_db)
        
        for i in range(10):
            await history_service.save_conversation_turn(
                user_id=test_user.id,
                user_content=f"对话{i}",
                assistant_content=f"回复{i}",
                model="test_model",
                tokens_used=50
            )
        
        recent_messages, summary = await history_service.get_lightweight_context(
            user_id=test_user.id,
            max_messages=5
        )
        
        assert isinstance(recent_messages, list)
        assert len(recent_messages) <= 5
        assert summary is None or isinstance(summary, str)

    @pytest.mark.asyncio
    async def test_get_recent_context_with_summary(
        self,
        test_db: AsyncSession,
        test_user: User
    ):
        """测试获取带摘要的近期上下文"""
        history_service = ChatHistoryService(test_db)
        
        await history_service.save_conversation_turn(
            user_id=test_user.id,
            user_content="测试对话",
            assistant_content="测试回复",
            model="test_model",
            tokens_used=50
        )
        
        message_list, summary_text = await history_service.get_recent_context(
            user_id=test_user.id
        )
        
        assert isinstance(message_list, list)
        assert summary_text is None or isinstance(summary_text, str)


# =============================================================================
# 历史记录服务测试
# =============================================================================

@pytest.mark.unit
@pytest.mark.database
class TestHistoryService:
    """历史记录服务测试"""

    @pytest.mark.asyncio
    async def test_save_history_to_db_new_conversation(
        self,
        test_db: AsyncSession,
        test_user: User
    ):
        """测试保存新对话历史"""
        conversation_id = await save_history_to_db(
            db=test_db,
            user_id=str(test_user.id),
            conversation_id=None,
            prompt="测试问题",
            thinking=None,
            response="测试回答"
        )
        
        assert conversation_id is not None
        
        result = await test_db.execute(
            select(History).where(History.user_id == test_user.id)
        )
        records = result.scalars().all()
        
        assert len(records) >= 1

    @pytest.mark.asyncio
    async def test_save_history_to_db_existing_conversation(
        self,
        test_db: AsyncSession,
        test_user: User
    ):
        """测试保存已有对话历史"""
        conv_id = await save_history_to_db(
            db=test_db,
            user_id=str(test_user.id),
            conversation_id=None,
            prompt="问题 1",
            thinking=None,
            response="回答 1"
        )
        
        new_conv_id = await save_history_to_db(
            db=test_db,
            user_id=str(test_user.id),
            conversation_id=conv_id,
            prompt="问题 2",
            thinking=None,
            response="回答 2"
        )
        
        assert new_conv_id == conv_id

    @pytest.mark.asyncio
    async def test_search_history_to_db_with_keyword(
        self,
        test_db: AsyncSession,
        test_user: User
    ):
        """测试关键词搜索历史记录"""
        await save_history_to_db(
            db=test_db,
            user_id=str(test_user.id),
            conversation_id=None,
            prompt="测试搜索",
            thinking=None,
            response="包含搜索关键词的回答"
        )
        
        await test_db.commit()
        
        histories = await search_history_to_db(
            db=test_db,
            user_id=str(test_user.id),
            prompt_keyword="搜索",
            limit=10,
            offset=0
        )
        
        assert len(histories) >= 1

    @pytest.mark.asyncio
    async def test_search_history_to_db_pagination(
        self,
        test_db: AsyncSession,
        test_user: User
    ):
        """测试历史记录搜索分页"""
        for i in range(25):
            await save_history_to_db(
                db=test_db,
                user_id=str(test_user.id),
                conversation_id=None,
                prompt=f"测试{i}",
                thinking=None,
                response=f"回答{i}"
            )
        
        await test_db.commit()
        
        histories_page1 = await search_history_to_db(
            db=test_db,
            user_id=str(test_user.id),
            limit=10,
            offset=0
        )
        
        histories_page2 = await search_history_to_db(
            db=test_db,
            user_id=str(test_user.id),
            limit=10,
            offset=10
        )
        
        assert len(histories_page1) == 10
        assert len(histories_page2) == 10

    @pytest.mark.asyncio
    async def test_get_conversation_history(
        self,
        test_db: AsyncSession,
        test_user: User
    ):
        """测试获取对话历史详情"""
        conv_id = await save_history_to_db(
            db=test_db,
            user_id=str(test_user.id),
            conversation_id=None,
            prompt="问题 1",
            thinking=None,
            response="回答 1"
        )
        
        await save_history_to_db(
            db=test_db,
            user_id=str(test_user.id),
            conversation_id=conv_id,
            prompt="问题 2",
            thinking=None,
            response="回答 2"
        )
        
        histories = await get_conversation_history(
            db=test_db,
            user_id=str(test_user.id),
            conversation_id=conv_id,
            last_history_id=None,
            limit=20
        )
        
        assert len(histories) >= 2

    @pytest.mark.asyncio
    async def test_get_conversation_history_pagination(
        self,
        test_db: AsyncSession,
        test_user: User
    ):
        """测试对话历史分页加载"""
        conv_id = await save_history_to_db(
            db=test_db,
            user_id=str(test_user.id),
            conversation_id=None,
            prompt="问题 1",
            thinking=None,
            response="回答 1"
        )
        
        last_id = None
        for i in range(25):
            result = await save_history_to_db(
                db=test_db,
                user_id=str(test_user.id),
                conversation_id=conv_id,
                prompt=f"问题{i}",
                thinking=None,
                response=f"回答{i}"
            )
            last_id = result
        
        histories = await get_conversation_history(
            db=test_db,
            user_id=str(test_user.id),
            conversation_id=conv_id,
            last_history_id=last_id,
            limit=10
        )
        
        assert len(histories) <= 10


# =============================================================================
# Mock 测试
# =============================================================================

@pytest.mark.unit
class TestDatabaseMock:
    """数据库 Mock 测试"""

    @pytest.mark.asyncio
    async def test_mock_get_user_by_email(self):
        """测试 Mock 获取用户"""
        from unittest.mock import patch, MagicMock, AsyncMock
        
        mock_user = MagicMock()
        mock_user.email = "mock@example.com"
        mock_user.username = "mock_user"
        mock_user.id = 123
        
        with patch(
            "app.db.user_sql_server.get_user_by_email",
            return_value=mock_user
        ):
            pass

    @pytest.mark.asyncio
    async def test_mock_permission_service(self):
        """测试 Mock 权限服务"""
        from unittest.mock import patch, MagicMock, AsyncMock
        
        mock_permission = MagicMock()
        mock_permission.permission_level = "super"
        
        with patch.object(
            PermissionService,
            'get_permission',
            new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_permission
            
            service = PermissionService(MagicMock())
            perm = await service.get_permission(123)
            
            assert perm.permission_level == "super"
            mock_get.assert_called_once_with(123)
