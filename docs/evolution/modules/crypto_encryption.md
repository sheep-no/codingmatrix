# crypto.py + encryption.py 加密双轨

> 第一百一十六轮补扫 | v1.117 | 2026-08-17 | 分析对象：`app/utils/crypto.py`（166 行，RSA 直解）+ `app/utils/encryption.py`（235 行，RSA+AES 混合）
>
> 结论：**加密双轨——两模块各自定义同名 `RSAKeyManager`、共用同一对密钥文件（`keys/rsa_private.pem` / `keys/rsa_public.pem`），但加解密语义不同、单例独立、加载时机独立**——是 SCT6 家族（secret 处理）与 CodeValidator 式「同名异构双轨」的又一实例。

## 一、模块定位

| 维度 | crypto.py | encryption.py |
|------|-----------|---------------|
| 用途 | API Key 安全传输（RSA 公钥加密，后端私钥直解） | 登录密码安全传输（前端 RSA+AES 混合加密） |
| 密钥算法 | 单一 RSA-2048 OAEP（SHA-256） | RSA-2048 OAEP 包 AES-CBC |
| 消费者 | `app/api/v1/apikey.py:158/:184` | `app/api/v1/auth.py:38/:109` |
| 单例 | `get_rsa_key_manager()` 无锁 | `get_key_manager()` asyncio 双检锁 |
| 密钥文件 | `keys/rsa_private.pem` + `keys/rsa_public.pem` | 同左（默认路径字符串版） |
| 私钥权限 | :97 `os.chmod(0o600)` | :87-107 无 chmod（默认 umask） |

**共用密钥文件**：crypto.py:26 `Path("keys")` → `keys/rsa_private.pem`；encryption.py:203 默认 `keys/rsa_private.pem`——**同路径**。两模块的密钥对可共存（同 RSA 密钥可服务两种加解密），但以下轮换/权限问题使共用成为风险点。

## 二、缺陷清单

### P2（3 项）

- **CRY1 [P2] 密钥加载失败静默重生成——覆盖共用密钥文件，双模块密钥轮换不同步（SCT6 家族）**——crypto.py:71-75 `_load_keys` 任一异常 → `_generate_keys()` + `_save_keys()` **覆盖写盘**；encryption.py:79-86 同（FileNotFoundError → 生成+保存，其他异常 → 仅内存生成）。两模块单例独立、各自触发加载——**任一方在另一方已加载后因瞬时文件损坏/权限/并发读失败触发重生成**，会覆盖文件并留下与另一模块内存私钥不一致的新密钥——此后 apikey（crypto 旧私钥内存）与 auth（encryption 新文件加载后新私钥）**对同一前端公钥加密的密文解密行为分裂**。且重生成无告警无提示——历史密文（API Key/登录数据）全部不可解。修复方向：密钥加载失败禁止自动重生成覆盖（改抛错+人工介入），或引入密钥版本号 + 轮换流程。
- **CRY2 [P2] encryption.py 版私钥明文落盘权限过宽（无 chmod）**——encryption.py:87-107 `save_keys` 写私钥后**未收紧权限**——默认 umask（通常 0o644）——**磁盘明文私钥任何用户可读**（与 crypto.py:97 `0o600` 不对称）。配合 `NoEncryption()`（:97 明文 PEM）——整个密钥文件无保护。修复方向：save_keys 统一 `os.chmod(private_key_path, 0o600)` + key_dir 目录 0o700。
- **CRY3 [P2] 默认相对路径 `keys/`——CWD 漂移下密钥位置漂移、多 worker 各自生成（GRD3 家族）**——crypto.py:26 `Path("keys")`、encryption.py:203 `"keys/rsa_private.pem"` 均为相对路径——部署 CWD 不同 → 找不到密钥文件 → **各自生成新密钥对** → 前端已缓存的旧公钥加密数据在新 worker 上解密失败（登录/API Key 随机失败）。且无密钥版本号——前端无法感知公钥更换。修复方向：密钥路径改为绝对配置（环境变量/配置文件注入），前端公钥带版本标识。

### P3（4 项）

- **CRY4 [P3] 密钥无密码保护（`NoEncryption`）——磁盘明文，依赖文件权限兜底**——crypto.py:84 与 encryption.py:97 均 `serialization.NoEncryption()`——私钥无口令加密——一旦文件权限失守（CRY2）即泄露。修复方向：私钥加密口令经环境变量注入。
- **CRY5 [P3] 解密失败静默吞错——统一抛无上下文 ValueError（EC3 家族）**——encryption.py:134-136 `logger.error` 后抛 `ValueError("解密失败")`、:193-195 拼 `str(e)` 但日志仅记外层——API 层拿到的是无原因的通用失败——排障只能翻日志。crypto.py:113 base64 解码失败同样直接冒泡无包装。
- **CRY6 [P3] crypto.py 单例无锁 + 无双检**——crypto.py:154-158 `get_rsa_key_manager` 直接判断赋值（无锁）——多线程首次并发 init 竞态（encryption.py:208-211 有 async 双检——**两模块模式不对称**）。crypto.py 版若被线程化调用路径触发，可重复初始化覆盖全局单例。
- **CRY7 [P3] encryption.py 构造误配：只给一个路径即静默生成内存密钥并覆盖**——encryption.py:43-46 仅当 `not private_key_path or not public_key_path` 才生成内存密钥，但 `save_keys` :89 仅在两路径齐全时写盘——**若调用方传了路径但文件不存在 → FileNotFoundError 分支生成+保存（:81-82）→ 覆盖同名文件**；若只传一个路径 → 生成内存密钥但 save_keys 不写盘——`decrypt_login_data` 用随机内存私钥永远解密失败。修复方向：构造参数校验（两路径必须同时给出或同时为空）。

## 三、全库交叉确认

- **SCT6 家族（secret 处理）**：密钥文件落盘、权限、轮换均属敏感数据处理——CRY1/CRY2 与 SCT6 直接相关；guardrails FORBIDDEN_PATTERNS 对 keys/*.pem 无拦截（GRD7 家族确认不覆盖本项目密钥文件）。
- **EC3 家族（错误静默丢弃）**：CRY5 与 file_operator grep errors='ignore'（FO7）、guardrails 空 except 同族。
- **GRD3 家族（相对路径 CWD 漂移）**：CRY3 与 crypto.py:26 / encryption.py:203 一致。
- **双轨模式**：与 CodeValidator 双轨（spec_first_generate 详档）、路径安全四轨道（file_operator 详档）同模式——两模块做同一件事（RSA 密钥管理 + 解密）却有两份实现、两份单例、两份密钥文件读写逻辑。
- **密钥轮换缺失**：全库无公钥版本化 / 密钥轮换 API——前端公钥缓存后密钥重建即失联（CRY1/CRY3 共同放大）。

## 四、测试状态

零单元测试。CRY2 私钥权限、CRY3 路径漂移、CRY1 文件损坏恢复均无测试约束。修复建议：密钥管理测试——① 生成→落盘权限断言（0o600）；② 文件损坏→加载失败→禁止覆盖（抛错断言）；③ CWD 不同路径下密钥路径一致性；④ 双模块共用文件对加载同一密钥断言。
