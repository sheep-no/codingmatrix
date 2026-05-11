import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'

const FOCUSABLE_SELECTORS = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
  'details > summary',
  'area[href]',
  'iframe',
  'object',
  'embed',
  '[contenteditable]'
].join(', ')

export function useFocusTrap(containerRef, options = {}) {
  const {
    autoFocus = true,
    escapeDeactivates = true,
    onEscape = null,
    returnFocusOnDeactivate = true
  } = options

  const isActivated = ref(false)
  let previousActiveElement = null
  let focusableElements = []
  let firstFocusable = null
  let lastFocusable = null

  const getFocusableElements = (container) => {
    const elements = Array.from(container.querySelectorAll(FOCUSABLE_SELECTORS))
    return elements.filter(el => {
      return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
    })
  }

  const trapFocus = (event) => {
    if (!isActivated.value) return

    const container = containerRef?.value
    if (!container) return

    focusableElements = getFocusableElements(container)
    if (focusableElements.length === 0) return

    firstFocusable = focusableElements[0]
    lastFocusable = focusableElements[focusableElements.length - 1]

    if (event.key === 'Tab') {
      if (event.shiftKey) {
        if (document.activeElement === firstFocusable) {
          event.preventDefault()
          lastFocusable.focus()
        }
      } else {
        if (document.activeElement === lastFocusable) {
          event.preventDefault()
          firstFocusable.focus()
        }
      }
    }
  }

  const handleEscape = (event) => {
    if (event.key === 'Escape' && escapeDeactivates) {
      if (onEscape && typeof onEscape === 'function') {
        onEscape()
      } else {
        deactivate()
      }
    }
  }

  const activate = async () => {
    previousActiveElement = document.activeElement

    await nextTick()

    const container = containerRef?.value
    if (!container) return

    container.setAttribute('aria-modal', 'true')
    isActivated.value = true

    focusableElements = getFocusableElements(container)

    if (autoFocus && focusableElements.length > 0) {
      const autoFocusEl = container.querySelector('[autofocus]')
      if (autoFocusEl) {
        autoFocusEl.focus()
      } else {
        focusableElements[0].focus()
      }
    }

    document.addEventListener('keydown', trapFocus)
    document.addEventListener('keydown', handleEscape)
  }

  const deactivate = () => {
    const container = containerRef?.value
    if (container) {
      container.removeAttribute('aria-modal')
    }

    isActivated.value = false

    document.removeEventListener('keydown', trapFocus)
    document.removeEventListener('keydown', handleEscape)

    if (returnFocusOnDeactivate && previousActiveElement) {
      previousActiveElement.focus()
      previousActiveElement = null
    }
  }

  onMounted(() => {
    if (isActivated.value) {
      activate()
    }
  })

  onUnmounted(() => {
    if (isActivated.value) {
      deactivate()
    }
  })

  watch(isActivated, (newValue) => {
    if (newValue) {
      activate()
    } else {
      deactivate()
    }
  })

  return {
    isActivated,
    activate,
    deactivate
  }
}

export default useFocusTrap
