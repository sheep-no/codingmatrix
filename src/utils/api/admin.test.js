import { describe, expect, it, vi } from 'vitest'
import { createAdminClient } from './admin'

function response(body, ok = true, status = 200) {
  return {
    ok,
    status,
    json: vi.fn().mockResolvedValue(body)
  }
}

describe('admin API contract', () => {
  it('uses the final Guardian prefix and returns parsed service data', async () => {
    const client = {
      get: vi.fn().mockResolvedValue(response({ learned: 1, enabled: 1, services: [] }))
    }
    const adminApi = createAdminClient(client)

    await expect(adminApi.getServices()).resolves.toEqual({
      learned: 1,
      enabled: 1,
      services: []
    })
    expect(client.get).toHaveBeenCalledWith('/api/v2/Controller/services')
  })

  it('sends Guardian query parameters for rename and fuse updates', async () => {
    const client = {
      put: vi.fn().mockResolvedValue(response({ status: 'success' }))
    }
    const adminApi = createAdminClient(client)

    await adminApi.renameService(8080, 'python app.py', '后台')
    await adminApi.updateFuseConfig(8080, 'python app.py', {
      fuse_enabled: true,
      fuse_cooldown: 300,
      fuse_retry_times: 2
    })

    expect(client.put).toHaveBeenNthCalledWith(
      1,
      '/api/v2/Controller/service/8080/rename?process_signature=python+app.py&new_name=%E5%90%8E%E5%8F%B0'
    )
    expect(client.put).toHaveBeenNthCalledWith(
      2,
      '/api/v2/Controller/service/8080/fuse-config?process_signature=python+app.py&fuse_enabled=true&fuse_cooldown=300&fuse_retry_times=2'
    )
  })

  it('rejects failed role-limit saves instead of reporting success', async () => {
    const client = {
      post: vi.fn().mockResolvedValue(response({ detail: 'forbidden' }, false, 403))
    }
    const adminApi = createAdminClient(client)

    await expect(adminApi.saveRoleLimits({ free: 1 })).rejects.toThrow('Save role limit failed (403)')
    expect(client.post).toHaveBeenCalledWith('/api/v2/admin/config', {
      path: 'system_config.user_concurrent_limits.default_tiers.free',
      value: 1
    })
  })

  it('matches query and JSON response contracts for Guardian controls', async () => {
    const backup = { version: '1.0', configs: {} }
    const client = {
      get: vi.fn().mockResolvedValue(response(backup)),
      put: vi.fn().mockResolvedValue(response({ status: 'success' }))
    }
    const adminApi = createAdminClient(client)

    await expect(adminApi.downloadBackup('20260902_120000')).resolves.toEqual(backup)
    await adminApi.updateGlobalLogLevel('INFO')
    await adminApi.toggleRateLimit(true)

    expect(client.get).toHaveBeenCalledWith('/api/v2/Controller/admin/backup/20260902_120000')
    expect(client.put).toHaveBeenNthCalledWith(
      1,
      '/api/v2/Controller/admin/log-config/global-level?level=INFO'
    )
    expect(client.put).toHaveBeenNthCalledWith(
      2,
      '/api/v2/Controller/admin/rate-limit/enabled?enabled=true'
    )
  })
})
