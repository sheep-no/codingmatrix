  const stopSession = async () => {
    if (!form.value.sessionId) return
    
    try {
      await api.stopSession(form.value.sessionId)
      isGenerating.value = false
      hasStopped.value = true
      addLog('info', '项目已停止')
    } catch (error) {
      addLog('error', `停止项目失败: ${error.message}`)
    }
  }

  const deleteSession = async () => {
    if (!form.value.sessionId) return
    
    if (!confirm('确定要删除这个项目吗？这将释放所有相关资源。')) {
      return
    }
    
    try {
      await api.deleteSession(form.value.sessionId)
      resetAndStartNew()
      addLog('info', '项目已删除')
    } catch (error) {
      addLog('error', `删除项目失败: ${error.message}`)
    }
  }