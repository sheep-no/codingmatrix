// Markdown 渲染安全策略：
// 1. 原始 HTML 一律转义，只渲染 Markdown 语法；
// 2. 图片只允许同源与 data:image/，外部图片降级为普通链接；
// 3. 实际渲染的图片带 referrerpolicy="no-referrer"，避免泄露来源页。

export const MARKDOWN_IMAGE_ALLOWED_HOSTS = new Set()

const HTML_ESCAPE_MAP = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
}

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => HTML_ESCAPE_MAP[char])
}

function defaultOrigin() {
  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin
  }
  return 'http://localhost'
}

function resolveHttpUrl(href, baseOrigin) {
  try {
    const url = new URL(href, baseOrigin || defaultOrigin())
    if (!['http:', 'https:'].includes(url.protocol)) return null
    return url
  } catch {
    return null
  }
}

function isSameOrigin(url, baseOrigin) {
  try {
    return url.origin === new URL(baseOrigin || defaultOrigin()).origin
  } catch {
    return false
  }
}

/**
 * 返回可以安全放进 <img src> 的地址；不允许时返回空串。
 * 同源相对路径、同源绝对地址、data:image/* 和显式白名单域名放行。
 */
export function resolveMarkdownImageSrc(href, baseOrigin) {
  const raw = String(href ?? '').trim()
  if (!raw) return ''

  // data:image 仅允许图片 MIME，防止 data:text/html 被当作图片加载。
  if (/^data:/i.test(raw)) {
    return /^data:image\/(png|jpe?g|gif|webp|avif|bmp);/i.test(raw) ? raw : ''
  }

  const url = resolveHttpUrl(raw, baseOrigin)
  if (!url) return ''
  if (isSameOrigin(url, baseOrigin)) return raw
  if (MARKDOWN_IMAGE_ALLOWED_HOSTS.has(url.hostname)) return raw
  return ''
}

function resolveSafeLink(href, baseOrigin) {
  const raw = String(href ?? '').trim()
  if (!raw) return ''
  const url = resolveHttpUrl(raw, baseOrigin)
  return url ? raw : ''
}

function titleAttribute(title) {
  return title ? ` title="${escapeHtml(title)}"` : ''
}

/**
 * 渲染 Markdown 图片。允许的图片带 no-referrer；外部图片降级为链接，
 * 让用户主动决定是否访问，避免被动加载追踪像素。
 */
export function renderMarkdownImage(href, title, alt, baseOrigin) {
  const safeAlt = escapeHtml(alt || '')
  const safeSrc = resolveMarkdownImageSrc(href, baseOrigin)
  const titleAttr = titleAttribute(title)

  if (safeSrc) {
    return `<img src="${escapeHtml(safeSrc)}" alt="${safeAlt}"${titleAttr} loading="lazy" decoding="async" referrerpolicy="no-referrer" class="markdown-image" />`
  }

  const safeLink = resolveSafeLink(href, baseOrigin)
  if (safeLink) {
    const label = safeAlt || '外部图片'
    return `<a href="${escapeHtml(safeLink)}"${titleAttr} target="_blank" rel="noopener noreferrer nofollow" class="markdown-image-link">${label}（外部图片未自动加载）</a>`
  }

  return `<span class="markdown-image-blocked">${safeAlt || '图片已阻止加载'}</span>`
}
