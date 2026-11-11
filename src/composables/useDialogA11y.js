import { nextTick, onBeforeUnmount, watch } from 'vue'

const FOCUSABLE_SELECTOR = [
  'button:not([disabled])',
  '[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])'
].join(', ')

/**
 * 为自建弹窗补充 Escape 关闭、焦点进入/回归与 Tab 循环。
 * `visible` 与 `close` 由调用方提供，弹窗内容根节点需 `tabindex="-1"`。
 */
export function useDialogA11y(dialogRef, visible, close) {
  let previousFocus = null

  const onKeydown = (event) => {
    if (event.key === 'Escape') {
      event.stopPropagation()
      close()
      return
    }
    if (event.key !== 'Tab') return

    const dialog = dialogRef.value
    if (!dialog) return
    const focusable = [...dialog.querySelectorAll(FOCUSABLE_SELECTOR)]
    if (focusable.length === 0) {
      event.preventDefault()
      dialog.focus()
      return
    }

    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  const stopListening = () => document.removeEventListener('keydown', onKeydown)

  watch(visible, async (open) => {
    stopListening()
    if (open) {
      previousFocus = document.activeElement
      document.addEventListener('keydown', onKeydown)
      await nextTick()
      dialogRef.value?.focus()
    } else {
      previousFocus?.focus?.()
      previousFocus = null
    }
  }, { immediate: true })

  onBeforeUnmount(() => {
    stopListening()
    previousFocus?.focus?.()
  })
}
