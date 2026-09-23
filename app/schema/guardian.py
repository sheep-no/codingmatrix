from pydantic import BaseModel, Field, field_validator

# restart_cmd 会被 process_guard 交给 shell 执行（create_subprocess_shell），
# 命令链与替换语法可拼接任意命令，构成持久化 RCE 面（SD7）。这里只做输入端
# 的格式约束：拒绝命令链、重定向与替换语法，保留 systemctl/docker/pm2 等
# 单条命令的正常用法。
FORBIDDEN_SHELL_CHARS = (";", "|", "&", "`", "$", ">", "<", "\n", "\r", "\\")


class StartGuard(BaseModel):
    service_name:str
    port:int
    restart_cmd: str = Field(min_length=1, max_length=512)

    @field_validator("restart_cmd")
    @classmethod
    def validate_restart_cmd(cls, value: str) -> str:
        command = value.strip()
        if not command:
            raise ValueError("restart_cmd 不能为空")
        if command.startswith("#"):
            raise ValueError("restart_cmd 不能是注释")
        found = sorted({ch for ch in FORBIDDEN_SHELL_CHARS if ch in command})
        if found:
            raise ValueError(
                "restart_cmd 不允许包含 shell 元字符: " + " ".join(found)
            )
        return command
