import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { gzipSync } from 'node:zlib'
import { dirname, extname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const PERFORMANCE_BUDGETS = Object.freeze({
  initialJavaScriptGzip: 450 * 1024,
  initialCssGzip: 100 * 1024,
  largestImage: 200 * 1024,
  routeChunkGzip: 150 * 1024
})

const IMAGE_EXTENSIONS = new Set(['.avif', '.gif', '.jpeg', '.jpg', '.png', '.svg', '.webp'])

function collectStaticImports(manifest, key, collected = new Set()) {
  if (!key || collected.has(key)) return collected
  const chunk = manifest[key]
  if (!chunk) return collected
  collected.add(key)
  for (const importedKey of chunk.imports || []) collectStaticImports(manifest, importedKey, collected)
  return collected
}

function unique(values) {
  return [...new Set(values.filter(Boolean))]
}

export function analyzeManifest(manifest, getAssetSize) {
  const entries = Object.entries(manifest)
  const entryKeys = entries.filter(([, chunk]) => chunk.isEntry).map(([key]) => key)
  if (entryKeys.length === 0) throw new Error('构建 manifest 中没有入口 chunk')

  const initialChunkKeys = new Set()
  for (const key of entryKeys) collectStaticImports(manifest, key, initialChunkKeys)
  const initialChunks = [...initialChunkKeys].map(key => manifest[key])
  const initialJavaScript = unique(initialChunks.map(chunk => chunk.file).filter(file => extname(file) === '.js'))
  const initialCss = unique(initialChunks.flatMap(chunk => chunk.css || []))
  const currentAssets = unique(entries.flatMap(([, chunk]) => [chunk.file, ...(chunk.css || []), ...(chunk.assets || [])]))
  const imageAssets = currentAssets.filter(file => IMAGE_EXTENSIONS.has(extname(file).toLowerCase()))
  const routeChunkKeys = unique(entryKeys.flatMap(key => manifest[key].dynamicImports || []))
  const routeChunks = routeChunkKeys
    .map(source => ({ source, chunk: manifest[source] }))
    .filter(({ chunk }) => chunk && extname(chunk.file) === '.js')
    .map(({ source, chunk }) => ({ source, file: chunk.file, ...getAssetSize(chunk.file) }))

  const sum = (files, field) => files.reduce((total, file) => total + getAssetSize(file)[field], 0)
  const largestImage = imageAssets
    .map(file => ({ file, ...getAssetSize(file) }))
    .sort((left, right) => right.raw - left.raw)[0] || { file: null, raw: 0, gzip: 0 }
  const largestRouteChunk = routeChunks
    .sort((left, right) => right.gzip - left.gzip)[0] || { source: null, file: null, raw: 0, gzip: 0 }

  return {
    initialJavaScript: { files: initialJavaScript, gzip: sum(initialJavaScript, 'gzip') },
    initialCss: { files: initialCss, gzip: sum(initialCss, 'gzip') },
    largestImage,
    largestRouteChunk
  }
}

export function evaluateBudgets(metrics, budgets = PERFORMANCE_BUDGETS) {
  const checks = [
    { metric: 'initialJavaScriptGzip', actual: metrics.initialJavaScript.gzip, limit: budgets.initialJavaScriptGzip, assets: metrics.initialJavaScript.files },
    { metric: 'initialCssGzip', actual: metrics.initialCss.gzip, limit: budgets.initialCssGzip, assets: metrics.initialCss.files },
    { metric: 'largestImage', actual: metrics.largestImage.raw, limit: budgets.largestImage, assets: [metrics.largestImage.file].filter(Boolean) },
    { metric: 'routeChunkGzip', actual: metrics.largestRouteChunk.gzip, limit: budgets.routeChunkGzip, assets: [metrics.largestRouteChunk.file].filter(Boolean) }
  ]
  return checks.map(check => ({ ...check, passed: check.actual <= check.limit }))
}

function formatKiB(bytes) {
  return `${(bytes / 1024).toFixed(1)} KiB`
}

function collectPublicImages(directory, root = directory) {
  if (!existsSync(directory)) return []
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return collectPublicImages(path, root)
    if (!IMAGE_EXTENSIONS.has(extname(entry.name).toLowerCase())) return []
    return [{ file: `public/${path.slice(root.length + 1)}`, raw: statSync(path).size, gzip: 0 }]
  })
}

function run() {
  const scriptDirectory = dirname(fileURLToPath(import.meta.url))
  const outputDirectory = resolve(scriptDirectory, '../../dist')
  const manifestPath = join(outputDirectory, '.vite/manifest.json')
  if (!existsSync(manifestPath)) throw new Error(`缺少构建 manifest: ${manifestPath}`)

  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  const getAssetSize = file => {
    const assetPath = join(outputDirectory, file)
    const content = readFileSync(assetPath)
    return { raw: statSync(assetPath).size, gzip: gzipSync(content).length }
  }
  const metrics = analyzeManifest(manifest, getAssetSize)
  const publicImages = collectPublicImages(resolve(scriptDirectory, '../public'))
  metrics.largestImage = [metrics.largestImage, ...publicImages]
    .sort((left, right) => right.raw - left.raw)[0]
  const checks = evaluateBudgets(metrics)

  for (const check of checks) {
    const status = check.passed ? 'PASS' : 'FAIL'
    const affectedAssets = check.assets.length ? ` [${check.assets.join(', ')}]` : ''
    console.log(`${status} ${check.metric}: ${formatKiB(check.actual)} / ${formatKiB(check.limit)}${affectedAssets}`)
  }

  if (checks.some(check => !check.passed)) process.exitCode = 1
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    run()
  } catch (error) {
    console.error(`性能预算检查失败: ${error.message}`)
    process.exitCode = 1
  }
}
