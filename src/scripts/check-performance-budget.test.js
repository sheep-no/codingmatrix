import { describe, expect, it } from 'vitest'
import { analyzeManifest, evaluateBudgets } from './check-performance-budget.js'

const manifest = {
  'index.html': {
    file: 'static/index.js',
    isEntry: true,
    imports: ['_vendor.js'],
    dynamicImports: ['views/Workflow.vue'],
    css: ['static/index.css']
  },
  '_vendor.js': { file: 'static/vendor.js', css: ['static/vendor.css'] },
  'views/Workflow.vue': {
    file: 'static/workflow.js',
    isDynamicEntry: true,
    assets: ['static/workflow.png']
  }
}

const sizes = {
  'static/index.js': { raw: 300, gzip: 100 },
  'static/vendor.js': { raw: 600, gzip: 200 },
  'static/index.css': { raw: 120, gzip: 40 },
  'static/vendor.css': { raw: 180, gzip: 60 },
  'static/workflow.js': { raw: 450, gzip: 150 },
  'static/workflow.png': { raw: 900, gzip: 850 }
}

describe('performance budget checks', () => {
  it('calculates initial assets and largest route and image resources', () => {
    const metrics = analyzeManifest(manifest, file => sizes[file])

    expect(metrics.initialJavaScript).toEqual({
      files: ['static/index.js', 'static/vendor.js'],
      gzip: 300
    })
    expect(metrics.initialCss).toEqual({
      files: ['static/index.css', 'static/vendor.css'],
      gzip: 100
    })
    expect(metrics.largestImage.file).toBe('static/workflow.png')
    expect(metrics.largestRouteChunk.file).toBe('static/workflow.js')
  })

  it('reports every exceeded metric and affected asset', () => {
    const metrics = analyzeManifest(manifest, file => sizes[file])
    const checks = evaluateBudgets(metrics, {
      initialJavaScriptGzip: 299,
      initialCssGzip: 99,
      largestImage: 899,
      routeChunkGzip: 149
    })

    expect(checks.every(check => !check.passed)).toBe(true)
    expect(checks.map(check => check.metric)).toEqual([
      'initialJavaScriptGzip',
      'initialCssGzip',
      'largestImage',
      'routeChunkGzip'
    ])
    expect(checks[3].assets).toEqual(['static/workflow.js'])
  })

  it('fails clearly when the manifest has no application entry', () => {
    expect(() => analyzeManifest({}, () => ({ raw: 0, gzip: 0 }))).toThrow('没有入口 chunk')
  })
})
