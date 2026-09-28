import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessage } from 'element-plus'
import { useAgentWorkspace } from './useAgentWorkspace'
import { useAgentBackend } from './useAgentBackend'

const writeText = vi.fn()

function setClipboard(available = true) {
  Object.defineProperty(navigator, 'clipboard', {
    value: available ? { writeText } : undefined,
    configurable: true
  })
}

function makeWorkspace(fileContent = 'print(1)') {
  return useAgentWorkspace({
    session: {},
    files: { selectedFile: fileContent === null ? null : { content: fileContent } }
  })
}

function makeBackend() {
  return useAgentBackend(
    {},
    { addLog: vi.fn() },
    { generatedFiles: [], selectedFile: null },
    {}
  )
}

describe('Agent 剪贴板复制的异步错误处理', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    writeText.mockReset()
    setClipboard(true)
    vi.spyOn(ElMessage, 'success').mockImplementation(() => {})
    vi.spyOn(ElMessage, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('copyFileContent 成功后提示成功', async () => {
    writeText.mockResolvedValue()
    const workspace = makeWorkspace('print(1)')

    await workspace.copyFileContent()

    expect(writeText).toHaveBeenCalledWith('print(1)')
    expect(ElMessage.success).toHaveBeenCalledWith('已复制到剪贴板')
    expect(ElMessage.error).not.toHaveBeenCalled()
  })

  it('copyFileContent 剪贴板拒绝时提示失败且不误报成功', async () => {
    writeText.mockRejectedValue(new Error('NotAllowedError'))
    const workspace = makeWorkspace('print(1)')

    await expect(workspace.copyFileContent()).resolves.toBeUndefined()

    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(ElMessage.error).toHaveBeenCalledWith('复制失败，请手动选择内容复制')
  })

  it('copyFileContent 剪贴板不可用时不抛出，转为失败提示', async () => {
    setClipboard(false)
    const workspace = makeWorkspace('print(1)')

    await expect(workspace.copyFileContent()).resolves.toBeUndefined()

    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(ElMessage.error).toHaveBeenCalledWith('复制失败，请手动选择内容复制')
  })

  it('copySettingsToClipboard 成功后提示成功', async () => {
    writeText.mockResolvedValue()
    const backend = makeBackend()

    await backend.copySettingsToClipboard()

    expect(writeText).toHaveBeenCalledTimes(1)
    expect(ElMessage.success).toHaveBeenCalledWith('配置已复制到剪贴板')
    expect(ElMessage.error).not.toHaveBeenCalled()
  })

  it('copySettingsToClipboard 拒绝时提示失败，不再出现假成功', async () => {
    writeText.mockRejectedValue(new Error('NotAllowedError'))
    const backend = makeBackend()

    await expect(backend.copySettingsToClipboard()).resolves.toBeUndefined()

    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(ElMessage.error).toHaveBeenCalledWith('复制失败，请检查浏览器剪贴板权限')
  })
})
