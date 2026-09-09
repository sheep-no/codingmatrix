import { describe, expect, it } from 'vitest'
import {
  createTaskFeedback,
  mergeTaskFeedback,
  normalizeTaskFeedback,
  TASK_FEEDBACK_STATUSES
} from './taskFeedback.js'

const EXPECTED_KEYS = ['elapsedMs', 'error', 'nextAction', 'progress', 'stage', 'status']

function expectContract(feedback) {
  expect(Object.keys(feedback).sort()).toEqual(EXPECTED_KEYS)
  expect(TASK_FEEDBACK_STATUSES).toContain(feedback.status)
}

describe('normalizeTaskFeedback', () => {
  it.each([
    ['agent', { type: 'progress', data: { phase: 'generating_file', percentage: 0 } }, 'running', '正在生成文件', 0],
    ['agent', { type: 'done', phase: 'generation_complete', percentage: 100 }, 'completed', '项目生成完成', 100],
    ['workflow', { event: 'workflow_started' }, 'running', '工作流已启动', null],
    ['workflow', { event: 'workflow_completed', elapsed_seconds: 2.5 }, 'completed', '工作流已完成', null],
    ['image', {}, 'running', '图生图', null]
  ])('maps %s state into the shared contract', (domain, input, status, stage, progress) => {
    const context = domain === 'image' ? { isGenerating: true, mode: 'img2img' } : {}
    const feedback = normalizeTaskFeedback(domain, input, context)

    expectContract(feedback)
    expect(feedback).toMatchObject({ status, stage, progress })
  })

  it('calculates workflow progress from terminal node states', () => {
    const feedback = normalizeTaskFeedback('workflow', { status: 'running' }, {
      nodes: [
        { status: 'completed' },
        { status: 'failed' },
        { status: 'skipped' },
        { status: 'pending' }
      ]
    })

    expect(feedback.progress).toBe(75)
  })

  it('normalizes PPT fractional progress and event replay wrappers', () => {
    const feedback = normalizeTaskFeedback('ppt', {
      type: 'task.progress',
      sequence: 4,
      payload: { status: 'running', step: 'rendering', progress: 42 }
    })

    expect(feedback).toEqual({
      status: 'running',
      stage: 'rendering',
      progress: 42,
      elapsedMs: 0,
      error: null,
      nextAction: null
    })
  })

  it('keeps SQL replay progress on a 0 to 100 scale', () => {
    expect(normalizeTaskFeedback('ppt', {
      type: 'task.progress',
      sequence: 1,
      status: 'running',
      progress: 1
    }).progress).toBe(1)

    expect(normalizeTaskFeedback('ppt', {
      type: 'progress',
      status: 'running',
      progress: 0.42
    }).progress).toBe(42)
  })

  it('rebuilds PPT feedback from a recovery snapshot', () => {
    const feedback = normalizeTaskFeedback('ppt', {
      type: 'snapshot_recovery',
      revision: 8,
      state: {
        status: 'completed',
        stage: 'quality_review',
        progress: 100,
        elapsed_ms: 3200,
        next_action: '预览演示文稿'
      }
    })

    expect(feedback).toMatchObject({
      status: 'completed',
      stage: 'quality_review',
      progress: 100,
      elapsedMs: 3200,
      nextAction: '预览演示文稿'
    })
  })

  it.each(['cancelled', 'canceled', 'stopped'])('maps %s into a resumable paused state', status => {
    const feedback = normalizeTaskFeedback('ppt', { type: 'error', step: status, error: '任务中止' })

    expect(feedback).toMatchObject({
      status: 'paused',
      stage: 'PPT 任务已取消',
      error: '任务中止'
    })
  })

  it('preserves errors and derives elapsed time from a start timestamp', () => {
    const feedback = normalizeTaskFeedback('image', {}, {
      error: new Error('模型不可用'),
      mode: 'text2img',
      startedAt: 1000,
      now: 3500
    })

    expect(feedback).toMatchObject({
      status: 'failed',
      stage: '文生图',
      elapsedMs: 2500,
      error: '模型不可用'
    })
  })

  it('clamps invalid progress values to the supported range', () => {
    expect(normalizeTaskFeedback('agent', { status: 'running', percentage: -10 }).progress).toBe(0)
    expect(normalizeTaskFeedback('agent', { status: 'running', percentage: 150 }).progress).toBe(100)
    expect(normalizeTaskFeedback('agent', { status: 'running', percentage: 'unknown' }).progress).toBeNull()
  })
})

describe('mergeTaskFeedback', () => {
  it('updates one incremental field while preserving the existing task context', () => {
    const previous = createTaskFeedback({
      status: 'running',
      stage: '生成文件',
      progress: 35,
      elapsedMs: 1200
    })

    const feedback = mergeTaskFeedback(previous, 'agent', {
      type: 'thinking',
      message: '继续分析依赖'
    }, { now: 2200 })

    expect(feedback).toMatchObject({
      status: 'running',
      stage: '生成文件',
      progress: 35,
      elapsedMs: 1200
    })
  })

  it('replaces stale incremental fields with a recovery snapshot', () => {
    const feedback = mergeTaskFeedback(
      createTaskFeedback({ status: 'paused', stage: '旧阶段', progress: 20, error: '连接中断' }),
      'ppt',
      {
        type: 'snapshot_recovery',
        state: { status: 'running', stage: 'rendering', progress: 68, elapsed_ms: 5000 }
      }
    )

    expect(feedback).toEqual({
      status: 'running',
      stage: 'rendering',
      progress: 68,
      elapsedMs: 5000,
      error: null,
      nextAction: null
    })
  })
})
