# vision.py + image_generation.py 视觉家族

> 第一百三十一轮补扫 | v1.132 | 2026-08-17 | 分析对象：`app/utils/vision.py`（292 行，图片理解/OCR/安全审核）+ `app/utils/image_generation.py`（483 行，Kolors 文生图/图生图/修复）
>
> 结论：**两模块均为真实消费——vision_api.py 暴露 analyze_image/extract_text/generate_code/check_image_safety 全部 API、kolors_api.py 暴露文生图/图生图/修复/快捷函数——image_to_base64 双实现、安全审核关键字判断脆弱、图片路径用户可控时存在任意文件读取**。

## 一、模块定位

| 组件 | 位置 | 消费状态 |
|------|------|----------|
| analyze_image（带降级） | vision.py:110 | vision_api.py:140 / Aicode.py:338 真实消费 |
| extract_text_from_image | vision.py:172 | vision_api.py:192 |
| generate_code_from_image | vision.py:194 | vision_api.py:240 |
| check_image_safety | vision.py:260 | vision_api.py:292 |
| text_to_image / image_to_image / inpaint_image | image_generation.py:171/:240/:314 | kolors_api.py 全 API 消费 |
| generate_avatar/landscape/icon | image_generation.py:433/:454/:474 | kolors_api.py:786/:808/:830 |
| _call_vision_model | vision.py:79 | pptx/visual_analyzer.py:150 复用 |

## 二、缺陷清单

### P2（4 项）

- **VS1 [P2] `image_to_base64` 任意文件读取——image_path 用户可控时文件内容 base64 外发 LLM**——vision.py:32-68——`Path(image_path)` 直接读——vision_api.py:140 `analyze_image(image_path, ...)` 若 image_path 来自请求参数 → **任意文件读取并编码发送给视觉模型**（内容外泄给第三方 LLM）——且仅检查扩展名（`../etc/passwd` 无法通过扩展名检查，但可传带合法扩展名的敏感文件，如 `.env`、`/etc/hosts.png` 不存在——符号链接可绕过）。修复方向：强制校验路径在受限 upload 目录内（resolve + is_relative_to）。
- **VS3 [P2] `analyze_image` 降级循环只捕获 HTTPException——其他异常不降级直接传播**——vision.py:159-162——`_call_vision_model` 可能抛 KeyError（:107 `result["choices"][0]` 结构异常）、LLMCallError、httpx 错误——**降级机制只对 HTTPException 生效——其余异常直接 500**——降级形同虚设。
- **VS4 [P2] `check_image_safety` 关键字判断脆弱——可绕过且误报**——vision.py:283-286——`not any(kw in desc.lower() for kw in [...])`——**"不包含暴力"含"暴力"字 → 误判不安全**；模型用英文回复（"This image contains violence"）→ 中文关键词匹配失败 → **误判安全**——内容审核功能形同虚设（安全关键路径）。修复方向：结构化输出（模型返回 JSON safe:true/false + 理由）替代关键词匹配。
- **IG1 [P2] `_save_images_from_response` url 下载用同步 `httpx.get(url, follow_redirects=True)`——阻塞事件循环 + SSRF 面**——image_generation.py:113——同步调用阻塞（10MB+ 图片下载）；url 来自供应商响应——若返回恶意/内网 url → 请求任意地址（WS2/HTTP3 SSRF 家族）。修复方向：改用共享 async client + url 白名单/域名校验。

### P3（11 项）

- **VS2 [P3] stat 大小/扩展名检查与读取分离——TOCTOU**——vision.py:48-58（文件读取期间可能被替换）。
- **VS5 [P3] `VISION_MODEL`/`OCR_MODEL`/`IMAGE_DESC_MODEL` 三常量同为 DeepSeek-OCR，但 `VISION_MODEL_FALLBACK` 首选 GLM——默认与降级链不一致**——vision.py:21-23 vs :72-76。
- **VS7 [P3] `_call_vision_model` 假设 OpenAI 响应格式——`result["choices"][0]["message"]["content"]` 无结构防御**——vision.py:107。
- **VS8 [P3] `generate_code_from_image` 硬编码 `"Qwen/Qwen2.5-7B-Instruct"`——不经 provider 路由/降级**——vision.py:247。
- **VS9 [P3] 安全判断中英混合文本失效——英文描述完全无法判定**——vision.py:283-286（同 VS4 根因）。
- **IG2 [P3] `OUTPUT_DIR` 模块级 `mkdir(exist_ok=True)`——import 副作用 + `./generated_images` 相对路径 CWD 漂移**——image_generation.py:42-43。
- **IG4 [P3] `image_to_base64` 与 vision.py 重复实现——两套相同函数**——image_generation.py:128-152 vs vision.py:32-68——第十三处双轨族。
- **IG6 [P3] 用户 key 失效时静默降级平台 key——用户以为用自己的配额实际走平台**——image_generation.py:386-387。
- **IG7 [P3] `response_format` 硬编码 `"url"` 但 `_save_images_from_response` 优先 `b64_json`——数据格式语义不一致**——image_generation.py:217 vs :99。
- **IG9 [P3] `settings.SILICONFLOW_API_KEY` 未配置时 `Bearer None`——无预校验**——image_generation.py:378/:390。
- **IG10 [P3] generate_avatar/landscape/icon 不透传 api_key_token——用户 key 无法用于快捷函数**——image_generation.py:433-483。

## 三、全库交叉确认

- **任意文件读取家族**：VS1 与 PL2（prompt_loader 路径穿越）同族——**第二条「文件路径 → LLM 上下文」外泄链**——且 VS1 走真实 API 暴露（vision_api）比 PL2 更直接可利用。
- **降级失真家族**：VS3 只捕获 HTTPException、IG6 静默降级平台 key——同 SL3/RG1/SNT2 静默失真族。
- **双实现家族**：IG4（image_to_base64 两套）与 cosine_similarity 三轨、HTTP 客户端四轨同族——第十三处双轨。
- **相对路径家族**：IG2 与 CRY3/PG10/SC3/PMC6/RM7/LA5 同族。
- **SSRF 家族**：IG1 与 WS2/HTTP3 同族——**生成图片下载路径**是新增 SSRF 面。

## 四、测试状态

零单元测试。任意文件读取、降级覆盖、安全判断可靠性、url 下载阻塞均无测试约束。修复建议：① VS1 路径白名单测试；② VS3 降级覆盖全异常测试；③ VS4 结构化安全输出 + 中英文回归测试；④ IG1 异步下载 + url 校验测试；⑤ IG4 收敛 image_to_base64。
