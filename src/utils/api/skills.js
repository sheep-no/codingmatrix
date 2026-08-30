export function createSkillsClient(client) {
  return {
    async listSkills() {
      const response = await client.get('/skills/list')
      return response.ok ? await response.json() : []
    },

    async listAgentHostSessions() {
      const response = await client.get('/agent/host/sessions')
      return response.ok ? await response.json() : []
    }
  }
}
