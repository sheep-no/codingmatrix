import { reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useApiKeyStore } from '@/stores/apikey'
import { getPhaseLabel } from '@/constants/agentPhases'
import { createStreamUpdateBatcher } from '@/utils/streamUpdateBatcher'

const AGENT_ROLE_ALIAS = {
  'architecture': 'architect',
  'arch': 'architect',
  'frontend engineer': 'frontend',
  'frontend_engineer': 'frontend',
  'backend engineer': 'backend',
  'backend_engineer': 'backend',
  'review': 'reviewer',
  'code review': 'reviewer',
  'reviewer_model': 'reviewer',
  '架构师': 'architect',
  '前端工程师': 'frontend',
  '后端工程师': 'backend',
  '审查员': 'reviewer',
  '代码审查员': 'reviewer',
}

export function normalizeAgentRole(agent) {
  const rawAgent = (agent || '').toString().toLowerCase()
  return AGENT_ROLE_ALIAS[rawAgent] || rawAgent
}

export function normalizeEventTimestamp(ts) {
  if (ts == null || ts === '') return Date.now()
  const numeric = Number(ts)
  if (!Number.isFinite(numeric) || numeric <= 0) return Date.now()
  return numeric < 1e12 ? numeric * 1000 : numeric
}

export function markThinkingStreamEnded(messages, { agent, phase } = {}) {
  if (!Array.isArray(messages)) return messages
  for (const message of messages) {
    if (message.streaming !== true) continue
    if (agent && message.agent !== agent) continue
    if (phase != null && phase !== '' && (message.phase || '') !== phase) continue
    message.streaming = false
  }
  return messages
}

export function resolveIncrementalStreamOptions(hasExistingFiles, currentProjectPath) {
  const incremental = Boolean(hasExistingFiles && currentProjectPath)
  if (!incremental) return { incremental: false }
  return {
    incremental: true,
    engine: 'core',
    is_resume: false,
    project_path: currentProjectPath,
  }
}

export function useAgentStreaming(projectApi, workspace, files, generation, session, taskFeedback = null) {
  // 注意：workspace 和 files 是 reactive() 对象，ref 属性会被自动解包
  // 不能解构后使用 .value，必须通过对象访问（如 workspace.currentAgent）
  const { addLog, addDetail } = workspace
  const { ensureStage, updateStageStatus, addThinkingToStage } = generation

  // 获取 API Key Store
  const apiKeyStore = useApiKeyStore()
  let activeStreamSessionId = null

  const thinkingBatcher = createStreamUpdateBatcher(update => {
    const list = workspace.thinkingMessages
    let lastSame = null
    for (let index = list.length - 1; index >= 0; index--) {
      const message = list[index]
      if (
        message.agent === update.agent &&
        (message.phase || '') === update.phase &&
        message.streaming === true
      ) {
        lastSame = message
        break
      }
    }

    if (lastSame) {
      lastSame.message = (lastSame.message || '') + update.responseDelta
      if (update.accumulated) lastSame.accumulated = update.accumulated
      if (update.model) lastSame.model = update.model
    } else {
      list.push({
        agent: update.agent,
        message: update.responseDelta,
        timestamp: update.timestamp,
        model: update.model || workspace.currentModel,
        phase: update.phase,
        streaming: true,
        accumulated: update.accumulated || update.responseDelta
      })
    }

    addLog('thinking', `[${update.agent}] ${update.responseDelta}`)
    if (update.phase) {
      addThinkingToStage(update.phase, {
        agent: update.agent,
        message: update.responseDelta,
        timestamp: update.timestamp,
        model: update.model || workspace.currentModel
      })
    }
  })

  const handleSseMessage = (data) => {
    if (activeStreamSessionId && session.currentSessionId !== activeStreamSessionId) return
    taskFeedback?.update(data, {
      currentPhase: generation.currentPhase,
      progress: generation.getOverallProgress(),
      hasFailedStage: generation.workflowStages.some(stage => stage.status === 'failed'),
      hasGeneratedFiles: files.generatedFiles.length > 0
    })
    const innerData = data.data || data
    if (innerData.phase) {
      const stageId = innerData.phase
      const stageName = getPhaseLabel(innerData.phase)
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
        {
          const fileEntry = {
            path: data.path,
            content: data.content,
            fileSize: data.file_size,
            fileSizeHuman: data.file_size_human,
            complexity: data.complexity,
            lineCount: data.line_count,
            description: data.description || '',
            operation: data.operation || 'create',
            timestamp: normalizeEventTimestamp(data.timestamp)
          }
          const existingIndex = files.generatedFiles.findIndex(item => item.path === data.path)
          if (existingIndex >= 0) {
            files.generatedFiles.splice(existingIndex, 1, fileEntry)
          } else {
            files.generatedFiles.push(fileEntry)
          }
          addLog('info', `生成文件: ${data.path} (${data.file_size_human || ''}, ${data.line_count || 0} 行)`)
          if (data.file_type) addDetail('文件生成', `${data.path} (${data.file_type}, 复杂度: ${data.complexity?.level || '未知'})`)
        }
        break
      case 'file_diff': {
        files.fileDiffs.push({
          path: data.path,
          oldContent: data.old_content || '',
          newContent: data.new_content || data.content || '',
          operation: data.operation || 'create',
          changes: data.changes,
          sizeDelta: data.size_delta,
          timestamp: normalizeEventTimestamp(data.timestamp)
        })
        const changeSummary = data.changes ? `+${data.changes.added}/-${data.changes.removed}` : ''
        addLog('info', `文件变更: ${data.path} (${data.operation}) ${changeSummary}`)
        break
      }
      case 'thinking': {
        const agent = data.agent || 'AI Agent'
        const msg = data.message || data.content
        const ts = normalizeEventTimestamp(data.timestamp)
        const phase = data.phase || ''
        const isStreaming = data.streaming === true

        if (isStreaming && msg) {
          thinkingBatcher.enqueue({
            key: `${agent}:${phase}`,
            agent,
            phase,
            timestamp: ts,
            model: data.model,
            accumulated: data.accumulated,
            responseDelta: msg
          })
        } else {
          thinkingBatcher.flush()
          markThinkingStreamEnded(workspace.thinkingMessages, { agent })
          if (data.streaming === false && !msg) {
            break
          }
          workspace.thinkingMessages.push({
            agent,
            message: msg,
            timestamp: ts,
            model: data.model || workspace.currentModel,
            phase,
            reasoningSteps: data.reasoning_steps || [],
            confidence: data.confidence || null
          })
        }

        if (!isStreaming) {
          addLog('thinking', `[${agent}] ${msg}`)
          if (data.phase) {
            addThinkingToStage(data.phase, { agent, message: msg, timestamp: ts, model: data.model || workspace.currentModel })
          }
        }
        break
      }
      case 'model_info': {
        workspace.currentAgent = data.agent
        workspace.currentModel = data.model
        generation.currentAgent = data.agent
        generation.currentModel = data.model
        addLog('info', `使用模型: ${data.model} (${data.agent})`)
        addDetail('模型分配', `${data.agent} → ${data.model}`)
        // 兼容后端可能的命名变体（_report_model_info 当前传 str(engineer)，
        // 真实意图应当是 frontend/backend/architect/reviewer/fallback）
        const assignmentKey = normalizeAgentRole(data.agent)
        if (generation.modelAssignments[assignmentKey]) {
          generation.modelAssignments[assignmentKey].model = data.model
          generation.modelAssignments[assignmentKey].calls++
        }
        if (data.fallback_from) {
          generation.fallbackHistory.push({
            from_model: data.fallback_from,
            to_model: data.model,
            reason: data.reason || null,
            timestamp: data.timestamp ? String(data.timestamp) : null
          })
          generation.fallbackHistory = generation.fallbackHistory.slice(-50)
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
      case 'cancelled':
        thinkingBatcher.flush()
        markThinkingStreamEnded(workspace.thinkingMessages)
        taskFeedback?.update({ status: 'stopped', stage: '会话已停止', nextAction: '输入新需求后继续' })
        addLog('warning', data.data?.message || '项目已停止')
        break
      case 'error':
        thinkingBatcher.flush()
        markThinkingStreamEnded(workspace.thinkingMessages)
        taskFeedback?.fail(data.data?.error || data.message || '任务执行失败', data)
        addLog('error', data.data?.error || data.message || '未知错误')
        break
      case 'warning':
        addLog('warning', data.message || data.content || '警告')
        if (data.code) {
          addDetail('警告详情', `[${data.code}] ${data.message}`)
        }
        break
      case 'pause_for_approval':
        workspace.pendingApproval = {
          filePath: data.data?.file_path,
          sessionId: data.data?.session_id,
          description: data.data?.description
        }
        addLog('warning', `等待审批: ${data.data?.file_path || '文件'}`)
        break
      case 'file_rejected':
        addLog('warning', `文件被拒绝: ${data.data?.file_path}`)
        break
      case 'log':
        addLog('info', data.data?.message || data.message || '')
        break
      case 'react_tool_call': {
        const toolMsg = data.message || `调用工具: ${data.tool || '未知'}`
        addLog('info', toolMsg)
        addDetail('工具调用', `Round ${data.round || '?'}: ${data.tool || '未知'}`)
        if (!Array.isArray(workspace.toolEvents)) workspace.toolEvents = []
        workspace.toolEvents.push({
          id: `${data.tool || 'tool'}-${data.round || 0}-${Date.now()}`,
          tool: data.tool || 'unknown',
          params: data.params || {},
          round: data.round,
          maxRounds: data.max_rounds,
          message: toolMsg,
          status: 'running',
          result: '',
          timestamp: normalizeEventTimestamp(data.timestamp),
          agent: data.agent || workspace.currentAgent
        })
        break
      }
      case 'react_tool_result': {
        const resultMsg = data.message || `工具返回: ${data.tool || '未知'}`
        addLog('info', resultMsg)
        if (!Array.isArray(workspace.toolEvents)) workspace.toolEvents = []
        const running = [...workspace.toolEvents].reverse().find(
          item => item.tool === (data.tool || item.tool) && item.status === 'running'
        )
        if (running) {
          running.status = 'done'
          running.result = resultMsg
          running.resultCount = data.result_count
        } else {
          workspace.toolEvents.push({
            id: `${data.tool || 'tool'}-result-${Date.now()}`,
            tool: data.tool || 'unknown',
            params: {},
            round: data.round,
            message: resultMsg,
            status: 'done',
            result: resultMsg,
            timestamp: normalizeEventTimestamp(data.timestamp),
            agent: data.agent || workspace.currentAgent
          })
        }
        break
      }
      case 'react_generating': {
        workspace.currentAgent = data.agent || workspace.currentAgent
        if (data.model) workspace.currentModel = data.model
        break
      }
      case 'done':
        thinkingBatcher.flush()
        markThinkingStreamEnded(workspace.thinkingMessages)
        taskFeedback?.complete({ ...data, stage: getPhaseLabel('generation_complete'), progress: 100, nextAction: '预览或下载生成文件' })
        addLog('success', '项目生成完成')
        generation.workflowStages.forEach(stage => {
          if (stage.status !== 'failed') updateStageStatus(stage.id, 'completed', 100)
        })
        if (session.currentSessionId) {
          const doneData = data.data || data
          const dirName = doneData.project_path || doneData.output_dir || session.currentSessionId
          workspace.currentProjectPath = dirName
        }
        if (data.data?.performance) {
          workspace.performanceMetrics = data.data.performance
        }
        if (data.data?.cost) {
          workspace.costData = data.data.cost
        }
        break
      default:
        // 静默忽略未知消息类型，避免控制台噪音
        break
    }
  }

  const processSseResponse = async (response) => {
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let terminalEvent = null
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed.startsWith('data: ')) {
          try {
            const data = JSON.parse(trimmed.slice(6))
            if (['done', 'error', 'cancelled'].includes(data.type)) terminalEvent = data.type
            handleSseMessage(data)
          } catch (e) {
            console.error('Failed to parse SSE:', e)
          }
        }
      }
    }
    if (buffer.trim().startsWith('data: ')) {
      try {
        const data = JSON.parse(buffer.trim().slice(6))
        if (['done', 'error', 'cancelled'].includes(data.type)) terminalEvent = data.type
        handleSseMessage(data)
      } catch (e) {
        // ignore trailing incomplete data
      }
    }
    thinkingBatcher.flush()
    markThinkingStreamEnded(workspace.thinkingMessages)
    return terminalEvent
  }

  const buildStreamParams = (requirement, sessionId, selectedProviderModel, projectName) => {
    const selectedApiKeyToken = apiKeyStore.preferredAgentKey
    
    // 解析动态供应商选择 (格式: "provider_id::model_id")
    let providerId = undefined
    if (selectedProviderModel && selectedProviderModel.includes('::')) {
      providerId = selectedProviderModel.split('::')[0]
    }
    
    // 自动判断模式：有已生成文件则为增量更新，否则为新建
    const hasExistingFiles = files.generatedFiles.length > 0
    const incrementalOptions = resolveIncrementalStreamOptions(
      hasExistingFiles,
      workspace.currentProjectPath,
    )
    
    return {
      requirement,
      session_id: sessionId,
      enable_review: true,
      enable_validation: true,
      enable_error_recovery: true,
      enable_memory: true,
      spec_first: true,
      dependency_graph: true,
      require_approval: false,
      api_key_token: selectedApiKeyToken ? selectedApiKeyToken.token : undefined,
      provider_id: providerId,
      project_name: projectName || undefined,
      ...incrementalOptions,
    }
  }

  // 429 并发限制弹窗：显示活跃会话列表和操作选项
  const showConcurrentLimitDialog = async (error, projectApi, session) => {
    const sessions = error.activeSessions || []
    const limit = error.limit || 0
    const count = error.currentCount || sessions.length

    // 构建会话列表 HTML
    let sessionsHtml = ''
    if (sessions.length > 0) {
      const items = sessions.map((s, i) => {
        const req = s.requirement ? (s.requirement.length > 60 ? s.requirement.slice(0, 60) + '...' : s.requirement) : '未知需求'
        const createdAt = s.created_at ? new Date(s.created_at).toLocaleString('zh-CN') : '未知时间'
        const statusMap = { running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消' }
        const statusText = statusMap[s.status] || s.status
        return `<div style="padding:8px 12px;margin:4px 0;background:#f5f5f5;border-radius:6px;display:flex;justify-content:space-between;align-items:center;">
          <div style="flex:1;min-width:0;">
            <div style="font-size:13px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${req}</div>
            <div style="font-size:11px;color:#999;margin-top:2px;">${createdAt} · ${statusText}</div>
          </div>
          <div style="margin-left:8px;font-size:11px;color:#e6a23c;font-weight:500;">#${i + 1}</div>
        </div>`
      }).join('')
      sessionsHtml = `<div style="margin-top:12px;max-height:240px;overflow-y:auto;">${items}</div>`
    }

    try {
      await ElMessageBox.confirm(
        `<div style="line-height:1.6;">
          <div style="font-weight:600;margin-bottom:8px;">并发会话已满 (${count}/${limit})</div>
          <div style="color:#666;font-size:13px;">当前已有 ${count} 个活跃项目，达到上限 ${limit} 个。请先停止或删除一个现有项目后再创建新项目。</div>
          ${sessionsHtml}
        </div>`,
        '无法创建新项目',
        {
          confirmButtonText: '停止最早的项目',
          cancelButtonText: '知道了',
          dangerouslyUseHTMLString: true,
          type: 'warning',
          distinguishCancelAndClose: true
        }
      )

      // 用户点击"停止最早的项目"
      if (sessions.length > 0) {
        const oldest = sessions[sessions.length - 1]
        try {
          await projectApi.stopSession(oldest.session_id)
          ElMessage.success('已停止项目，现在可以创建新项目了')
          // 清除当前会话，让用户可以重新创建
          session.currentSessionId = null
        } catch (stopError) {
          ElMessage.error('停止项目失败: ' + stopError.message)
        }
      }
    } catch (action) {
      // 用户点击"知道了"或关闭弹窗，不做任何操作
    }
  }

  const streamGenerate = async (selectedProviderModel, projectName) => {
    if (generation.isGenerating) {
      ElMessage.warning('当前会话正在生成中')
      return
    }
    // 检查是否有 SiliconFlow API Key 或动态供应商
    if (!apiKeyStore.hasSiliconflowKey && !apiKeyStore.hasGlmKey && !selectedProviderModel) {
      ElMessage.warning('请先配置 SiliconFlow 或智谱 GLM API Key，或选择自定义供应商模型')
      return
    }

    // 自动判断模式
    const hasExistingFiles = files.generatedFiles.length > 0
    const isIncremental = resolveIncrementalStreamOptions(
      hasExistingFiles,
      workspace.currentProjectPath,
    ).incremental
    const mode = isIncremental ? '增量更新' : '新建项目'
    
    if (!isIncremental) {
      files.generatedFiles = []
      files.fileDiffs = []
    }
    workspace.logs = []
    workspace.toolEvents = []
    generation.isGenerating = true
    taskFeedback?.start({ stage: isIncremental ? '准备增量更新' : '准备生成项目', progress: 0 })
    addLog('info', `开始${mode}...`)

    let streamSessionId = null
    try {
      streamSessionId = session.currentSessionId || session.createNewSession({})
      activeStreamSessionId = streamSessionId
      const params = buildStreamParams(session.projectPrompt, streamSessionId, selectedProviderModel, projectName)
      const response = await projectApi.generateProjectStream(params)
      const terminalEvent = await processSseResponse(response)
      if (!terminalEvent) {
        taskFeedback?.markDisconnected('任务连接意外结束，当前消息和文件已保留')
        addLog('warning', '任务连接意外结束，已保留当前状态')
        return
      }
      if (terminalEvent === 'error' || terminalEvent === 'cancelled') return
      if (session.currentSessionId === streamSessionId) {
        const observedContext = generation.getModelContextSnapshot()
        try {
          let modelContext = await projectApi.updateAgentModelContext(
            streamSessionId,
            observedContext
          )
          if (modelContext.conflict) {
            const latest = await projectApi.getAgentModelContext(streamSessionId)
            modelContext = await projectApi.updateAgentModelContext(streamSessionId, {
              ...observedContext,
              expected_revision: latest.revision,
              config_version: latest.context.config_version,
              roles: latest.context.roles,
            })
          }
          if (modelContext.conflict) {
            throw new Error('模型上下文已被其他页面更新')
          }
          if (session.currentSessionId === streamSessionId) {
            generation.applyModelContext(modelContext.context, modelContext.revision)
          }
        } catch (syncError) {
          addLog('warning', `同步模型上下文失败，保留本地状态: ${syncError.message}`)
        }
        addLog('success', `${mode}完成`)
        session.projectPrompt = ''
      }
    } catch (error) {
      // 429 并发限制：显示详细提醒和操作选项
      if (error.code === 429) {
        taskFeedback?.fail(error.message, { stage: '等待可用会话', nextAction: '停止已有项目后重试' })
        addLog('error', `并发会话已满: ${error.message}`)
        showConcurrentLimitDialog(error, projectApi, session)
        return
      }

      if (error.name === 'TypeError' || error.name === 'NetworkError') {
        taskFeedback?.markDisconnected('网络连接中断，当前消息和文件已保留')
      } else {
        taskFeedback?.fail(error, { stage: '项目生成失败', nextAction: '检查配置后重新生成' })
      }
      addLog('error', `${mode}失败: ${error.message}`)
      ElMessage.error(`${mode}失败`)
    } finally {
      thinkingBatcher.flush()
      if (activeStreamSessionId === streamSessionId) {
        activeStreamSessionId = null
        generation.isGenerating = false
      }
    }
  }

  return reactive({
    handleSseMessage, processSseResponse, streamGenerate
  })
}
