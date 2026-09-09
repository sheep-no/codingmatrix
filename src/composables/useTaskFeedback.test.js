import { afterEach, describe, expect, it, vi } from 'vitest'
import { useTaskFeedback } from './useTaskFeedback.js'

describe('useTaskFeedback', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('tracks elapsed time while a task is running', () => {
    vi.useFakeTimers()
    vi.setSystemTime(1000)
    const task = useTaskFeedback('agent')

    task.start({ stage: '分析需求' })
    vi.advanceTimersByTime(2000)

    expect(task.feedback.value.elapsedMs).toBe(2000)
    task.dispose()
  })

  it('stops elapsed time when a task reaches a terminal state', () => {
    vi.useFakeTimers()
    vi.setSystemTime(1000)
    const task = useTaskFeedback('agent')

    task.start({ stage: '生成文件' })
    vi.advanceTimersByTime(2000)
    task.complete({ stage: '生成完成', progress: 100 })
    vi.advanceTimersByTime(3000)

    expect(task.feedback.value).toMatchObject({ status: 'completed', elapsedMs: 2000 })
    task.dispose()
  })

  it('ignores duplicate events and requests recovery for a sequence gap', () => {
    const task = useTaskFeedback('ppt')
    task.start({ step: 'planning', progress: 0 })

    expect(task.update({ sequence: 1, status: 'running', step: 'assets', progress: 25 }).applied).toBe(true)
    expect(task.update({ sequence: 1, status: 'running', step: 'duplicate', progress: 30 }).stale).toBe(true)
    expect(task.update({ sequence: 3, status: 'running', step: 'rendering', progress: 70 }).gap).toBe(true)

    expect(task.feedback.value).toMatchObject({ status: 'paused', stage: 'assets', progress: 25 })
    expect(task.connectionStatus.value).toBe('reconnecting')
    task.dispose()
  })

  it('applies a recovery snapshot and advances the replay cursor', () => {
    const task = useTaskFeedback('ppt')
    task.update({ sequence: 1, status: 'running', step: 'assets', progress: 30 })

    const result = task.update({
      type: 'snapshot_recovery',
      sequence: 5,
      revision: 3,
      state: { status: 'running', stage: 'rendering', progress: 80, elapsed_ms: 4000 }
    })

    expect(result.applied).toBe(true)
    expect(task.lastSequence.value).toBe(5)
    expect(task.connectionStatus.value).toBe('connected')
    expect(task.feedback.value).toMatchObject({ status: 'running', stage: 'rendering', progress: 80 })
    task.dispose()
  })

  it('rejects stale recovery snapshots by revision', () => {
    const task = useTaskFeedback('ppt')
    task.update({
      type: 'snapshot_recovery',
      sequence: 5,
      revision: 3,
      state: { status: 'running', stage: 'rendering', progress: 80 }
    })

    const result = task.update({
      type: 'snapshot_recovery',
      sequence: 4,
      revision: 2,
      state: { status: 'running', stage: 'stale', progress: 40 }
    })

    expect(result).toEqual({ applied: false, stale: true })
    expect(task.lastSequence.value).toBe(5)
    expect(task.feedback.value).toMatchObject({ stage: 'rendering', progress: 80 })
    task.dispose()
  })

  it.each(['completed', 'failed'])('preserves the %s terminal state after disconnecting', status => {
    const task = useTaskFeedback('workflow')
    task.update({ event: status === 'completed' ? 'workflow_completed' : 'workflow_error' })

    task.markDisconnected('连接已断开')

    expect(task.feedback.value).toMatchObject({ status, error: '连接已断开' })
    expect(task.connectionStatus.value).toBe('disconnected')
    task.dispose()
  })

  it('resets replay cursors and connection state', () => {
    const task = useTaskFeedback('ppt')
    task.update({ sequence: 1, status: 'running', step: 'assets', progress: 20 })
    task.markDisconnected()

    task.reset({ stage: '等待新任务' })

    expect(task.lastSequence.value).toBeNull()
    expect(task.connectionStatus.value).toBe('connected')
    expect(task.feedback.value).toMatchObject({ status: 'queued', stage: '等待新任务' })
    task.dispose()
  })
})
