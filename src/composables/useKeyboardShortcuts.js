import { ref, onMounted, onUnmounted } from 'vue'

const INPUT_SELECTORS = 'input, textarea, [contenteditable="true"], [role="textbox"]'

function isElementInput(el) {
  if (!el) return false
  if (el.matches(INPUT_SELECTORS)) return true
  if (el.isContentEditable) return true
  return false
}

function normalizeKey(e) {
  const parts = []
  if (e.ctrlKey || e.metaKey) parts.push('mod')
  if (e.shiftKey) parts.push('shift')
  if (e.altKey) parts.push('alt')

  let key = e.key
  if (key === ' ') key = ' '
  else if (key.length === 1) key = key.toLowerCase()
  else key = key.toLowerCase()

  parts.push(key)
  return parts.join('+')
}

export function useKeyboardShortcuts() {
  const shortcuts = ref(new Map())
  const sequenceBuffer = ref([])
  const sequenceTimeout = ref(null)
  const SEQUENCE_TIMEOUT_MS = 1500

  function register(shortcut, handler, options = {}) {
    const { preventDefault = true, allowInInput = false } = options
    shortcuts.value.set(shortcut, { handler, preventDefault, allowInInput })

    return () => unregister(shortcut)
  }

  function unregister(shortcut) {
    shortcuts.value.delete(shortcut)
  }

  function registerSequence(keys, handler, options = {}) {
    const { preventDefault = true, allowInInput = false } = options

    const sequenceKey = 'seq:' + keys.join('+')
    shortcuts.value.set(sequenceKey, {
      handler,
      preventDefault,
      allowInInput,
      isSequence: true,
      sequenceKeys: keys.map(k => k.toLowerCase())
    })

    return () => unregister(sequenceKey)
  }

  function handleKeyDown(e) {
    const target = e.target
    const isInInput = isElementInput(target)

    const normalized = normalizeKey(e)

    for (const [shortcut, config] of shortcuts.value) {
      if (config.isSequence) continue

      if (normalized === shortcut) {
        if (isInInput && !config.allowInInput) return
        if (config.preventDefault) e.preventDefault()
        config.handler(e)
        return
      }
    }

    for (const [shortcut, config] of shortcuts.value) {
      if (!config.isSequence) continue
      if (isInInput && !config.allowInInput) continue

      const expectedKey = config.sequenceKeys[sequenceBuffer.value.length]
      if (normalized === expectedKey || normalized.replace('mod+', '') === expectedKey) {
        if (config.preventDefault) e.preventDefault()
        sequenceBuffer.value.push(normalized.replace('mod+', ''))

        if (sequenceTimeout.value) clearTimeout(sequenceTimeout.value)

        if (sequenceBuffer.value.length === config.sequenceKeys.length) {
          config.handler(e)
          sequenceBuffer.value = []
          return
        }

        sequenceTimeout.value = setTimeout(() => {
          sequenceBuffer.value = []
        }, SEQUENCE_TIMEOUT_MS)
        return
      } else {
        sequenceBuffer.value = []
        if (sequenceTimeout.value) clearTimeout(sequenceTimeout.value)
      }
    }
  }

  onMounted(() => {
    window.addEventListener('keydown', handleKeyDown)
  })

  onUnmounted(() => {
    window.removeEventListener('keydown', handleKeyDown)
    if (sequenceTimeout.value) clearTimeout(sequenceTimeout.value)
  })

  return {
    register,
    unregister,
    registerSequence
  }
}
