import { createBaseClient } from './base'

export function createClient(config = {}) {
  const client = createBaseClient()

  // admin.js 需要 patch 方法，base.js 未提供
  if (!client.patch) {
    client.patch = async (url, data) => {
      return client.request(url, {
        method: 'PATCH',
        body: JSON.stringify(data)
      })
    }
  }

  return client
}
