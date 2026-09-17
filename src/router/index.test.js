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

  it('allows superadmin into the superadmin-only dashboard', () => {
    expect(resolveRouteAccess(
      { fullPath: '/admin/dashboard', meta: { requiresAuth: true, requiresSuper: true, requiresSuperAdmin: true } },
      'token',
      'superadmin'
    )).toBe(true)
  })

  it('sends admins from the superadmin-only dashboard back to the admin panel', () => {
    expect(resolveRouteAccess(
      { fullPath: '/admin/dashboard', meta: { requiresAuth: true, requiresSuper: true, requiresSuperAdmin: true } },
      'token',
      'admin'
    )).toEqual({ name: 'admin' })
  })

  it('sends normal users from the superadmin-only dashboard home', () => {
    expect(resolveRouteAccess(
      { fullPath: '/admin/dashboard', meta: { requiresAuth: true, requiresSuper: true, requiresSuperAdmin: true } },
      'token',
      'normal'
    )).toEqual({ name: 'home' })
  })
})
