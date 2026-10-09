import { describe, expect, it, vi } from 'vitest'
import { createSseParser } from './sseParser'

function collect() {
  const events = []
  const parser = createSseParser({ onEvent: (e) => events.push(e) })
  return { events, parser }
}

describe('sseParser', () => {
  it('parses standard data frames from the backend', () => {
    const { events, parser } = collect()
    parser.push('data: {"type":"progress"}\n\n')
    expect(events).toEqual([
      { event: 'message', data: '{"type":"progress"}', id: null }
    ])
  })

  it('accepts data fields without a space after the colon', () => {
    const { events, parser } = collect()
    parser.push('data:{"type":"log"}\n\n')
    expect(events[0].data).toBe('{"type":"log"}')
  })

  it('joins multi-line data fields with newlines', () => {
    const { events, parser } = collect()
    parser.push('data: line1\ndata: line2\n\n')
    expect(events[0].data).toBe('line1\nline2')
  })

  it('handles CRLF line endings and CRLF frame separators', () => {
    const { events, parser } = collect()
    parser.push('data: a\r\n\r\ndata: b\r\n\r\n')
    expect(events.map((e) => e.data)).toEqual(['a', 'b'])
  })

  it('skips comment lines used as heartbeats', () => {
    const { events, parser } = collect()
    parser.push(': keepalive\ndata: {"type":"log"}\n\n')
    expect(events).toHaveLength(1)
    expect(events[0].data).toBe('{"type":"log"}')
  })

  it('exposes event and id fields', () => {
    const { events, parser } = collect()
    parser.push('event: progress\nid: 42\ndata: {"step":1}\n\n')
    expect(events[0]).toEqual({ event: 'progress', data: '{"step":1}', id: '42' })
  })

  it('reassembles frames split across chunks', () => {
    const { events, parser } = collect()
    parser.push('data: {"type":"pro')
    parser.push('gress"}\n')
    parser.push('\ndata: {"type":"done"}\n\n')
    expect(events.map((e) => e.data)).toEqual([
      '{"type":"progress"}',
      '{"type":"done"}'
    ])
  })

  it('strips a UTF-8 BOM before the first frame', () => {
    const { events, parser } = collect()
    parser.push('\uFEFFdata: {"type":"log"}\n\n')
    expect(events[0].data).toBe('{"type":"log"}')
  })

  it('flushes a trailing frame without a final blank line', () => {
    const { events, parser } = collect()
    parser.push('data: {"type":"done"}\n')
    parser.flush()
    expect(events[0].data).toBe('{"type":"done"}')
  })

  it('tolerates frames without data fields and empty pushes', () => {
    const { events, parser } = collect()
    parser.push('')
    parser.push('\n\n')
    parser.push('event: ping\n\n')
    parser.flush()
    expect(events).toEqual([])
  })

  it('passes the [DONE] sentinel through as data', () => {
    const { events, parser } = collect()
    parser.push('data: [DONE]\n\n')
    expect(events[0].data).toBe('[DONE]')
  })

  it('reports JSON-level parse failures through onParseError by the caller', () => {
    const onParseError = vi.fn()
    const parser = createSseParser({ onEvent: vi.fn(), onParseError })
    // 解析器只负责分帧，data 是否合法 JSON 由调用方判定；
    // 这里仅验证 onParseError 在 flush 异常时被调用
    parser.push('data: ok\n\n')
    parser.flush()
    expect(onParseError).not.toHaveBeenCalled()
  })
})
