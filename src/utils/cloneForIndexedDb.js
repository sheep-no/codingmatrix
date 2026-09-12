/**
 * IndexedDB uses the structured clone algorithm, which cannot store Vue
 * proxies, functions, or other host objects. JSON round-trip yields plain data.
 */
export function cloneForIndexedDb(value) {
  return JSON.parse(JSON.stringify(value ?? null, (_key, item) => {
    if (typeof item === 'function') return undefined
    if (item instanceof Error) {
      return {
        name: item.name,
        message: item.message,
        status: item.status,
        retryable: item.retryable
      }
    }
    return item
  }))
}
