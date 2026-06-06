/**
 * 统一错误处理工具
 * 为前端所有 catch {} 块提供一致的错误日志和用户提示
 *
 * 用法:
 *   import { handleError, silentError } from '@/utils/errorHandler'
 *
 *   try {
 *     ...
 *   } catch (e) {
 *     handleError(e, '加载数据失败', { silent: true })
 *   }
 */

import { ElMessage } from 'element-plus'

/**
 * 统一处理错误
 * @param {Error|string} error - 错误对象或消息
 * @param {string} context - 错误上下文描述（如"加载数据失败"）
 * @param {Object} options
 * @param {boolean} options.silent - 不显示给用户（仅记录日志）
 * @param {boolean} options.toast - 显示 ElMessage 错误提示（默认 true）
 * @param {string} options.level - 'debug' | 'info' | 'warn' | 'error'
 */
export function handleError(error, context = '', options = {}) {
  const { silent = false, toast = !silent, level = 'warn' } = options
  const message = error?.message || error?.toString() || String(error)
  const fullMessage = context ? `${context}: ${message}` : message

  // 控制台日志
  if (level === 'debug') console.debug('[Error]', fullMessage)
  else if (level === 'info') console.info('[Error]', fullMessage)
  else if (level === 'error') console.error('[Error]', fullMessage, error)
  else console.warn('[Error]', fullMessage)

  // 用户提示
  if (toast && !silent) {
    ElMessage({
      type: 'error',
      message: fullMessage,
      duration: 3000,
      showClose: true,
    })
  }
}

/**
 * 静默处理错误（仅记录日志，不提示用户）
 * 用于降级场景（如 storage 不可用、highlight 失败）
 */
export function silentError(error, context = '', level = 'debug') {
  handleError(error, context, { silent: true, toast: false, level })
}

/**
 * 兼容性 try/catch 包装器
 * @param {Function} fn - 要执行的函数
 * @param {string} context - 错误上下文
 * @param {*} defaultValue - 出错时的默认返回值
 */
export async function tryAsync(fn, context = '', defaultValue = null) {
  try {
    return await fn()
  } catch (e) {
    handleError(e, context)
    return defaultValue
  }
}

/**
 * 同步版本的 try/catch 包装器
 */
export function trySync(fn, context = '', defaultValue = null) {
  try {
    return fn()
  } catch (e) {
    handleError(e, context)
    return defaultValue
  }
}
