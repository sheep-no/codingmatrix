import { nextTick, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { useApiKeyStore } from '@/stores/apikey'

export function useAgentStreaming(projectApi, workspace, files, generation, session) {
  const {
    logs, executionDetails, thinkingMessages, pendingDecisions,
    decisionAnswers, decisionHistory, currentAgent, currentModel,
    currentProjectPath, addLog, addDetail
  } = workspace

  const {
    generatedFiles, fileDiffs, selectedFile
  } = files

  // generation 是 reactive() 对象，不能解构基本类型，需通过 generation.xxx 访问
  const { ensureStage, updateStageStatus, addThinkingToStage } = generation

  // 获取 API Key Store
  const apiKeyStore = useApiKeyStore()

  const phaseNames = {
    'context_init': '上下文初始化', 'specs': '规格书生成',
    'architecture': '架构设计', 'dependency_graph': '依赖图构建',
    'code_generation': '代码生成', 'validation': '验证审查'
  }

  const handleSseMessage = (data) => {
    const innerData = data.data || data
    if (innerData.phase) {
      const stageId = innerData.phase
      const stageName = phaseNames[innerData.phase] || innerData.phase
      const progress = innerData.percentage || 0
      ensureStage(stageId, stageName)
      if (data.type === 'progress' && progress > 0 && progress < 100) {
        updateStageStatus(stageId, 'running', progress)
      } else if (data.type === 'done' || progress === 100) {
        updateStageStatus(stageId, 'completed', 100)
      } else if (data.type === 'error') {
        updateStageStatus(stageId, 'failed', progress)
      }
    }

    switch (data.type) {
      case 'file':
        generatedFiles.value.push({ path: data.path, content: data.content })
        addLog('info', `生成文件: ${data.path}`)
        if (data.file_type) addDetail('文件生成', `${data.path} (${data.file_type})`)
        break
      case 'file_diff':
        fileDiffs.value.push({
          path: data.path,
          oldContent: data.old_content || '',
          newContent: data.new_content || data.content || '',
          operation: data.operation || 'create'
        })
        addLog('info', `文件变更: ${data.path} (${data.operation})`)
        break
      case 'thinking': {
        const agent = data.agent || 'AI Agent'
        const msg = data.message || data.content
        const ts = data.timestamp || Date.now()
        thinkingMessages.value.push({ agent, message: msg, timestamp: ts, model: data.model || currentModel.value, phase: data.phase || '' })
        addLog('thinking', `[${agent}] ${msg}`)
        if (data.phase) {
          addThinkingToStage(data.phase, { agent, message: msg, timestamp: ts, model: data.model || currentModel.value })
        }
        break
      }
      case 'model_info':
        currentAgent.value = data.agent
        currentModel.value = data.model
        addLog('info', `使用模型: ${data.model} (${data.agent})`)
        addDetail('模型分配', `${data.agent} → ${data.model}`)
        const assignmentKey = data.agent?.toLowerCase()
        if (generation.modelAssignments[assignmentKey]) {
          generation.modelAssignments[assignmentKey].model = data.model
          generation.modelAssignments[assignmentKey].calls++
        }
        break
      case 'progress': {
        const progressData = data.data || data
        if (progressData.step) {
          addLog('progress', `${progressData.phase ? progressData.phase + ': ' : ''}${progressData.step} (${progressData.percentage}%)`)
          addDetail('进度更新', `${progressData.current}/${progressData.total} (${progressData.percentage}%)`)
          generation.currentStep = progressData.current
          generation.totalSteps = progressData.total
        }
        break
      }
      case 'step_detail':
        if (data.description) addDetail(data.category || '执行步骤', data.description)
        break
      case 'critical_decisions':
        pendingDecisions.value = data.data?.decisions || []
        decisionAnswers.value = {}
        addLog('warning', '需要您确认架构决策')
        break
      case 'error':
        addLog('error', data.data?.error || data.message || '未知错误')
        break
      case 'warning':
        addLog('warning', data.message || data.content || '警告')
        break
      case 'done':
        addLog('success', '项目生成完成')
        generation.workflowStages.forEach(stage => {
          if (stage.status !== 'failed') updateStageStatus(stage.id, 'completed', 100)
        })
        if (session.currentSessionId.value) {
          currentProjectPath.value = `projects/${session.currentSessionId.value}`
        }
        break
      default:
        console.log('未知SSE消息类型:', data.type, data)
    }
  }

  const processSseResponse = async (response) => {
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const text = decoder.decode(value)
      const lines = text.split('\n').filter(line => line.trim())
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            handleSseMessage(data)
          } catch (e) {
            console.error('Failed to parse SSE:', e)
          }
        }
      }
    }
  }

  const buildStreamParams = (requirement, sessionId, mode, selectedProviderModel) => {
    // 获取用户 SiliconFlow API Key token
    const siliconflowKey = apiKeyStore.siliconflowKey
    
    // 解析动态供应商选择 (格式: "provider_id::model_id")
    let providerId = undefined
    if (selectedProviderModel && selectedProviderModel.includes('::')) {
      providerId = selectedProviderModel.split('::')[0]
    }
    
    return {
      requirement,
      session_id: sessionId,
      enable_review: true,
      enable_validation: true,
      enable_error_recovery: true,
      enable_memory: true,
      spec_first: true,
      dependency_graph: true,
      incremental: mode !== 'create',
      require_approval: false,
      api_key_token: siliconflowKey ? siliconflowKey.token : undefined,
      provider_id: providerId,
      ...(mode && mode !== 'create' ? {
        project_path: currentProjectPath.value,
        ...(mode === 'debug' ? { mode: 'debug' } : {})
      } : {})
    }
  }

  const streamGenerate = async (mode, selectedProviderModel) => {
    // 检查是否有 SiliconFlow API Key 或动态供应商
    if (!apiKeyStore.hasSiliconflowKey && !selectedProviderModel) {
      ElMessage.warning('请先配置 SiliconFlow API Key 或选择自定义供应商模型')
      return
    }

    if (mode === 'create') {
      generatedFiles.value = []
      fileDiffs.value = []
    }
    logs.value = []
    generation.isGenerating = true
    addLog('info', mode === 'create' ? '开始生成项目...' : mode === 'modify' ? '开始增量更新...' : '开始调试修复...')

    try {
      const sessionId = session.currentSessionId || session.createNewSession({})
      const params = buildStreamParams(session.projectPrompt, sessionId, mode, selectedProviderModel)
      const response = await projectApi.generateProjectStream(params)
      await processSseResponse(response)
      generation.isGenerating = false
      addLog('success', mode === 'create' ? '项目生成完成' : mode === 'modify' ? '增量更新完成' : '调试修复完成')
      session.projectPrompt = ''
    } catch (error) {
      generation.isGenerating = false
      addLog('error', `${mode === 'create' ? '生成' : mode === 'modify' ? '增量更新' : '调试修复'}失败: ${error.message}`)
      ElMessage.error(mode === 'create' ? '项目生成失败' : mode === 'modify' ? '增量更新失败' : '调试修复失败')
    }
  }

  return reactive({
    handleSseMessage, processSseResponse, streamGenerate
  })
}
