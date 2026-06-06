import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'

const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  breaks: true,
  highlight(str, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs"><code>${
          hljs.highlight(str, { language: lang, ignoreIllegals: true }).value
        }</code></pre>`
      } catch (e) {
        console.debug('[useMarkdown] 高亮失败，使用 escapeHtml 兜底:', e.message)
      }
    }
    return `<pre class="hljs"><code>${md.utils.escapeHtml(str)}</code></pre>`
  }
})

export function useMarkdown() {
  function render(text) {
    if (!text) return ''
    return DOMPurify.sanitize(md.render(text))
  }

  function renderInline(text) {
    if (!text) return ''
    return DOMPurify.sanitize(md.renderInline(text))
  }

  return { render, renderInline }
}
