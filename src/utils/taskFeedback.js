import { getPhaseLabel } from '../constants/agentPhases.js'

export const TASK_FEEDBACK_STATUSES = Object.freeze([
  'queued',
  'running',
  'paused',
  'failed',
  'completed'
])

export const EMPTY_TASK_FEEDBACK = Object.freeze({
  status: 'queued',
  stage: '',
  progress: null,
  elapsedMs: 0,
  error: null,
  nextAction: null
})

const STATUS_ALIASES = Object.freeze({
  created: 'queued',
  idle: 'queued',
  imported: 'queued',
  pending: 'queued',
  progress: 'running',
  started: 'running',
  running: 'running',
  processing: 'running',
  pause_for_approval: 'paused',
  paused: 'paused',
  waiting_for_approval: 'paused',
  waiting_for_confirmation: 'paused',
  cancelled: 'paused',
  canceled: 'paused',
  stopped: 'paused',
  error: 'failed',
  failed: 'failed',
  failure: 'failed',
  complete: 'completed',
  completed: 'completed',
  done: 'completed',
  success: 'completed',
  succeeded: 'completed'
})

const WORKFLOW_EVENT_STATUSES = Object.freeze({
  workflow_started: 'running',
  node_started: 'running',
  node_completed: 'running',
  workflow_completed: 'completed',
  workflow_error: 'failed',
  workflow_paused: 'paused',
  workflow_cancelled: 'paused'
})

const WORKFLOW_EVENT_LABELS = Object.freeze({
  workflow_started: '工作流已启动',
  node_started: '执行工作流节点',
  node_completed: '工作流节点已完成',
  workflow_completed: '工作流已完成',
  workflow_error: '工作流执行失败',
  workflow_paused: '工作流已暂停',
  workflow_cancelled: '工作流已取消'
})

function asObject(value) {
  return value && typeof value === 'object' ? value : {}
}

function hasOwn(object, key) {
  return Object.prototype.hasOwnProperty.call(object, key)
}

function unwrapEvent(input) {
  const event = asObject(input)
  const payload = asObject(event.payload)
  const data = asObject(event.data)
  const state = asObject(event.state)

  if (event.type === 'snapshot_recovery') return { ...event, ...state }
  if (Object.keys(payload).length > 0) return { ...event, ...payload }
  if (Object.keys(data).length > 0) return { ...event, ...data }
  return event
}

function normalizeStatus(value, fallback = 'queued') {
  const normalized = String(value || '').trim().toLowerCase()
  return STATUS_ALIASES[normalized] || fallback
}

function normalizeProgress(value, scale = 100) {
  if (value === null || value === undefined || value === '') return null
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return null
  const percentage = scale === 1 ? numericValue * 100 : numericValue
  return Math.min(100, Math.max(0, percentage))
}

function elapsedFrom(input, context) {
  const directValue = input.elapsedMs ?? input.elapsed_ms ?? context.elapsedMs
  if (Number.isFinite(Number(directValue))) return Math.max(0, Number(directValue))

  const elapsedSeconds = input.elapsed_seconds ?? context.elapsedSeconds
  if (Number.isFinite(Number(elapsedSeconds))) return Math.max(0, Number(elapsedSeconds) * 1000)

  const startedAt = input.startedAt ?? input.started_at ?? context.startedAt
  if (!startedAt) return 0
  const startedTimestamp = typeof startedAt === 'number' ? startedAt : Date.parse(startedAt)
  const now = context.now ?? Date.now()
  return Number.isFinite(startedTimestamp) ? Math.max(0, now - startedTimestamp) : 0
}

function errorFrom(input, context) {
  const error = input.error ?? input.errorMessage ?? input.error_message ?? context.error
  if (error instanceof Error) return error.message
  if (error && typeof error === 'object') return error.message || error.detail || JSON.stringify(error)
  return error ? String(error) : null
}

function nextActionFrom(input, context) {
  const nextAction = input.nextAction ?? input.next_action ?? context.nextAction
  return nextAction ? String(nextAction) : null
}

function agentFeedback(input, context) {
  const eventType = input.type
  const phase = input.phase ?? context.currentPhase
  let sourceStatus = input.status ?? eventType

  if (context.isGenerating) sourceStatus = 'running'
  if (!input.status && !eventType && context.hasFailedStage) sourceStatus = 'failed'
  if (!input.status && !eventType && context.hasGeneratedFiles) sourceStatus = 'completed'

  return {
    status: normalizeStatus(sourceStatus),
    stage: getPhaseLabel(phase) || input.step || context.stage || '',
    progress: normalizeProgress(input.percentage ?? input.progress ?? context.progress),
    elapsedMs: elapsedFrom(input, context),
    error: errorFrom(input, context),
    nextAction: nextActionFrom(input, context)
  }
}

function workflowFeedback(input, context) {
  const event = input.event ?? input.type
  const nodes = input.nodes ?? context.nodes
  let progress = input.percentage ?? input.progress ?? context.progress

  if (progress === undefined && Array.isArray(nodes) && nodes.length > 0) {
    const finished = nodes.filter(node => ['completed', 'failed', 'skipped'].includes(node.status) || node.result).length
    progress = (finished / nodes.length) * 100
  }

  return {
    status: WORKFLOW_EVENT_STATUSES[event] || normalizeStatus(input.status ?? context.status),
    stage: input.stage || input.node_name || input.node?.name || WORKFLOW_EVENT_LABELS[event] || context.stage || '',
    progress: normalizeProgress(progress),
    elapsedMs: elapsedFrom(input, context),
    error: errorFrom(input, context),
    nextAction: nextActionFrom(input, context)
  }
}

function pptFeedback(input, context) {
  const isCancelled = ['cancelled', 'canceled', 'stopped'].includes(String(input.step || '').toLowerCase())
  const status = isCancelled ? 'paused' : normalizeStatus(input.status ?? input.type ?? input.step)
  const progressValue = input.progress ?? input.percentage ?? context.progress
  const progressScale = context.progressScale ?? (
    Number.isFinite(Number(input.sequence)) ? 100 :
      Number(progressValue) >= 0 && Number(progressValue) <= 1 ? 1 : 100
  )

  return {
    status,
    stage: isCancelled ? 'PPT 任务已取消' : input.step || input.stage || context.stage || '',
    progress: normalizeProgress(progressValue, progressScale),
    elapsedMs: elapsedFrom(input, context),
    error: errorFrom(input, context),
    nextAction: nextActionFrom(input, context)
  }
}

function imageFeedback(input, context) {
  let sourceStatus = input.status
  if (input.error || context.error) sourceStatus = 'failed'
  else if (input.isGenerating ?? context.isGenerating) sourceStatus = 'running'
  else if ((input.images ?? context.images)?.length > 0) sourceStatus = 'completed'

  const mode = input.mode ?? context.mode
  return {
    status: normalizeStatus(sourceStatus),
    stage: input.stage || context.stage || (mode === 'img2img' ? '图生图' : mode === 'text2img' ? '文生图' : ''),
    progress: normalizeProgress(input.progress ?? context.progress),
    elapsedMs: elapsedFrom(input, context),
    error: errorFrom(input, context),
    nextAction: nextActionFrom(input, context)
  }
}

export function normalizeTaskFeedback(domain, source = {}, context = {}) {
  const input = unwrapEvent(source)

  switch (domain) {
    case 'agent':
      return agentFeedback(input, context)
    case 'workflow':
      return workflowFeedback(input, context)
    case 'ppt':
      return pptFeedback(input, context)
    case 'image':
    case 'drawing':
      return imageFeedback(input, context)
    default:
      return {
        status: normalizeStatus(input.status ?? input.type ?? context.status),
        stage: input.stage || input.step || context.stage || '',
        progress: normalizeProgress(input.progress ?? input.percentage ?? context.progress),
        elapsedMs: elapsedFrom(input, context),
        error: errorFrom(input, context),
        nextAction: nextActionFrom(input, context)
      }
  }
}

export function createTaskFeedback(overrides = {}) {
  return { ...EMPTY_TASK_FEEDBACK, ...overrides }
}

export function mergeTaskFeedback(previous, domain, source = {}, context = {}) {
  const current = createTaskFeedback(previous)
  const input = unwrapEvent(source)
  const event = input.event ?? input.type
  const normalizationContext = source.type === 'snapshot_recovery' ? context : { ...current, ...context }
  const normalized = normalizeTaskFeedback(domain, source, normalizationContext)

  if (source.type === 'snapshot_recovery') {
    return createTaskFeedback(normalized)
  }

  const statusFromEvent = hasOwn(STATUS_ALIASES, String(event || '').toLowerCase())
  const hasStatus = hasOwn(input, 'status') || statusFromEvent ||
    (domain === 'workflow' && hasOwn(WORKFLOW_EVENT_STATUSES, event)) ||
    (domain === 'image' && ['isGenerating', 'images', 'error'].some(key => hasOwn(input, key)))
  const hasStage = ['stage', 'step', 'phase', 'node_name'].some(key => hasOwn(input, key)) ||
    Boolean(input.node?.name) || (domain === 'workflow' && hasOwn(WORKFLOW_EVENT_LABELS, event))
  const hasProgress = ['progress', 'percentage'].some(key => hasOwn(input, key)) ||
    Array.isArray(input.nodes) || Array.isArray(context.nodes)
  const hasError = ['error', 'errorMessage', 'error_message'].some(key => hasOwn(input, key))
  const hasNextAction = ['nextAction', 'next_action'].some(key => hasOwn(input, key))

  const next = {
    ...current,
    elapsedMs: normalized.elapsedMs
  }
  if (hasStatus) next.status = normalized.status
  if (hasStage) next.stage = normalized.stage
  if (hasProgress) next.progress = normalized.progress
  if (hasError) next.error = normalized.error
  if (hasNextAction) next.nextAction = normalized.nextAction

  if (hasStatus && ['running', 'completed'].includes(next.status) && !hasError) next.error = null
  if (hasStatus && next.status === 'completed' && !hasNextAction) next.nextAction = normalized.nextAction

  return next
}
