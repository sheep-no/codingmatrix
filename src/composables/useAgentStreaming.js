import { reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useApiKeyStore } from '@/stores/apikey'
import { getPhaseLabel } from '@/constants/agentPhases'

export function useAgentStreaming(projectApi, workspace, files, generation, session) {
  // 注意：workspace 和 files 是 reactive() 对象，ref 属性会被自动解包
  // 不能解构后使用 .value，必须通过对象访问（如 workspace.currentAgent）
  const { addLog, addDetail } = workspace
  const { ensureStage, updateStageStatus, addThinkingToStage } = generation

  // 获取 API Key Store
  const apiKeyStore = useApiKeyStore()

  // model_info 事件中 data.agent 的可能命名 → 标准化为 modelAssignments 的 key
  // 解决：前端先用了 5 角色硬编码、后端又用 str(engineer) 传对象 repr 的双重历史遗留
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
  }

  const handleSseMessage = (data) => {
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
        // 兼容后端可能的命名变体（_report_model_info 当前传 str(engineer)，
        // 真实意图应当是 frontend/backend/architect/reviewer/fallback）
        const rawAgent = (data.agent || '').toString().toLowerCase()
        const assignmentKey = AGENT_ROLE_ALIAS[rawAgent] || rawAgent
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
        break
      }
      case 'react_tool_result': {
        const resultMsg = data.message || `工具返回: ${data.tool || '未知'}`
        addLog('info', resultMsg)
        break
      }
      case 'react_generating': {
        workspace.currentAgent = data.agent || workspace.currentAgent
        if (data.model) workspace.currentModel = data.model
        break
      }
      case 'done':
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
        // 静默忽略未知消息类型，避免控制台噪音
        break
    }
  }

  const processSseResponse = async (response) => {
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
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
        handleSseMessage(data)
      } catch (e) {
        // ignore trailing incomplete data
      }
    }
  }

  const buildStreamParams = (requirement, sessionId, selectedProviderModel, projectName) => {
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
      project_name: projectName || undefined,
      ...(isIncremental ? {
        project_path: workspace.currentProjectPath
      } : {})
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
      const params = buildStreamParams(session.projectPrompt, sessionId, selectedProviderModel, projectName)
      const response = await projectApi.generateProjectStream(params)
      await processSseResponse(response)
      generation.isGenerating = false
      addLog('success', `${mode}完成`)
      session.projectPrompt = ''
    } catch (error) {
      generation.isGenerating = false
      
      // 429 并发限制：显示详细提醒和操作选项
      if (error.code === 429) {
        addLog('error', `并发会话已满: ${error.message}`)
        showConcurrentLimitDialog(error, projectApi, session)
        return
      }
      
      addLog('error', `${mode}失败: ${error.message}`)
      ElMessage.error(`${mode}失败`)
    }
  }

  return reactive({
    handleSseMessage, processSseResponse, streamGenerate
  })
}
