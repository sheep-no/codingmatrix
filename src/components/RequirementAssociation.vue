<template>
  <div v-if="visible" class="requirement-association-overlay">
    <div class="requirement-association-panel">
      <div class="panel-header">
        <h3>[需求联想] 功能补全建议</h3>
        <span
          v-for="domain in (associationResult.domains_matched || [associationResult.domain_matched])"
          v-show="domain"
          :key="domain"
          class="domain-badge"
        >
          {{ domainLabelMap[domain] || domain }}
        </span>
        <button class="close-btn" @click="skipAssociation">跳过</button>
      </div>

      <div v-if="associationResult.skipped" class="skip-info">
        <p>{{ associationResult.skip_reason }}</p>
        <button @click="$emit('skip')">继续生成</button>
      </div>

      <div v-else class="association-content">
        <div class="stats-row">
          <span class="stat">联想项: {{ (associationResult.items || []).length }}</span>
          <span class="stat">耗时: {{ (associationResult.elapsed_seconds || 0).toFixed(1) }}s</span>
          <span v-if="associationResult.domain_matched" class="stat">
            领域: {{ domainLabelMap[associationResult.domain_matched] }}
          </span>
        </div>

        <div
          v-if="(associationResult.devil_review_items || []).length > 0"
          class="devil-review-section"
        >
          <h4 class="category-risk">反向审视提醒</h4>
          <div
            v-for="review in associationResult.devil_review_items"
            :key="review.target_item"
            class="devil-review-item"
          >
            <span class="devil-target">[{{ review.target_item }}]</span>
            <span class="devil-challenge">{{ review.challenge }}</span>
            <span
              class="devil-severity"
              :class="'severity-' + review.severity"
            >
              {{ review.severity }}
            </span>
            <span v-if="review.suggestion" class="devil-suggestion">
              建议: {{ review.suggestion }}
            </span>
          </div>
        </div>

        <div v-for="category in displayCategories" :key="category.key" class="category-group">
          <h4 :class="'category-' + category.key">
            {{ category.label }}
            <span class="item-count">({{ getCategoryItems(category.key).shown.length }})</span>
          </h4>

          <div class="item-list">
            <div
              v-for="item in getCategoryItems(category.key).shown"
              :key="item.content"
              class="association-item shown"
            >
              <input
                type="checkbox"
                :checked="isItemAccepted(item)"
                @change="toggleItem(item)"
              />
              <span class="item-content">{{ item.content }}</span>
              <span
                class="item-source"
                :class="'source-' + getSourceClass(item.source)"
              >
                {{ getSourceLabel(item.source) }}
              </span>
              <span
                v-if="item.dual_model_agreement === 'both_agree'"
                class="dual-badge both"
              >
                双模型一致
              </span>
              <span
                v-if="item.dual_model_agreement === 'needs_confirmation'"
                class="dual-badge single"
              >
                待确认
              </span>
              <span class="item-confidence">{{ (item.confidence * 100).toFixed(0) }}%</span>
            </div>
          </div>

          <div v-if="getCategoryItems(category.key).collapsed.length > 0" class="collapsed-section">
            <button class="expand-btn" @click="toggleCollapsed(category.key)">
              {{ collapsedState[category.key] ? '收起更多建议' : '展开更多建议' }}
              ({{ getCategoryItems(category.key).collapsed.length }}项)
            </button>
            <div v-if="collapsedState[category.key]" class="collapsed-items">
              <div
                v-for="item in getCategoryItems(category.key).collapsed"
                :key="item.content"
                class="association-item collapsed"
              >
                <input
                  type="checkbox"
                  :checked="isItemAccepted(item)"
                  @change="toggleItem(item)"
                />
                <span class="item-content">{{ item.content }}</span>
                <span class="item-source" :class="'source-' + getSourceClass(item.source)">
                  {{ getSourceLabel(item.source) }}
                </span>
                <span class="item-confidence low">{{ (item.confidence * 100).toFixed(0) }}%</span>
              </div>
            </div>
          </div>
        </div>

        <div class="helpfulness-section">
          <p class="helpfulness-question">这些建议对你有帮助吗?</p>
          <div class="helpfulness-options">
            <button
              class="helpfulness-btn"
              :class="{ active: helpfulness === 'very_helpful' }"
              @click="setHelpfulness('very_helpful')"
            >
              很有帮助
            </button>
            <button
              class="helpfulness-btn"
              :class="{ active: helpfulness === 'somewhat_helpful' }"
              @click="setHelpfulness('somewhat_helpful')"
            >
              部分有用
            </button>
            <button
              class="helpfulness-btn"
              :class="{ active: helpfulness === 'not_helpful' }"
              @click="setHelpfulness('not_helpful')"
            >
              不太有用
            </button>
          </div>
        </div>

        <div class="action-bar">
          <button class="btn-confirm" @click="confirmAssociation">
            确认并继续 ({{ acceptedItems.length }}项已选)
          </button>
          <button class="btn-skip" @click="skipAssociation">
            跳过联想，直接生成
          </button>
        </div>
      </div>
    </div>
  </div>

  <div
    v-if="showRejectionDialog"
    class="rejection-dialog-overlay"
  >
    <div class="rejection-dialog">
      <h4>为什么删除这条建议?</h4>
      <div class="rejection-options">
        <button @click="submitRejection('irrelevant')">不相关</button>
        <button @click="submitRejection('already_planned')">已有计划</button>
        <button @click="submitRejection('out_of_scope')">超出范围</button>
        <button @click="submitRejection('other')">其他</button>
      </div>
      <button class="cancel-btn" @click="cancelRejection">取消删除</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  associationResult: {
    type: Object,
    default: () => ({
      skipped: true,
      skip_reason: '',
      items: [],
      classified_items: {},
      domain_matched: '',
      domains_matched: [],
      devil_review_items: [],
      elapsed_seconds: 0
    })
  }
})

const emit = defineEmits(['confirm', 'skip'])

const acceptedItems = ref([])
const removedItems = ref([])
const collapsedState = reactive({})
const helpfulness = ref('')
const showRejectionDialog = ref(false)
const pendingRemovalItem = ref(null)

const domainLabelMap = {
  banking: '金融/银行',
  ecommerce: '电商/商城',
  cms: '内容管理',
  saas: 'SaaS后台',
  social: '社交/聊天',
  dashboard: '数据大屏',
  education: '教育/学习',
  healthcare: '医疗健康',
  iot: '物联网',
  erp: 'ERP/进销存'
}

const sourceLabelMap = {
  domain_template: '领域模板',
  history_project: '历史项目',
  llm_association: 'AI联想',
  'llm_association:dual': '双模型联想',
  'llm_association:single': '单模型联想',
  'llm_association:fallback': 'AI联想',
  'domain_template:banking': '金融模板',
  'domain_template:ecommerce': '电商模板',
  'domain_template:cms': '内容模板',
  'domain_template:saas': 'SaaS模板',
  'domain_template:social': '社交模板',
  'domain_template:dashboard': '大屏模板',
  'domain_template:education': '教育模板',
  'domain_template:healthcare': '医疗模板',
  'domain_template:iot': '物联网模板',
  'domain_template:erp': 'ERP模板',
  'history_project:semantic': '语义匹配',
  'history_project:keyword': '关键词匹配',
}

const displayCategories = [
  { key: 'functional', label: '功能需求' },
  { key: 'architectural', label: '架构影响' },
  { key: 'risk', label: '潜在风险' },
  { key: 'decision', label: '关键决策' }
]

const classifiedItems = computed(() => props.associationResult.classified_items || {})

function getCategoryItems(categoryKey) {
  return classifiedItems.value[categoryKey] || { shown: [], collapsed: [] }
}

function getSourceClass(source) {
  if (!source) return 'unknown'
  if (source.startsWith('domain_template')) return 'domain_template'
  if (source.startsWith('history_project')) return 'history_project'
  if (source.startsWith('llm_association')) return 'llm_association'
  return source
}

function getSourceLabel(source) {
  return sourceLabelMap[source] || sourceLabelMap[getSourceClass(source)] || source
}

function isItemAccepted(item) {
  return acceptedItems.value.some(i => i.content === item.content && i.category === item.category)
}

function toggleItem(item) {
  const idx = acceptedItems.value.findIndex(i => i.content === item.content && i.category === item.category)
  if (idx >= 0) {
    pendingRemovalItem.value = item
    showRejectionDialog.value = true
  } else {
    acceptedItems.value.push(item)
  }
}

function submitRejection(reason) {
  const item = pendingRemovalItem.value
  if (item) {
    const idx = acceptedItems.value.findIndex(i => i.content === item.content && i.category === item.category)
    if (idx >= 0) {
      acceptedItems.value.splice(idx, 1)
    }
    removedItems.value.push({ ...item, rejection_reason: reason })
  }
  showRejectionDialog.value = false
  pendingRemovalItem.value = null
}

function cancelRejection() {
  showRejectionDialog.value = false
  pendingRemovalItem.value = null
}

function toggleCollapsed(categoryKey) {
  collapsedState[categoryKey] = !collapsedState[categoryKey]
}

function setHelpfulness(level) {
  helpfulness.value = level
}

async function confirmAssociation() {
  const allItems = props.associationResult.items || []
  const confirmed = acceptedItems.value

  const removed = allItems.filter(item =>
    !confirmed.some(c => c.content === item.content && c.category === item.category) &&
    !removedItems.value.some(r => r.content === item.content && r.category === item.category)
  )
  const allRemoved = [...removedItems.value, ...removed.map(item => ({ ...item, rejection_reason: 'no_reason' }))]

  try {
    const { createBaseClient } = await import('@/utils/api/base')
    const client = createBaseClient()
    await client.post('/api/v1/agent/requirement-association/confirm', {
      requirement: props.associationResult.enhanced_requirement || '',
      confirmed_items: confirmed,
      removed_items: allRemoved,
      modified_items: []
    })

    if (helpfulness.value) {
      const sessionId = new Date().toISOString().replace(/[-:]/g, '').slice(0, 15)
      await client.post('/api/v1/agent/requirement-association/helpfulness', {
        session_id: sessionId,
        requirement: props.associationResult.enhanced_requirement || '',
        helpfulness: helpfulness.value
      })
    }
  } catch (e) {
    console.warn('确认结果保存失败:', e)
  }

  emit('confirm', {
    confirmed_items: confirmed,
    removed_items: allRemoved,
    enhanced_requirement: props.associationResult.enhanced_requirement
  })
}

function skipAssociation() {
  emit('skip')
}
</script>

<style scoped>
.requirement-association-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.requirement-association-panel {
  background: var(--bg-primary);
  border-radius: 12px;
  max-width: 640px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
  padding: 24px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.panel-header h3 {
  font-size: 18px;
  margin: 0;
}

.domain-badge {
  background: var(--color-primary-50);
  color: var(--primary);
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 13px;
}

.close-btn {
  margin-left: auto;
  background: none;
  border: 1px solid var(--border-color);
  padding: 4px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.stats-row {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--text-secondary);
}

.devil-review-section {
  margin-bottom: 16px;
  padding: 12px;
  background: var(--bg-primary)1f0;
  border-radius: 6px;
  border: 1px solid var(--danger);
}

.devil-review-item {
  padding: 6px 0;
  font-size: 13px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
}

.devil-target {
  color: var(--danger);
  font-weight: 500;
}

.devil-challenge {
  color: var(--text-primary);
  flex: 1;
}

.devil-severity {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
}

.severity-high { background: #fff1f0; color: var(--danger); }
.severity-medium { background: #fff7e6; color: var(--warning); }
.severity-low { background: var(--color-success-50, #f6ffed); color: var(--success); }

.devil-suggestion {
  color: var(--primary);
  font-size: 12px;
}

.category-group {
  margin-bottom: 16px;
}

.category-group h4 {
  font-size: 15px;
  margin: 0 0 8px 0;
  padding: 4px 0;
  border-bottom: 1px solid var(--border-color);
}

.category-functional { color: var(--primary); }
.category-architectural { color: var(--warning); }
.category-risk { color: var(--danger); }
.category-decision { color: var(--color-primary-700); }

.item-count {
  font-size: 12px;
  color: var(--text-tertiary);
}

.association-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  margin: 4px 0;
  border-radius: 4px;
  cursor: pointer;
}

.association-item.shown {
  background: var(--bg-secondary);
}

.association-item.collapsed {
  background: var(--bg-secondary);
  opacity: 0.85;
}

.item-content {
  flex: 1;
  font-size: 14px;
}

.item-source {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 3px;
}

.source-domain_template { background: var(--color-primary-50); color: var(--primary); }
.source-history_project { background: var(--color-success-50, #f6ffed); color: var(--success); }
.source-llm_association { background: #fff7e6; color: var(--warning); }
.source-unknown { background: var(--bg-tertiary); color: var(--text-tertiary); }

.dual-badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
}

.dual-badge.both {
  background: var(--color-success-50, #f6ffed);
  color: var(--success);
}

.dual-badge.single {
  background: var(--bg-primary)7e6;
  color: var(--warning);
}

.item-confidence {
  font-size: 11px;
  color: var(--success);
  font-weight: 500;
}

.item-confidence.low {
  color: var(--warning);
}

.expand-btn {
  background: none;
  border: none;
  color: var(--primary);
  cursor: pointer;
  font-size: 13px;
  padding: 4px 0;
}

.collapsed-items {
  margin-top: 8px;
}

.helpfulness-section {
  margin-top: 16px;
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
}

.helpfulness-question {
  font-size: 14px;
  color: var(--text-primary);
  margin: 0 0 8px 0;
}

.helpfulness-options {
  display: flex;
  gap: 8px;
}

.helpfulness-btn {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  padding: 6px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.helpfulness-btn.active {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
}

.action-bar {
  display: flex;
  gap: 12px;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.btn-confirm {
  background: var(--primary);
  color: #fff;
  border: none;
  padding: 8px 24px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.btn-skip {
  background: none;
  border: 1px solid var(--border-color);
  padding: 8px 24px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.skip-info {
  text-align: center;
  padding: 32px 0;
}

.skip-info p {
  color: var(--text-secondary);
  margin-bottom: 16px;
}

.rejection-dialog-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: 1100;
  display: flex;
  align-items: center;
  justify-content: center;
}

.rejection-dialog {
  background: var(--bg-primary);
  border-radius: 8px;
  padding: 24px;
  max-width: 320px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

.rejection-dialog h4 {
  margin: 0 0 16px 0;
  font-size: 16px;
}

.rejection-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rejection-options button {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  text-align: left;
}

.rejection-options button:hover {
  background: var(--color-primary-50);
  border-color: var(--primary);
}

.cancel-btn {
  margin-top: 12px;
  background: none;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  font-size: 13px;
}
</style>