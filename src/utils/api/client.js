export function createClient(config = {}) {
  const { baseURL = '/api/v1', token = null } = config
  return { get: async () => ({}), post: async () => ({}), put: async () => ({}), delete: async () => ({}) }
}
