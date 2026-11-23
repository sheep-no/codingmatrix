import { describe, expect, it } from 'vitest'
import {
  MARKDOWN_IMAGE_ALLOWED_HOSTS,
  escapeHtml,
  renderMarkdownImage,
  resolveMarkdownImageSrc
} from './markdown'

const ORIGIN = 'https://chat.example.com'

describe('markdown html escaping', () => {
  it('escapes raw html instead of emitting elements', () => {
    expect(escapeHtml('<img src=x onerror=alert(1)>')).toBe('&lt;img src=x onerror=alert(1)&gt;')
    expect(escapeHtml('<script>alert(1)</script>')).toBe('&lt;script&gt;alert(1)&lt;/script&gt;')
  })
})

describe('markdown image policy', () => {
  it('allows same-origin and data images', () => {
    expect(resolveMarkdownImageSrc('/static/a.png', ORIGIN)).toBe('/static/a.png')
    expect(resolveMarkdownImageSrc('https://chat.example.com/a.png', ORIGIN))
      .toBe('https://chat.example.com/a.png')
    expect(resolveMarkdownImageSrc('data:image/png;base64,AAAA', ORIGIN))
      .toBe('data:image/png;base64,AAAA')
  })

  it('rejects cross-origin images and non-image data uris', () => {
    expect(resolveMarkdownImageSrc('https://example.com/pixel.gif', ORIGIN)).toBe('')
    expect(resolveMarkdownImageSrc('data:text/html,<script>alert(1)</script>', ORIGIN)).toBe('')
    expect(resolveMarkdownImageSrc('javascript:alert(1)', ORIGIN)).toBe('')
  })

  it('honors the explicit image host allowlist', () => {
    MARKDOWN_IMAGE_ALLOWED_HOSTS.add('cdn.example.net')
    try {
      expect(resolveMarkdownImageSrc('https://cdn.example.net/a.png', ORIGIN))
        .toBe('https://cdn.example.net/a.png')
      expect(resolveMarkdownImageSrc('https://other.example.net/a.png', ORIGIN)).toBe('')
    } finally {
      MARKDOWN_IMAGE_ALLOWED_HOSTS.delete('cdn.example.net')
    }
  })

  it('renders allowed images with no-referrer and lazy loading', () => {
    const html = renderMarkdownImage('/a.png', '标题', '示意', ORIGIN)
    expect(html).toContain('src="/a.png"')
    expect(html).toContain('referrerpolicy="no-referrer"')
    expect(html).toContain('loading="lazy"')
    expect(html).toContain('alt="示意"')
  })

  it('downgrades external images to a user-initiated link', () => {
    const html = renderMarkdownImage('https://example.com/pixel.gif', '', '像素', ORIGIN)
    expect(html).not.toContain('<img')
    expect(html).toContain('href="https://example.com/pixel.gif"')
    expect(html).toContain('rel="noopener noreferrer nofollow"')
    expect(html).toContain('外部图片未自动加载')
  })

  it('escapes alt text so attributes cannot be broken out of', () => {
    const html = renderMarkdownImage('/a.png', '', '"><script>alert(1)</script>', ORIGIN)
    expect(html).not.toContain('<script>')
    expect(html).toContain('&quot;&gt;')
  })
})
