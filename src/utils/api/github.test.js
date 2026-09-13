import { describe, expect, it } from 'vitest'
import { toGithubRepoName } from './github'

describe('toGithubRepoName', () => {
  it('keeps a valid GitHub repo name', () => {
    expect(toGithubRepoName('demo-app')).toBe('demo-app')
  })

  it('strips non-ascii characters and edge punctuation', () => {
    expect(toGithubRepoName('项目_2026')).toBe('2026')
    expect(toGithubRepoName('...')).toBe('project')
  })

  it('truncates names longer than 100 characters', () => {
    expect(toGithubRepoName('a'.repeat(120))).toBe('a'.repeat(100))
  })
})
