import { afterEach, describe, expect, it, vi } from 'vitest'
import { createImageThumbnail } from './imageThumbnail'

describe('createImageThumbnail', () => {
  const originalCreateImageBitmap = globalThis.createImageBitmap

  afterEach(() => {
    globalThis.createImageBitmap = originalCreateImageBitmap
    vi.restoreAllMocks()
  })

  it('scales large images to the configured bounding box', async () => {
    const close = vi.fn()
    globalThis.createImageBitmap = vi.fn().mockResolvedValue({ width: 1600, height: 800, close })
    const drawImage = vi.fn()
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage })
    vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/webp;base64,thumb')

    const thumbnail = await createImageThumbnail(new Blob(['image']), 320)

    expect(thumbnail).toBe('data:image/webp;base64,thumb')
    expect(drawImage).toHaveBeenCalledWith(expect.anything(), 0, 0, 320, 160)
    expect(close).toHaveBeenCalledOnce()
  })

  it('returns an empty value when bitmap decoding is unavailable', async () => {
    globalThis.createImageBitmap = undefined
    await expect(createImageThumbnail(new Blob(['image']))).resolves.toBe('')
  })
})
