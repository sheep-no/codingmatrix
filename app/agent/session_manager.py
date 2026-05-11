    async def get_user_sessions(self, user_id: str) -> List[SessionState]:
        """获取用户的活跃会话列表"""
        sessions_dir = Path("./sessions")
        if not sessions_dir.exists():
            return []
        
        user_sessions = []
        for session_file in sessions_dir.glob("*.json"):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                    if session_data.get("user_id") == user_id:
                        status = session_data.get("status", "running")
                        if status in ["running", "paused"]:
                            # 转换为SessionState对象
                            state = SessionState(**session_data)
                            user_sessions.append(state)
            except (json.JSONDecodeError, KeyError, IOError, TypeError):
                continue
        
        return user_sessions