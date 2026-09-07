export const DEFAULT_MESSAGE_HEIGHT = 200
export const MESSAGE_GAP = 24

export function getMessageKey(message, index) {
  return message?.id ?? `message-${index}`
}

function getMessageExtent(message, index, measuredHeights) {
  const measuredHeight = measuredHeights.get(getMessageKey(message, index))
  return (measuredHeight || DEFAULT_MESSAGE_HEIGHT) + MESSAGE_GAP
}

export function getMessageOffset(messages, endIndex, measuredHeights) {
  let offset = 0
  for (let index = 0; index < endIndex; index++) {
    offset += getMessageExtent(messages[index], index, measuredHeights)
  }
  return offset
}

export function getTotalMessageHeight(messages, measuredHeights) {
  return getMessageOffset(messages, messages.length, measuredHeights)
}

export function calculateVisibleRange({
  messages,
  measuredHeights,
  scrollTop,
  viewportHeight,
  buffer
}) {
  let start = 0
  let offset = 0

  while (start < messages.length) {
    const extent = getMessageExtent(messages[start], start, measuredHeights)
    if (offset + extent > scrollTop) break
    offset += extent
    start++
  }

  let end = start
  let visibleHeight = offset
  const viewportEnd = scrollTop + viewportHeight
  while (end < messages.length && visibleHeight < viewportEnd) {
    visibleHeight += getMessageExtent(messages[end], end, measuredHeights)
    end++
  }

  return {
    start: Math.max(0, start - buffer),
    end: Math.min(messages.length, end + buffer)
  }
}
