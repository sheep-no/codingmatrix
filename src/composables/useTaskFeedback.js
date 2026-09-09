import { computed, getCurrentScope, onScopeDispose, ref } from 'vue'
import { createTaskFeedback, mergeTaskFeedback } from '@/utils/taskFeedback'

const TERMINAL_STATUSES = new Set(['failed', 'completed'])

export function useTaskFeedback(domain, initial = {}) {
  const feedback = ref(createTaskFeedback(initial))
  const connectionStatus = ref('connected')
  const lastSequence = ref(null)
  const lastRevision = ref(null)
  let startedAt = initial.startedAt || null
  let ticker = null

  const hasFeedback = computed(() => (
    feedback.value.status !== 'queued' ||
    Boolean(feedback.value.stage || feedback.value.error || feedback.value.nextAction)
  ))

  function stopTicker() {
    if (ticker !== null) {
      clearInterval(ticker)
      ticker = null
    }
  }

  function syncTicker() {
    if (feedback.value.status !== 'running') {
      stopTicker()
      return
    }
    if (ticker !== null) return
    ticker = setInterval(() => {
      if (startedAt) feedback.value = { ...feedback.value, elapsedMs: Math.max(0, Date.now() - startedAt) }
    }, 1000)
  }

  function reset(overrides = {}) {
    stopTicker()
    startedAt = overrides.startedAt || null
    lastSequence.value = null
    lastRevision.value = null
    connectionStatus.value = 'connected'
    feedback.value = createTaskFeedback(overrides)
  }

  function update(source = {}, context = {}) {
    const sequence = Number(source.sequence)
    const revision = Number(source.revision)
    const isSnapshot = source.type === 'snapshot_recovery'

    if (isSnapshot && Number.isFinite(revision)) {
      if (lastRevision.value !== null && revision < lastRevision.value) return { applied: false, stale: true }
      lastRevision.value = revision
    }

    if (!isSnapshot && Number.isFinite(sequence)) {
      if (lastSequence.value !== null && sequence <= lastSequence.value) return { applied: false, stale: true }
      const expectedSequence = (lastSequence.value ?? 0) + 1
      if (sequence > expectedSequence) {
        markReconnecting('检测到任务事件缺口，正在恢复最新状态')
        return { applied: false, gap: true }
      }
      lastSequence.value = sequence
    }

    feedback.value = mergeTaskFeedback(feedback.value, domain, source, {
      ...context,
      startedAt: context.startedAt || startedAt,
      now: context.now || Date.now()
    })
    if (isSnapshot) {
      connectionStatus.value = 'connected'
      if (Number.isFinite(sequence)) lastSequence.value = sequence
    }
    syncTicker()
    return { applied: true }
  }

  function start(source = {}, context = {}) {
    startedAt = context.startedAt || Date.now()
    connectionStatus.value = 'connected'
    feedback.value = createTaskFeedback({
      ...mergeTaskFeedback(createTaskFeedback(), domain, { status: 'running', ...source }, {
        ...context,
        startedAt,
        now: Date.now()
      }),
      error: null,
      nextAction: null
    })
    syncTicker()
  }

  function complete(source = {}, context = {}) {
    update({ status: 'completed', ...source }, context)
    stopTicker()
  }

  function fail(error, source = {}, context = {}) {
    update({ status: 'failed', error, ...source }, context)
    stopTicker()
  }

  function markReconnecting(message = '连接中断，正在恢复任务状态') {
    connectionStatus.value = 'reconnecting'
    feedback.value = {
      ...feedback.value,
      status: TERMINAL_STATUSES.has(feedback.value.status) ? feedback.value.status : 'paused',
      error: message,
      nextAction: '恢复连接后继续接收进度'
    }
    stopTicker()
  }

  function markDisconnected(message = '连接已中断，当前内容已保留') {
    connectionStatus.value = 'disconnected'
    feedback.value = {
      ...feedback.value,
      status: TERMINAL_STATUSES.has(feedback.value.status) ? feedback.value.status : 'paused',
      error: message,
      nextAction: '重新连接后继续'
    }
    stopTicker()
  }

  function markConnected() {
    connectionStatus.value = 'connected'
    if (feedback.value.status === 'paused' && feedback.value.nextAction?.includes('连接')) {
      feedback.value = { ...feedback.value, status: 'running', error: null, nextAction: null }
      syncTicker()
    }
  }

  if (getCurrentScope()) onScopeDispose(stopTicker)

  return {
    feedback,
    connectionStatus,
    lastSequence,
    hasFeedback,
    reset,
    update,
    start,
    complete,
    fail,
    markReconnecting,
    markDisconnected,
    markConnected,
    dispose: stopTicker
  }
}
