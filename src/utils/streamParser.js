/**
 * Consume newline-delimited JSON or SSE data without losing split chunks.
 */
export async function consumeJsonStream(response, onData, { onParseError, signal } = {}) {
  if (!response.body) return

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const readWithAbort = async () => {
    if (!signal) return reader.read()
    if (signal.aborted) {
      throw new DOMException('Aborted', 'AbortError')
    }

    return new Promise((resolve, reject) => {
      const onAbort = () => {
        reader.cancel().catch(() => undefined)
        reject(new DOMException('Aborted', 'AbortError'))
      }

      signal.addEventListener('abort', onAbort, { once: true })
      reader.read().then(resolve, reject).finally(() => signal.removeEventListener('abort', onAbort))
    })
  }

  const processLine = line => {
    const trimmed = line.trim()
    if (!trimmed || trimmed === 'data: [DONE]') return

    const payload = trimmed.startsWith('data:') ? trimmed.slice(5).trim() : trimmed
    try {
      onData(JSON.parse(payload))
    } catch (error) {
      onParseError?.(error, line)
    }
  }

  while (true) {
    const { done, value } = await readWithAbort()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const lines = buffer.split(/\r?\n/)
    buffer = lines.pop() || ''
    lines.forEach(processLine)
    if (done) break
  }

  if (buffer.trim()) processLine(buffer)
}
