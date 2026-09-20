// @vitest-environment node
import { describe, expect, it } from 'vitest'

import { createAiCloudClient } from './aicloud'

describe('AiCloud 客户端契约', () => {
  it('审查操作与后端端点一一对应', () => {
    const client = createAiCloudClient({})

    // GET /reviews、POST /reviews/approve、POST /reviews/reject 是后端已挂载的端点。
    expect(typeof client.getReviews).toBe('function')
    expect(typeof client.approveReview).toBe('function')
    expect(typeof client.rejectReview).toBe('function')
    // 后端未定义 /aicloud/reviews/toggle，客户端不应暴露对应方法。
    expect(client.toggleReview).toBeUndefined()
  })
})
