const defaultSchedule = callback => requestAnimationFrame(callback)
const defaultCancel = handle => cancelAnimationFrame(handle)

export function createStreamUpdateBatcher(
  commit,
  { schedule = defaultSchedule, cancel = defaultCancel } = {}
) {
  const pending = new Map()
  let scheduledHandle = null

  const flush = () => {
    if (scheduledHandle !== null) {
      cancel(scheduledHandle)
      scheduledHandle = null
    }

    const updates = [...pending.values()]
    pending.clear()
    updates.forEach(update => commit(update))
  }

  const enqueue = update => {
    const existing = pending.get(update.key)
    const current = existing
      ? {
          ...existing,
          ...update,
          responseDelta: existing.responseDelta,
          reasoningDelta: existing.reasoningDelta
        }
      : { ...update, responseDelta: '', reasoningDelta: '' }
    current.responseDelta += update.responseDelta || ''
    current.reasoningDelta += update.reasoningDelta || ''
    pending.set(update.key, current)

    if (scheduledHandle === null) {
      scheduledHandle = schedule(() => {
        scheduledHandle = null
        flush()
      })
    }
  }

  return { enqueue, flush, dispose: flush }
}
