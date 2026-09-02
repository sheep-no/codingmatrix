/**
 * Consume newline-delimited JSON or SSE data without losing split chunks.
 */
export async function consumeJsonStream(response, onData, { onParseError } = {}) {
  if (!response.body) return

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

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
    const { done, value } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const lines = buffer.split(/\r?\n/)
    buffer = lines.pop() || ''
    lines.forEach(processLine)
    if (done) break
  }

  if (buffer.trim()) processLine(buffer)
}
