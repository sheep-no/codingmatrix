/**
 * 标准 SSE（text/event-stream）帧解析器。
 *
 * 后端当前发送 `data: {json}\n\n` 单行帧；本解析器同时覆盖标准协议的
 * 其余合法形态：`data:` 无空格、多行 `data:` 拼接、`event:`/`id:` 字段、
 * `:` 开头注释行（心跳）、CRLF 行尾、跨 chunk 的帧边界与 UTF-8 BOM。
 * 尾帧 `[DONE]` 以 data 值形式透传给 onEvent，由调用方判定终止。
 */
export function createSseParser({ onEvent, onParseError } = {}) {
  let buffer = ''
  let sawBom = false

  const stripBom = (text) => {
    if (sawBom) return text
    sawBom = true
    return text.charCodeAt(0) === 0xfeff ? text.slice(1) : text
  }

  const dispatchFrame = (frame) => {
    if (frame === '') return
    let eventName = 'message'
    let dataLines = []
    let lastEventId = null
    for (const rawLine of frame.split(/\r\n|\n|\r/)) {
      if (rawLine === '' || rawLine.startsWith(':')) continue
      const colon = rawLine.indexOf(':')
      const field = colon === -1 ? rawLine : rawLine.slice(0, colon)
      let value = colon === -1 ? '' : rawLine.slice(colon + 1)
      if (value.startsWith(' ')) value = value.slice(1)
      if (field === 'data') {
        dataLines.push(value)
      } else if (field === 'event') {
        eventName = value
      } else if (field === 'id') {
        if (!value.includes('\0')) lastEventId = value
      }
    }
    if (dataLines.length === 0) return
    if (typeof onEvent === 'function') {
      onEvent({ event: eventName, data: dataLines.join('\n'), id: lastEventId })
    }
  }

  const consumeBuffer = () => {
    // 空行是帧分隔符：\n\n、\r\n\r\n（CRLF）以及 \r\r
    let index
    while ((index = buffer.search(/\r\n\r\n|\n\n|\r\r/)) !== -1) {
      const matchLength = buffer.startsWith('\r\n\r\n', index) ? 4 : 2
      const frame = buffer.slice(0, index)
      buffer = buffer.slice(index + matchLength)
      dispatchFrame(frame)
    }
  }

  return {
    push(chunk) {
      buffer += stripBom(chunk)
      consumeBuffer()
    },
    flush() {
      const frame = buffer
      buffer = ''
      try {
        dispatchFrame(frame)
      } catch (error) {
        if (typeof onParseError === 'function') onParseError(error)
      }
    }
  }
}
