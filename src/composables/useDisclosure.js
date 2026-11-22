import { ref } from 'vue'

// 快速连点会先打开再立刻关闭，看起来像「点了没反应」。
// 折叠类交互共用一个最小间隔，让双击/连点只生效一次。
export const DISCLOSURE_GUARD_MS = 350

function createGuard(guardMs) {
  let lastInvokeAt = 0
  const canInvoke = () => {
    const now = Date.now()
    if (now - lastInvokeAt < guardMs) return false
    lastInvokeAt = now
    return true
  }
  return { canInvoke, reset: () => { lastInvokeAt = 0 } }
}

// 指针移动超过该距离视为拖拽/取消，不再触发动作。
const DRAG_CANCEL_PX = 8

/**
 * 点击兜底：正常情况仍然由 click 执行动作。
 *
 * 按钮获得焦点时浏览器可能滚动容器或触发重排，mouseup 落点一旦变化，
 * click 就不会派发到按钮上，表现为「只出现焦点环、没有反应」。
 * pointerdown 一定能到达按钮，因此在按下时记录一次按压，
 * 若随后的 click 没有到来，就在 pointerup 后补执行一次。
 *
 * 放在 pointerup 之后而不是 pointerdown 立即执行，是为了避免打开弹窗的
 * 按钮在 mouseup 前就挂载全屏遮罩，导致随后的 click 落在遮罩上又把它关掉。
 *
 * 键盘 Enter/Space 不产生 pointerdown，仍通过 click（detail 为 0）执行。
 */
function createPressHandlers({ canInvoke, invoke }) {
  let pending = null
  let fallbackTimer = null
  // 兜底执行后，吞掉随之而来的那次迟到 click，避免同一次按压执行两遍。
  // 用布尔标记而不是时间窗：关闭大弹层等重渲染会让 click 延迟数百毫秒，
  // 固定时间窗一旦过期，迟到的 click 就会把兜底刚打开的菜单又关掉。
  let swallowNextClick = false

  const detach = () => {
    window.removeEventListener('pointerup', onWindowPointerup, true)
    window.removeEventListener('pointercancel', onWindowPointercancel, true)
  }

  const clearPending = () => {
    pending = null
    detach()
    if (fallbackTimer) {
      clearTimeout(fallbackTimer)
      fallbackTimer = null
    }
  }

  function onWindowPointerup(event) {
    const press = pending
    detach()
    if (!press) return
    const scheduleFallback = () => {
      fallbackTimer = setTimeout(() => {
        fallbackTimer = null
        if (!pending) return
        clearPending()
        swallowNextClick = true
        if (canInvoke()) invoke()
      }, 0)
    }
    const distance = Number.isFinite(event.clientX) && Number.isFinite(event.clientY)
      ? Math.hypot(event.clientX - press.x, event.clientY - press.y)
      : 0
    if (distance > DRAG_CANCEL_PX) {
      clearPending()
      return
    }
    // 滚动中按下再抬起时，元素会在按住期间移走，抬起点落到列表里的相邻控件上。
    // 元素发生位移说明是滚动/重排把落点换了位置，意图仍是原控件；
    // 元素没动而指针落到相邻控件，才是真的滑过去，应当让位。
    if (press.rect && press.element?.isConnected) {
      const current = press.element.getBoundingClientRect()
      const moved = Math.abs(current.left - press.rect.left) > 1 ||
        Math.abs(current.top - press.rect.top) > 1
      if (moved) {
        scheduleFallback()
        return
      }
    }
    // 指针滑到另一个可点击控件上时，浏览器会把 click 派发给它，
    // 这里让位给那个控件，避免一次按压触发两个动作。
    const otherControl = event.target?.closest?.('button, a[href], [role="button"], input, textarea, select')
    if (otherControl && otherControl !== press.element) {
      clearPending()
      return
    }
    // click 紧接 pointerup 派发；先排到任务末尾，click 一到就取消兜底。
    scheduleFallback()
  }

  function onWindowPointercancel() {
    clearPending()
  }

  const onPointerdown = event => {
    if (event.button !== undefined && event.button !== 0) return
    if (event.isPrimary === false) return
    // 触摸的 click 由浏览器保证，交给 click 以免滑动时误触。
    if (event.pointerType === 'touch') return
    clearPending()
    // 新手势开始，之前兜底留下的迟到 click 不应影响这次按压。
    swallowNextClick = false
    const element = event.currentTarget
    const rect = element && typeof element.getBoundingClientRect === 'function'
      ? element.getBoundingClientRect()
      : null
    pending = { x: event.clientX ?? 0, y: event.clientY ?? 0, element, rect }
    window.addEventListener('pointerup', onWindowPointerup, true)
    window.addEventListener('pointercancel', onWindowPointercancel, true)
  }

  const onClick = event => {
    clearPending()
    // 只吞鼠标/触摸来源的迟到 click（detail > 0）。键盘 Enter/Space 的
    // click 没有 pointerdown 前置，不能被上一次按压的残留标记吞掉。
    if (swallowNextClick && (event?.detail ?? 0) > 0) {
      swallowNextClick = false
      return
    }
    swallowNextClick = false
    if (canInvoke()) invoke()
  }

  return { pointerdown: onPointerdown, click: onClick }
}

/**
 * 给普通动作按钮用（返回、导入、新建会话等）。
 * 正常由 click 执行；click 丢失时由 pointerup 兜底补执行一次。
 */
export function usePressAction(action) {
  const pressHandlers = createPressHandlers({
    canInvoke: () => true,
    invoke: action
  })
  return pressHandlers
}

export function useDisclosure(initial = false, { guardMs = DISCLOSURE_GUARD_MS, onChange } = {}) {
  const isOpen = ref(initial)
  const guard = createGuard(guardMs)

  const setOpen = value => {
    isOpen.value = value
    onChange?.(value)
  }
  const open = () => { setOpen(true) }
  const close = () => {
    setOpen(false)
    // 通过外部点击/Escape 关闭后，允许立刻重新打开。
    guard.reset()
  }
  const toggle = () => {
    if (!guard.canInvoke()) return
    setOpen(!isOpen.value)
  }
  const pressHandlers = createPressHandlers({
    canInvoke: guard.canInvoke,
    invoke: () => { setOpen(!isOpen.value) }
  })

  return { isOpen, open, close, toggle, pressHandlers }
}

export function useAccordion(initialKey = null, { guardMs = DISCLOSURE_GUARD_MS } = {}) {
  const activeKey = ref(initialKey)
  const guards = new Map()
  const handlers = new Map()

  const guardFor = key => {
    if (!guards.has(key)) guards.set(key, createGuard(guardMs))
    return guards.get(key)
  }

  const open = key => { activeKey.value = key }
  const close = () => {
    activeKey.value = null
    guards.forEach(guard => guard.reset())
  }
  const toggle = key => {
    const guard = guardFor(key)
    if (!guard.canInvoke()) return
    activeKey.value = activeKey.value === key ? null : key
  }
  // 每个折叠项独立计时，快速切换不同项仍然立即响应。
  const pressHandlersFor = key => {
    if (!handlers.has(key)) {
      const guard = guardFor(key)
      handlers.set(key, createPressHandlers({
        canInvoke: guard.canInvoke,
        invoke: () => { activeKey.value = activeKey.value === key ? null : key }
      }))
    }
    return handlers.get(key)
  }

  return { activeKey, open, close, toggle, pressHandlersFor }
}
