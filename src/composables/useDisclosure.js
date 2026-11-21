import { ref } from 'vue'

// 快速连点会先打开再立刻关闭，看起来像「点了没反应」。
// 折叠类交互共用一个最小间隔，让双击/连点只生效一次。
export const DISCLOSURE_GUARD_MS = 350

function createGuard(guardMs) {
  let lastToggleAt = 0
  const canToggle = () => {
    const now = Date.now()
    if (now - lastToggleAt < guardMs) return false
    lastToggleAt = now
    return true
  }
  return { canToggle, reset: () => { lastToggleAt = 0 } }
}

export function useDisclosure(initial = false, { guardMs = DISCLOSURE_GUARD_MS } = {}) {
  const isOpen = ref(initial)
  const guard = createGuard(guardMs)

  const open = () => { isOpen.value = true }
  const close = () => {
    isOpen.value = false
    // 通过外部点击/Escape 关闭后，允许立刻重新打开。
    guard.reset()
  }
  const toggle = () => {
    if (!guard.canToggle()) return
    isOpen.value = !isOpen.value
  }

  return { isOpen, open, close, toggle }
}

export function useAccordion(initialKey = null, { guardMs = DISCLOSURE_GUARD_MS } = {}) {
  const activeKey = ref(initialKey)
  const lastToggleAt = new Map()
  const canToggle = key => {
    const now = Date.now()
    // 每个折叠项独立计时，快速切换不同项仍然立即响应。
    if (now - (lastToggleAt.get(key) || 0) < guardMs) return false
    lastToggleAt.set(key, now)
    return true
  }

  const open = key => { activeKey.value = key }
  const close = () => { activeKey.value = null }
  const toggle = key => {
    if (!canToggle(key)) return
    activeKey.value = activeKey.value === key ? null : key
  }

  return { activeKey, open, close, toggle }
}
