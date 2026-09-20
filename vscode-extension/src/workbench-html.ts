// The workbench is a single self-contained webview. The chat panel keeps the
// live Agent session; the other five panels read user-scoped v1 APIs through
// the `workbench_request` channel handled by AgentWorkbenchController.
const WORKBENCH_STYLES = `
body{font-family:var(--vscode-font-family);color:var(--vscode-foreground);background:var(--vscode-editor-background);padding:20px;max-width:960px;margin:auto}
h1{font-size:22px;margin:0 0 8px}
button{color:var(--vscode-button-foreground);background:var(--vscode-button-background);border:0;padding:6px 12px;border-radius:3px;margin:4px 4px 4px 0;cursor:pointer}
button:disabled{opacity:.5;cursor:default}
button.danger{background:var(--vscode-errorForeground);color:var(--vscode-editor-background)}
button.secondary{background:var(--vscode-button-secondaryBackground,var(--vscode-button-background));color:var(--vscode-button-secondaryForeground,var(--vscode-button-foreground))}
textarea,input[type=text]{display:block;width:100%;box-sizing:border-box;background:var(--vscode-input-background);color:var(--vscode-input-foreground);border:1px solid var(--vscode-input-border);padding:6px}
textarea{min-height:90px;margin:10px 0}
#status{color:var(--vscode-descriptionForeground);margin:12px 0}
.tabs{border-bottom:1px solid var(--vscode-panel-border);margin-bottom:12px}
.tab-button{background:transparent;color:var(--vscode-foreground);border-bottom:2px solid transparent;border-radius:0;padding:8px 12px}
.tab-button.active{border-bottom-color:var(--vscode-focusBorder);font-weight:600}
.tab-panel{display:none}
.tab-panel.active{display:block}
.panel{border:1px solid var(--vscode-panel-border);padding:14px;margin-top:16px;border-radius:5px}
.item{border:1px solid var(--vscode-panel-border);border-radius:4px;padding:10px;margin-top:8px}
.item-title{font-weight:600;word-break:break-all}
.item-actions{margin-top:6px}
.row{display:flex;gap:10px;padding:3px 0}
.row .key{color:var(--vscode-descriptionForeground);min-width:160px}
.row .value{word-break:break-all}
.muted{color:var(--vscode-descriptionForeground);word-break:break-all}
.code{white-space:pre-wrap;word-break:break-all;background:var(--vscode-textCodeBlock-background);padding:10px;border-radius:4px;max-height:320px;overflow:auto}
.message{white-space:pre-wrap;border-left:3px solid var(--vscode-textLink-foreground);padding:8px;margin:6px 0}
.message.error{border-left-color:var(--vscode-errorForeground)}
`;

// No template literals or `${` may appear below: this text is embedded in a
// TypeScript template literal, so those sequences would be interpolated early.
const WORKBENCH_SCRIPT = `
const vscode=acquireVsCodeApi();
let approval,sequence=0,activeSession;
const pending=new Map();
const $=function(id){return document.getElementById(id);};
const status=$('status'),messages=$('messages'),approve=$('approve'),reject=$('reject'),prompt=$('prompt'),send=$('send');
const setStatus=function(text){status.textContent=text;};
const append=function(text,error){
  const item=document.createElement('p');
  item.className='message'+(error?' error':'');
  item.textContent=text;
  messages.appendChild(item);
  messages.scrollTop=messages.scrollHeight;
};
const empty=function(target,text){
  target.textContent='';
  const node=document.createElement('p');
  node.className='muted';
  node.textContent=text;
  target.appendChild(node);
};
const setCode=function(target,text){
  target.textContent='';
  const node=document.createElement('pre');
  node.className='code';
  node.textContent=text;
  target.appendChild(node);
};
const percent=function(value){
  const rate=Number(value||0);
  return (Number.isFinite(rate)?rate*100:0).toFixed(1);
};
const button=function(label,onClick,className){
  const node=document.createElement('button');
  node.textContent=label;
  if(className)node.className=className;
  node.addEventListener('click',onClick);
  return node;
};
const row=function(label,value){
  const line=document.createElement('div');
  line.className='row';
  const key=document.createElement('span');
  key.className='key';
  key.textContent=label;
  const val=document.createElement('span');
  val.className='value';
  val.textContent=value;
  line.appendChild(key);
  line.appendChild(val);
  return line;
};
const listItem=function(title,subtitle,actions){
  const box=document.createElement('div');
  box.className='item';
  const heading=document.createElement('div');
  heading.className='item-title';
  heading.textContent=title;
  box.appendChild(heading);
  if(subtitle){
    const sub=document.createElement('div');
    sub.className='muted';
    sub.textContent=subtitle;
    box.appendChild(sub);
  }
  if(actions&&actions.length){
    const bar=document.createElement('div');
    bar.className='item-actions';
    actions.forEach(function(action){bar.appendChild(action);});
    box.appendChild(bar);
  }
  return box;
};
const request=function(resource,params){
  const requestId='req-'+(++sequence);
  return new Promise(function(resolve,reject){
    pending.set(requestId,{resolve:resolve,reject:reject});
    vscode.postMessage({type:'workbench_request',request_id:requestId,resource:resource,params:params||{}});
  });
};
const runRequest=function(resource,params,onData){
  return request(resource,params).then(function(data){return onData(data);}).catch(function(error){
    setStatus(error&&error.message?error.message:'请求失败');
  });
};
const tabButtons=document.querySelectorAll('.tab-button');
const tabPanels=document.querySelectorAll('.tab-panel');
const activate=function(name){
  tabButtons.forEach(function(tab){tab.classList.toggle('active',tab.getAttribute('data-tab')===name);});
  tabPanels.forEach(function(panel){panel.classList.toggle('active',panel.id==='tab-'+name);});
};
tabButtons.forEach(function(tab){tab.addEventListener('click',function(){activate(tab.getAttribute('data-tab'));});});
const control=function(action){
  vscode.postMessage({type:'workbench_control',action:action});
  setStatus(action==='pause'?'Agent 已暂停':action==='resume'?'Agent 正在恢复':'Agent 已取消');
};
$('hello').addEventListener('click',function(){vscode.postMessage({type:'workbench_ready'});setStatus('已发送工作台连接请求');});
send.addEventListener('click',function(){
  const value=prompt.value.trim();
  if(!value)return;
  append('你：'+value);
  vscode.postMessage({type:'workbench_prompt',prompt:value});
  prompt.value='';
  send.disabled=true;
  setStatus('Agent 正在处理');
});
$('pause').addEventListener('click',function(){control('pause');});
$('resume').addEventListener('click',function(){control('resume');});
$('cancel').addEventListener('click',function(){control('cancel');});
const decide=function(approved){
  if(!approval)return;
  vscode.postMessage({type:'agent_host_message',message:{message_id:approval.message_id+':decision',schema_version:approval.schema_version,session_id:approval.session_id,kind:'approval_decision',payload:{request_id:approval.message_id,approved:approved}}});
  approval=undefined;
  approve.hidden=true;
  reject.hidden=true;
};
approve.addEventListener('click',function(){decide(true);});
reject.addEventListener('click',function(){decide(false);});
const loadHistory=function(){
  setStatus('正在读取会话历史');
  return runRequest('history_list',{limit:20,offset:0},function(items){
    const target=$('history-list');
    if(!items||!items.length){empty(target,'暂无会话历史');return;}
    target.textContent='';
    items.forEach(function(item){
      const open=button('查看',function(){loadConversation(item.conversation_id);});
      const remove=button('删除',function(){removeConversation(item.conversation_id,item.title);},'danger');
      target.appendChild(listItem(item.title||('会话 #'+item.conversation_id),item.prompt||'',[open,remove]));
    });
    setStatus('会话历史已更新');
  });
};
const loadConversation=function(conversationId){
  setStatus('正在读取会话内容');
  return runRequest('history_messages',{conversation_id:conversationId,limit:50},function(items){
    const target=$('history-detail');
    target.textContent='';
    if(!items||!items.length){empty(target,'该会话暂无消息');return;}
    items.slice().reverse().forEach(function(message){
      const block=document.createElement('div');
      block.className='item';
      const question=document.createElement('div');
      question.textContent='你：'+(message.prompt||'');
      const answer=document.createElement('div');
      answer.className='muted';
      answer.textContent='Agent：'+(message.response||'');
      block.appendChild(question);
      block.appendChild(answer);
      target.appendChild(block);
    });
    setStatus('会话内容已加载');
  });
};
const removeConversation=function(conversationId,title){
  setStatus('正在删除会话');
  return runRequest('history_delete',{conversation_id:conversationId},function(count){
    append('已删除会话：'+(title||conversationId)+'（'+count+' 条记录）');
    return loadHistory();
  });
};
$('history-refresh').addEventListener('click',function(){loadHistory();});
const loadModels=function(){
  setStatus('正在读取模型配置');
  return Promise.all([request('model_config',{}),request('token_usage',{})]).then(function(results){
    const config=results[0]||{},usage=results[1]||{};
    const rolesTarget=$('model-roles');
    const roles=config.roles||{};
    const roleKeys=Object.keys(roles);
    rolesTarget.textContent='';
    if(!roleKeys.length){empty(rolesTarget,'未配置角色模型');}
    roleKeys.forEach(function(key){
      const role=roles[key]||{};
      rolesTarget.appendChild(row(key,role.model||role.model_id||role.name||'-'));
    });
    const usageTarget=$('model-usage');
    usageTarget.textContent='';
    usageTarget.appendChild(row('总 Tokens',String(usage.total_tokens||0)));
    usageTarget.appendChild(row('输入 Tokens',String(usage.prompt_tokens||0)));
    usageTarget.appendChild(row('输出 Tokens',String(usage.completion_tokens||0)));
    usageTarget.appendChild(row('消息数',String(usage.total_messages||0)));
    usageTarget.appendChild(row('今日 Tokens',String(usage.today_tokens||0)));
    usageTarget.appendChild(row('本月 Tokens',String(usage.this_month_tokens||0)));
    const modelKeys=Object.keys(usage.by_model||{});
    setCode($('model-detail'),modelKeys.length?modelKeys.map(function(key){return key+': '+JSON.stringify(usage.by_model[key]);}).join('\\n'):'暂无按模型统计');
    setStatus('模型配置已更新');
  }).catch(function(error){setStatus(error&&error.message?error.message:'模型配置读取失败');});
};
$('models-refresh').addEventListener('click',function(){loadModels();});
const versionsSession=function(){
  const typed=$('version-session').value.trim();
  return typed||activeSession||'';
};
const loadSnapshots=function(){
  const sessionId=versionsSession();
  if(!sessionId){setStatus('请先填写会话 ID');return Promise.resolve();}
  setStatus('正在读取版本快照');
  return runRequest('snapshot_list',{session_id:sessionId},function(items){
    const target=$('version-list');
    if(!items||!items.length){empty(target,'该会话暂无版本快照');return;}
    target.textContent='';
    items.forEach(function(snapshot,index){
      const actions=[button('回滚',function(){rollbackSnapshot(sessionId,snapshot.tag);})];
      const previous=items[index+1];
      if(previous){actions.push(button('对比上一版',function(){diffSnapshots(sessionId,previous.tag,snapshot.tag);},'secondary'));}
      target.appendChild(listItem(snapshot.tag,snapshot.message||snapshot.commit||'',actions));
    });
    setStatus('版本快照已更新');
  });
};
const rollbackSnapshot=function(sessionId,tag){
  setStatus('正在回滚到 '+tag);
  return runRequest('snapshot_rollback',{session_id:sessionId,target_tag:tag},function(result){
    append('已回滚到 '+tag+'，恢复 '+(result?result.filesRestored:0)+' 个文件');
    setStatus('回滚完成');
    return loadSnapshots();
  });
};
const diffSnapshots=function(sessionId,fromTag,toTag){
  setStatus('正在生成版本差异');
  return runRequest('snapshot_diff',{session_id:sessionId,from_tag:fromTag,to_tag:toTag},function(diff){
    setCode($('version-diff'),diff||'（无差异）');
    setStatus('版本差异已更新');
  });
};
$('versions-load').addEventListener('click',function(){loadSnapshots();});
const loadPerformance=function(){
  setStatus('正在读取性能指标');
  return runRequest('performance',{},function(data){
    const metrics=(data&&data.metrics)||{};
    const target=$('performance-body');
    target.textContent='';
    const metricKeys=Object.keys(metrics);
    if(!metricKeys.length){empty(target,'暂无性能指标');}
    metricKeys.forEach(function(key){
      const value=metrics[key];
      target.appendChild(row(key,typeof value==='object'?JSON.stringify(value):String(value)));
    });
    const trends=(data&&data.trends)||{};
    const trendKeys=Object.keys(trends);
    setCode($('performance-trends'),trendKeys.length?trendKeys.map(function(key){
      const trend=trends[key]||{};
      return key+': avg '+String(trend.avg_time_ms)+'ms / max '+String(trend.max_time_ms)+'ms / calls '+String(trend.total_calls)+' / cache '+String(trend.cache_hit_rate);
    }).join('\\n'):'暂无趋势数据');
    setStatus('性能指标已更新');
  });
};
$('performance-refresh').addEventListener('click',function(){loadPerformance();});
const loadLearning=function(){
  setStatus('正在读取学习统计');
  return runRequest('learning',{},function(data){
    const stats=data||{};
    const target=$('learning-body');
    target.textContent='';
    target.appendChild(row('已学习模式',String(stats.learned_patterns||0)));
    target.appendChild(row('累计修复记录',String(stats.total_fixes_recorded||0)));
    target.appendChild(row('累计会话',String(stats.total_sessions||0)));
    target.appendChild(row('整体成功率',percent(stats.overall_success_rate)+'%'));
    const patterns=stats.top_errors||[];
    const errorTarget=$('learning-errors');
    errorTarget.textContent='';
    if(!patterns.length){empty(errorTarget,'暂无常见错误');}
    patterns.forEach(function(item){
      const meta=[item.error_message||'','频次 '+String(item.frequency||0),'成功率 '+percent(item.success_rate)+'%'];
      if(item.fix_description)meta.push('修复：'+item.fix_description);
      errorTarget.appendChild(listItem(item.error_type||'未知错误',meta.join(' · ')));
    });
    setStatus('学习统计已更新');
  });
};
$('learning-refresh').addEventListener('click',function(){loadLearning();});
window.addEventListener('message',function(event){
  const data=event.data;
  if(data&&data.type==='workbench_response'){
    const entry=pending.get(data.request_id);
    if(!entry)return;
    pending.delete(data.request_id);
    if(data.ok)entry.resolve(data.data);
    else entry.reject(new Error(data.error||'请求失败'));
    return;
  }
  if(data&&data.type==='workbench_event'){
    const value=data.event||{},payload=value.data||{};
    if(value.type==='done'){
      if(typeof payload.session_id==='string'&&payload.session_id){
        activeSession=payload.session_id;
        const input=$('version-session');
        if(input&&!input.value)input.value=payload.session_id;
      }
      setStatus('Agent 已完成');
      send.disabled=false;
    }
    if(value.type==='error'){setStatus('Agent 执行失败');send.disabled=false;}
    const text=typeof payload==='string'?payload:payload.message||payload.error||value.type;
    if(text)append(value.type+'：'+text,value.type==='error');
    return;
  }
  if(data&&data.type!=='agent_host_message')return;
  setStatus('已收到 Agent Host 事件');
  if(data.message&&data.message.kind==='approval_request'){
    approval=data.message;
    approve.hidden=false;
    reject.hidden=false;
    const payload=data.message.payload||{};
    append('等待审批：'+(payload.reason||payload.summary||data.message.capability||''));
  }
});
activate('chat');
`;

export function createAgentWorkbenchHtml(): string {
  return `<!doctype html>
<html><head><meta charset="UTF-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-codingmatrix-agent-host';"><style>${WORKBENCH_STYLES}
</style></head><body>
<h1>CodingMatrix Agent</h1>
<div id="status">VS Code Agent 工作台已连接</div>
<nav class="tabs">
<button class="tab-button" data-tab="chat">对话</button>
<button class="tab-button" data-tab="history">会话历史</button>
<button class="tab-button" data-tab="models">模型</button>
<button class="tab-button" data-tab="versions">文件版本</button>
<button class="tab-button" data-tab="performance">性能</button>
<button class="tab-button" data-tab="learning">学习</button>
</nav>
<section class="tab-panel" id="tab-chat">
<div class="panel"><p>当前工作台共享 Web Agent 会话，可在这里继续对话、审批本地动作和查看验证结果。</p><textarea id="prompt" maxlength="5000" placeholder="输入 Agent 需求"></textarea><button id="send">发送需求</button><button id="hello">连接本地 Agent Host</button><button id="pause">暂停</button><button id="resume">恢复</button><button id="cancel">取消</button><button id="approve" hidden>批准当前动作</button><button id="reject" hidden>拒绝当前动作</button><div id="messages" aria-live="polite"></div></div>
</section>
<section class="tab-panel" id="tab-history">
<div class="panel"><button id="history-refresh">刷新会话列表</button><div id="history-list"></div></div>
<div class="panel"><h2>会话内容</h2><div id="history-detail"></div></div>
</section>
<section class="tab-panel" id="tab-models">
<div class="panel"><button id="models-refresh">刷新模型与用量</button><div id="model-roles"></div><div id="model-usage"></div><div id="model-detail"></div></div>
</section>
<section class="tab-panel" id="tab-versions">
<div class="panel"><p>留空时使用最近一次 Agent 会话的 ID。</p><input type="text" id="version-session" placeholder="会话 ID"><button id="versions-load">读取版本</button><div id="version-list"></div><div id="version-diff"></div></div>
</section>
<section class="tab-panel" id="tab-performance">
<div class="panel"><button id="performance-refresh">刷新性能</button><div id="performance-body"></div><div id="performance-trends"></div></div>
</section>
<section class="tab-panel" id="tab-learning">
<div class="panel"><button id="learning-refresh">刷新学习统计</button><div id="learning-body"></div><div id="learning-errors"></div></div>
</section>
<script nonce="codingmatrix-agent-host">${WORKBENCH_SCRIPT}
</script></body></html>`;
}
