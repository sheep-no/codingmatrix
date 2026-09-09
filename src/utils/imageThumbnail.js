export async function createImageThumbnail(file, maxDimension = 320) {
  if (!(file instanceof Blob) || typeof createImageBitmap !== 'function') return ''

  const bitmap = await createImageBitmap(file)
  try {
    const scale = Math.min(1, maxDimension / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(bitmap.width * scale))
    canvas.height = Math.max(1, Math.round(bitmap.height * scale))
    const context = canvas.getContext('2d')
    if (!context) return ''
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/webp', 0.78)
  } finally {
    bitmap.close?.()
  }
}
