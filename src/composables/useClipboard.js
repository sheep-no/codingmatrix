import { useToast } from './useToast'

export function useClipboard() {
  const { success, error: showError } = useToast()

  async function copy(text) {
    if (!text) {
      showError('复制内容为空')
      return false
    }

    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text)
        success('已复制到剪贴板')
        return true
      }

      const textArea = document.createElement('textarea')
      textArea.value = text
      textArea.style.position = 'fixed'
      textArea.style.left = '-9999px'
      textArea.style.top = '-9999px'
      document.body.appendChild(textArea)
      textArea.focus()
      textArea.select()

      try {
        document.execCommand('copy')
        success('已复制到剪贴板')
        return true
      } catch (err) {
        showError('复制失败，请手动复制')
        return false
      } finally {
        document.body.removeChild(textArea)
      }
    } catch (err) {
      showError('复制失败，请手动复制')
      return false
    }
  }

  return { copy }
}
