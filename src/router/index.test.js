import { describe, expect, it } from 'vitest'
import { resolveRouteAccess } from './index'

describe('resolveRouteAccess', () => {
  it('redirects anonymous users and keeps the requested destination', () => {
    expect(resolveRouteAccess(
      { fullPath: '/agent?tab=files', meta: { requiresAuth: true } },
      null,
      null
    )).toEqual({ name: 'home', query: { redirect: '/agent?tab=files' } })
  })

  it('allows authenticated users with the required permission', () => {
    expect(resolveRouteAccess(
      { fullPath: '/admin', meta: { requiresAuth: true, requiresSuper: true } },
      'token',
      'admin'
    )).toBe(true)
  })
})
