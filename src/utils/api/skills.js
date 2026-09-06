export function createSkillsClient(client) {
  return {
    async listSkills() {
      const response = await client.get('/skills/list')
      return response.ok ? await response.json() : []
    },

    async getSkill(name) {
      const response = await client.get(`/skills/${encodeURIComponent(name)}`)
      if (!response.ok) throw new Error(`获取 Skill 失败 (${response.status})`)
      return response.json()
    },

    async listSkillCategories() {
      const response = await client.get('/skills/categories')
      if (!response.ok) throw new Error(`获取 Skill 分类失败 (${response.status})`)
      return response.json()
    },

    async uploadSkill(data) {
      const response = await client.post('/skills/upload', data)
      if (!response.ok) throw new Error(`上传 Skill 失败 (${response.status})`)
      return response.json()
    },

    async updateSkill(name, data) {
      const response = await client.put(`/skills/${encodeURIComponent(name)}`, data)
      if (!response.ok) throw new Error(`更新 Skill 失败 (${response.status})`)
      return response.json()
    },

    async deleteSkill(name) {
      const response = await client.delete(`/skills/${encodeURIComponent(name)}`)
      if (!response.ok) throw new Error(`删除 Skill 失败 (${response.status})`)
      return response.json()
    },

    async listAgentHostSessions() {
      const response = await client.get('/agent/host/sessions')
      return response.ok ? await response.json() : []
    },

    async getAgentHostActions(sessionId) {
      const response = await client.get(`/agent/host/sessions/${encodeURIComponent(sessionId)}/actions`)
      if (!response.ok) throw new Error(`获取 Agent Host 动作失败 (${response.status})`)
      return response.json()
    },

    async updateAgentHostPolicy(sessionId, expectedPolicyVersion, policy) {
      const response = await client.put(`/agent/host/sessions/${encodeURIComponent(sessionId)}/policy`, {
        expected_policy_version: expectedPolicyVersion,
        policy
      })
      if (!response.ok) throw new Error(`更新 Agent Host 策略失败 (${response.status})`)
      return response.json()
    },

    async controlAgentHostSession(sessionId, action) {
      const response = await client.post(`/agent/host/sessions/${encodeURIComponent(sessionId)}/control`, { action })
      if (!response.ok) throw new Error(`控制 Agent Host 会话失败 (${response.status})`)
      return response.json()
    }
  }
}
