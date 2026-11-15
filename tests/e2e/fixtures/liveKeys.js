/**
 * 真实模型测试的凭证解析。
 *
 * 硅基流动与智谱是两个独立供应商，Key 与 base_url 都不通用：
 * - 硅基流动用于 Qwen/DeepSeek/THUDM/Kolors/BAAI 等托管模型（含免费模型）
 * - 智谱官方用于 glm-4.7-flash / glm-4-flash-250414 / glm-z1-flash
 *
 * 兼容既有 TEST_API_KEY：未区分供应商时按硅基流动处理。
 */

const SILICONFLOW_KEY = process.env.TEST_SILICONFLOW_API_KEY || process.env.TEST_API_KEY || ''
const ZHIPU_KEY = process.env.TEST_ZHIPU_API_KEY || ''

export const LIVE_KEYS = {
  siliconflow: SILICONFLOW_KEY,
  zhipu: ZHIPU_KEY,
}

export const HAS_SILICONFLOW_KEY = Boolean(SILICONFLOW_KEY)
export const HAS_ZHIPU_KEY = Boolean(ZHIPU_KEY)
export const HAS_ANY_LIVE_KEY = HAS_SILICONFLOW_KEY || HAS_ZHIPU_KEY

/** 读取指定供应商的 Key；未提供时返回空串，供 test.skip 判定。 */
export function liveKey(provider) {
  return LIVE_KEYS[provider] || ''
}

/** 该供应商是否已配置 Key。 */
export function hasLiveKey(provider) {
  return Boolean(liveKey(provider))
}
