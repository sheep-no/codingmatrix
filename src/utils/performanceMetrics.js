export const PERFORMANCE_SNAPSHOT_EVENT = 'codingmatrix:performance-snapshot'

function rounded(value) {
  return Math.round(value * 100) / 100
}

function cloneSnapshot(snapshot) {
  return Object.freeze({ ...snapshot })
}

export function createClsTracker() {
  let maximum = 0
  let sessionValue = 0
  let sessionStart = null
  let previousShift = null

  return entries => {
    for (const entry of entries) {
      if (entry.hadRecentInput) continue
      const startsNewSession = previousShift === null || entry.startTime - previousShift >= 1000 || entry.startTime - sessionStart >= 5000
      if (startsNewSession) {
        sessionStart = entry.startTime
        sessionValue = entry.value
      } else {
        sessionValue += entry.value
      }
      previousShift = entry.startTime
      maximum = Math.max(maximum, sessionValue)
    }
    return rounded(maximum)
  }
}

export function createInpTracker() {
  const interactions = new Map()

  return (entries, interactionCount) => {
    for (const entry of entries) {
      if (!entry.interactionId) continue
      interactions.set(entry.interactionId, Math.max(interactions.get(entry.interactionId) || 0, entry.duration))
    }
    if (interactions.size === 0) return null

    const durations = [...interactions.values()].sort((left, right) => right - left)
    const observedCount = Number.isFinite(interactionCount) && interactionCount > 0 ? interactionCount : interactions.size
    const percentileIndex = Math.min(durations.length - 1, Math.floor(observedCount / 50))
    return rounded(durations[percentileIndex])
  }
}

export function installPerformanceMetrics(router, options = {}) {
  const target = options.target || window
  const clock = options.performance || performance
  const Observer = options.PerformanceObserver || target.PerformanceObserver
  const CustomEventConstructor = options.CustomEvent || target.CustomEvent
  const observers = []
  const stopCallbacks = []
  const buildVersion = options.buildVersion || import.meta.env.VITE_BUILD_VERSION || import.meta.env.VITE_APP_VERSION || import.meta.env.MODE
  let pendingNavigation = null
  let snapshot = {
    schemaVersion: 1,
    buildVersion,
    route: router.currentRoute?.value?.fullPath || target.location?.pathname || '/',
    navigationMs: null,
    lcp: null,
    inp: null,
    cls: 0,
    measuredAt: new Date().toISOString()
  }

  const publish = () => {
    snapshot = cloneSnapshot({ ...snapshot, measuredAt: new Date().toISOString() })
    target.__performanceSnapshot = snapshot
    options.onSnapshot?.(snapshot)
    if (target.dispatchEvent && CustomEventConstructor) {
      target.dispatchEvent(new CustomEventConstructor(PERFORMANCE_SNAPSHOT_EVENT, { detail: snapshot }))
    }
  }

  const observe = (type, callback, extraOptions = {}) => {
    if (!Observer) return
    const supportedTypes = Observer.supportedEntryTypes
    if (Array.isArray(supportedTypes) && !supportedTypes.includes(type)) return
    try {
      const observer = new Observer(list => callback(list.getEntries()))
      observer.observe({ type, buffered: true, ...extraOptions })
      observers.push(observer)
    } catch {
      // Browsers can expose PerformanceObserver while omitting individual entry types.
    }
  }

  const trackCls = createClsTracker()
  const trackInp = createInpTracker()
  observe('largest-contentful-paint', entries => {
    const latest = entries.at(-1)
    if (!latest) return
    snapshot = { ...snapshot, lcp: rounded(latest.startTime) }
    publish()
  })
  observe('layout-shift', entries => {
    snapshot = { ...snapshot, cls: trackCls(entries) }
    publish()
  })
  observe('event', entries => {
    const inp = trackInp(entries, clock.interactionCount)
    if (inp === null) return
    snapshot = { ...snapshot, inp }
    publish()
  }, { durationThreshold: 40 })

  const removeBeforeEach = router.beforeEach(to => {
    pendingNavigation = { route: to.fullPath, startedAt: clock.now() }
  })
  const removeAfterEach = router.afterEach((to, _from, failure) => {
    if (!pendingNavigation) return
    if (!failure) {
      snapshot = {
        ...snapshot,
        route: to.fullPath,
        navigationMs: rounded(clock.now() - pendingNavigation.startedAt)
      }
      publish()
    }
    pendingNavigation = null
  })
  if (typeof removeBeforeEach === 'function') stopCallbacks.push(removeBeforeEach)
  if (typeof removeAfterEach === 'function') stopCallbacks.push(removeAfterEach)

  const handlePageHide = () => publish()
  target.addEventListener?.('pagehide', handlePageHide)
  publish()

  return {
    getSnapshot: () => snapshot,
    stop() {
      for (const observer of observers) observer.disconnect()
      for (const stopCallback of stopCallbacks) stopCallback()
      target.removeEventListener?.('pagehide', handlePageHide)
    }
  }
}
