import { reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { useApiKeyStore } from '@/stores/apikey'

export function useAgentStreaming(projectApi, workspace, files, generation, session) {
  // 注意：workspace 和 files 是 reactive() 对象，ref 属性会被自动解包
  // 不能解构后使用 .value，必须通过对象访问（如 workspace.currentAgent）
  const { addLog, addDetail } = workspace
  const { ensureStage, updateStageStatus, addThinkingToStage } = generation

  // 获取 API Key Store
  const apiKeyStore = useApiKeyStore()

  const phaseNames = {
    'context_init': '上下文初始化', 'specs': '规格书生成',
    'architecture': '架构设计', 'dependency_graph': '依赖图构建',
    'code_generation': '代码生成', 'validation': '验证审查',
    'testing': '测试执行', 'cross_file': '跨文件检查',
    'cost_tracking': '成本追踪'
  }

  const handleSseMessage = (data) => {
    console.log('[SSE] 收到消息:', data.type, data.data?.phase || '')
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
        files.generatedFiles.push({
          path: data.path,
          content: data.content,
          fileSize: data.file_size,
          fileSizeHuman: data.file_size_human,
          complexity: data.complexity,
          lineCount: data.line_count
        })
        addLog('info', `生成文件: ${data.path} (${data.file_size_human || ''}, ${data.line_count || 0} 行)`)
        if (data.file_type) addDetail('文件生成', `${data.path} (${data.file_type}, 复杂度: ${data.complexity?.level || '未知'})`)
        break
      case 'file_diff': {
        files.fileDiffs.push({
          path: data.path,
          oldContent: data.old_content || '',
          newContent: data.new_content || data.content || '',
          operation: data.operation || 'create',
          changes: data.changes,
          sizeDelta: data.size_delta
        })
        const changeSummary = data.changes ? `+${data.changes.added}/-${data.changes.removed}` : ''
        addLog('info', `文件变更: ${data.path} (${data.operation}) ${changeSummary}`)
        break
      }
      case 'thinking': {
        const agent = data.agent || 'AI Agent'
        const msg = data.message || data.content
        const ts = data.timestamp || Date.now()
        workspace.thinkingMessages.push({
          agent,
          message: msg,
          timestamp: ts,
          model: data.model || workspace.currentModel,
          phase: data.phase || '',
          reasoningSteps: data.reasoning_steps || [],
          confidence: data.confidence || null
        })
        addLog('thinking', `[${agent}] ${msg}`)
        if (data.phase) {
          addThinkingToStage(data.phase, { agent, message: msg, timestamp: ts, model: data.model || workspace.currentModel })
        }
        break
      }
      case 'model_info': {
        workspace.currentAgent = data.agent
        workspace.currentModel = data.model
        addLog('info', `使用模型: ${data.model} (${data.agent})`)
        addDetail('模型分配', `${data.agent} → ${data.model}`)
        const assignmentKey = data.agent?.toLowerCase()
        if (generation.modelAssignments[assignmentKey]) {
          generation.modelAssignments[assignmentKey].model = data.model
          generation.modelAssignments[assignmentKey].calls++
        }
        break
      }
      case 'progress': {
        const progressData = data.data || data
        if (progressData.step) {
          addLog('progress', `${progressData.phase ? progressData.phase + ': ' : ''}${progressData.step} (${progressData.percentage}%)`)
          addDetail('进度更新', `${progressData.current}/${progressData.total} (${progressData.percentage}%)`)
          generation.currentStep = progressData.current
          generation.totalSteps = progressData.total
          // 更新当前文件名（如果有）
          if (progressData.current_file) {
            generation.currentFile = progressData.current_file
          }
          // 更新当前模型（如果有）
          if (progressData.current_model) {
            workspace.currentModel = progressData.current_model
          }
        }
        break
      }
      case 'step_detail':
        if (data.description) addDetail(data.category || '执行步骤', data.description)
        break
      case 'test_results': {
        const testSummary = data.summary || {}
        const passed = testSummary.passed || 0
        const failed = testSummary.failed || 0
        const total = passed + failed
        addLog(failed > 0 ? 'warning' : 'success', `测试结果: ${passed}/${total} 通过`)
        addDetail('测试结果', `通过: ${passed}, 失败: ${failed}, 跳过: ${testSummary.skipped || 0}`)
        // 保存测试结果到 workspace
        workspace.testResults = {
          passed,
          failed,
          skipped: testSummary.skipped || 0,
          coverage: testSummary.coverage || null,
          duration: data.duration || 0
        }
        break
      }
      case 'validation_results': {
        const issues = data.issues || []
        const passed = data.passed || false
        addLog(passed ? 'success' : 'warning', `验证${passed ? '通过' : '失败'}: ${issues.length} 个问题`)
        if (data.checks) {
          data.checks.forEach(check => {
            addDetail(check.passed ? '验证通过' : '验证失败', check.name + (check.message ? `: ${check.message}` : ''))
          })
        }
        workspace.validationResults = {
          passed,
          issues,
          checks: data.checks || []
        }
        break
      }
      case 'cost_update':
        workspace.costData = {
          totalTokens: data.total_tokens || 0,
          promptTokens: data.prompt_tokens || 0,
          completionTokens: data.completion_tokens || 0,
          totalCostUsd: data.total_cost_usd || 0,
          tokensPerSecond: data.tokens_per_second || 0,
          modelCosts: data.model_costs || {},
          modelTokens: data.model_tokens || {}
        }
        addLog('info', `Token 用量: ${data.total_tokens || 0} (费用: $${(data.total_cost_usd || 0).toFixed(4)})`)
        break
      case 'performance_metrics':
        workspace.performanceMetrics = {
          generationSpeed: data.generation_speed || 0,
          filesPerMinute: data.files_per_minute || 0,
          avgFileTime: data.avg_file_time || 0,
          totalDuration: data.total_duration || 0,
          llmCalls: data.llm_calls || 0,
          retryCount: data.retry_count || 0
        }
        addDetail('性能指标', `生成速度: ${data.files_per_minute?.toFixed(1) || 0} 文件/分钟, LLM 调用: ${data.llm_calls || 0}`)
        break
      case 'critical_decisions':
        workspace.pendingDecisions = data.data?.decisions || []
        workspace.decisionAnswers = {}
        addLog('warning', '需要您确认架构决策')
        break
      case 'error':
        addLog('error', data.data?.error || data.message || '未知错误')
        break
      case 'warning':
        addLog('warning', data.message || data.content || '警告')
        if (data.code) {
          addDetail('警告详情', `[${data.code}] ${data.message}`)
        }
        break
      case 'done':
        console.log('[SSE] 收到 done 事件，设置 isGenerating=false')
        addLog('success', '项目生成完成')
        generation.isGenerating = false
        generation.workflowStages.forEach(stage => {
          if (stage.status !== 'failed') updateStageStatus(stage.id, 'completed', 100)
        })
        if (session.currentSessionId) {
          const doneData = data.data || data
          const dirName = doneData.output_dir || session.currentSessionId
          workspace.currentProjectPath = `orchestrator/${dirName}`
        }
        if (data.data?.performance) {
          workspace.performanceMetrics = data.data.performance
        }
        if (data.data?.cost) {
          workspace.costData = data.data.cost
        }
        break
      default:
        console.log('未知SSE消息类型:', data.type, data)
    }
  }

  const processSseResponse = async (response) => {
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    console.log('[SSE] processSseResponse 开始读取流')
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        console.log('[SSE] 流已结束，reader.done=true')
        break
      }
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

  const buildStreamParams = (requirement, sessionId, selectedProviderModel) => {
    // 获取用户 SiliconFlow API Key token
    const siliconflowKey = apiKeyStore.siliconflowKey
    
    // 解析动态供应商选择 (格式: "provider_id::model_id")
    let providerId = undefined
    if (selectedProviderModel && selectedProviderModel.includes('::')) {
      providerId = selectedProviderModel.split('::')[0]
    }
    
    // 自动判断模式：有已生成文件则为增量更新，否则为新建
    const hasExistingFiles = files.generatedFiles.length > 0
    const isIncremental = hasExistingFiles && workspace.currentProjectPath
    
    return {
      requirement,
      session_id: sessionId,
      enable_review: true,
      enable_validation: true,
      enable_error_recovery: true,
      enable_memory: true,
      spec_first: true,
      dependency_graph: true,
      incremental: isIncremental,
      require_approval: false,
      api_key_token: siliconflowKey ? siliconflowKey.token : undefined,
      provider_id: providerId,
      ...(isIncremental ? {
        project_path: workspace.currentProjectPath
      } : {})
    }
  }

  const streamGenerate = async (selectedProviderModel) => {
    // 检查是否有 SiliconFlow API Key 或动态供应商
    if (!apiKeyStore.hasSiliconflowKey && !selectedProviderModel) {
      ElMessage.warning('请先配置 SiliconFlow API Key 或选择自定义供应商模型')
      return
    }

    // 自动判断模式
    const hasExistingFiles = files.generatedFiles.length > 0
    const isIncremental = hasExistingFiles && workspace.currentProjectPath
    const mode = isIncremental ? '增量更新' : '新建项目'
    
    if (!isIncremental) {
      files.generatedFiles = []
      files.fileDiffs = []
    }
    workspace.logs = []
    generation.isGenerating = true
    addLog('info', `开始${mode}...`)

    try {
      const sessionId = session.currentSessionId || session.createNewSession({})
      const params = buildStreamParams(session.projectPrompt, sessionId, selectedProviderModel)
      const response = await projectApi.generateProjectStream(params)
      console.log('[SSE] generateProjectStream 返回, response.ok:', response.ok, 'status:', response.status)
      await processSseResponse(response)
      generation.isGenerating = false
      addLog('success', `${mode}完成`)
      session.projectPrompt = ''
    } catch (error) {
      generation.isGenerating = false
      addLog('error', `${mode}失败: ${error.message}`)
      ElMessage.error(`${mode}失败`)
    }
  }

  return reactive({
    handleSseMessage, processSseResponse, streamGenerate
  })
}
