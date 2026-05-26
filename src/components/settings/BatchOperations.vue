<template>
  <div class="batch-operations">
    <el-card class="mb-4">
      <template #header>
        <div class="card-header">
          <span>批量导入 API Key</span>
          <el-button type="primary" size="small" @click="downloadTemplate">
            下载模板
          </el-button>
        </div>
      </template>
      
      <el-form :model="importForm" label-width="100px">
        <el-form-item label="导入格式">
          <el-radio-group v-model="importFormat">
            <el-radio label="json">JSON</el-radio>
            <el-radio label="csv">CSV</el-radio>
          </el-radio-group>
        </el-form-item>
        
        <el-form-item label="数据">
          <el-input
            v-if="importFormat === 'json'"
            v-model="importData"
            type="textarea"
            :rows="10"
            placeholder='[{"provider":"siliconflow","encrypted_key":"xxx","ttl":"24h","remark":"Key 1"}]'
          />
          <el-input
            v-else
            v-model="importData"
            type="textarea"
            :rows="10"
            placeholder="provider,encrypted_key,ttl,remark&#10;siliconflow,xxx,24h,Key 1"
          />
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" :loading="importing" @click="handleImport">
            开始导入
          </el-button>
          <el-button @click="resetImport">重置</el-button>
        </el-form-item>
      </el-form>
      
      <div v-if="importResults.length > 0" class="import-results">
        <h4>导入结果</h4>
        <el-alert
          type="success"
          :title="`成功：${importSuccessCount} 个`"
          show-icon
          class="mb-2"
        />
        <el-alert
          v-if="importFailedCount > 0"
          type="error"
          :title="`失败：${importFailedCount} 个`"
          show-icon
          class="mb-2"
        />
        
        <el-collapse>
          <el-collapse-item title="查看详情" name="1">
            <div v-for="(result, index) in importResults" :key="index" class="result-item">
              <el-tag :type="result.success ? 'success' : 'danger'" size="small">
                {{ result.success ? '成功' : '失败' }}
              </el-tag>
              <span class="ml-2">{{ result.provider }}</span>
              <span class="ml-2 text-sm text-gray">{{ result.message || result.error }}</span>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-card>
    
    <el-card>
      <template #header>
        <div class="card-header">
          <span>批量导出 API Key</span>
        </div>
      </template>
      
      <el-form :inline="true">
        <el-form-item label="导出格式">
          <el-select v-model="exportFormat" style="width: 120px">
            <el-option label="JSON" value="json" />
            <el-option label="CSV" value="csv" />
          </el-select>
        </el-form-item>
        
        <el-form-item>
          <el-button type="success" :loading="exporting" @click="handleExport">
            导出数据
          </el-button>
        </el-form-item>
      </el-form>
      
      <el-alert
        v-if="exportCount > 0"
        type="info"
        :title="`共导出 ${exportCount} 个 Key 元数据`"
        show-icon
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { batchImport, batchExport } from '@/api/apikey'
import { useApiKeyStore } from '@/stores/apikey'

const apikeyStore = useApiKeyStore()

const importFormat = ref('json')
const importData = ref('')
const importing = ref(false)
const importResults = ref([])
const importSuccessCount = ref(0)
const importFailedCount = ref(0)

const exportFormat = ref('json')
const exporting = ref(false)
const exportCount = ref(0)

// 下载模板
const downloadTemplate = () => {
  if (importFormat.value === 'json') {
    const template = [
      {
        provider: 'siliconflow',
        encrypted_key: 'RSA 加密后的 Key (Base64)',
        ttl: '24h',
        remark: '备注信息'
      }
    ]
    const blob = new Blob([JSON.stringify(template, null, 2)], { type: 'application/json' })
    downloadFile(blob, 'apikey_import_template.json')
  } else {
    const template = 'provider,encrypted_key,ttl,remark\nsiliconflow,RSA 加密后的 Key,24h，备注信息'
    const blob = new Blob([template], { type: 'text/csv' })
    downloadFile(blob, 'apikey_import_template.csv')
  }
}

const downloadFile = (blob, filename) => {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// 重置导入
const resetImport = () => {
  importData.value = ''
  importResults.value = []
  importSuccessCount.value = 0
  importFailedCount.value = 0
}

// 执行导入
const handleImport = async () => {
  if (!importData.value.trim()) {
    ElMessage.warning('请输入导入数据')
    return
  }
  
  let keys = []
  try {
    if (importFormat.value === 'json') {
      keys = JSON.parse(importData.value)
      if (!Array.isArray(keys)) {
        throw new Error('JSON 格式必须是数组')
      }
    } else {
      // CSV 解析
      const lines = importData.value.trim().split('\n')
      const headers = lines[0].split(',')
      
      for (let i = 1; i < lines.length; i++) {
        const values = lines[i].split(',')
        if (values.length >= 4) {
          keys.push({
            provider: values[0],
            encrypted_key: values[1],
            ttl: values[2],
            remark: values[3]
          })
        }
      }
    }
  } catch (e) {
    ElMessage.error(`数据格式错误：${e.message}`)
    return
  }
  
  if (keys.length === 0) {
    ElMessage.warning('没有有效的 Key 数据')
    return
  }
  
  importing.value = true
  try {
    const response = await batchImport({ keys })
    
    importResults.value = response.results
    importSuccessCount.value = response.success_count
    importFailedCount.value = response.failed_count
    
    ElMessage.success(`导入完成：成功${response.success_count}个，失败${response.failed_count}个`)
    
    // 刷新 Key 列表
    await apikeyStore.fetchKeys()
    
    importData.value = ''
  } catch (error) {
    ElMessage.error(`导入失败：${error.message}`)
  } finally {
    importing.value = false
  }
}

// 执行导出
const handleExport = async () => {
  exporting.value = true
  try {
    const response = await batchExport(exportFormat.value)
    
    const blob = new Blob([response.data], {
      type: exportFormat.value === 'json' ? 'application/json' : 'text/csv'
    })
    
    const filename = exportFormat.value === 'json'
      ? 'apikeys_export.json'
      : 'apikeys_export.csv'
    
    downloadFile(blob, filename)
    exportCount.value = response.count
    
    ElMessage.success(`导出成功：共${response.count}个 Key`)
  } catch (error) {
    ElMessage.error(`导出失败：${error.message}`)
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.batch-operations {
  max-width: 1200px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.mb-4 {
  margin-bottom: 16px;
}

.mb-2 {
  margin-bottom: 8px;
}

.ml-2 {
  margin-left: 8px;
}

.text-sm {
  font-size: 12px;
}

.text-gray {
  color: #666;
}

.import-results {
  margin-top: 16px;
}

.result-item {
  display: flex;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #eee;
}

.result-item:last-child {
  border-bottom: none;
}
</style>
