<template>
  <div v-if="files.length" class="message-attachments" aria-label="消息附件">
    <template v-for="file in documentFiles" :key="'doc-' + (file.id || file.name)">
      <a
        v-if="originalUrl(file)"
        :href="originalUrl(file)"
        target="_blank"
        rel="noopener noreferrer"
        class="attachment-document"
        :aria-label="`查看附件：${file.name || '文件'}`"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
        <span class="attachment-document-name">{{ file.name || '文件' }}</span>
      </a>
      <span v-else class="attachment-document" :aria-label="`附件：${file.name || '文件'}`">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
        <span class="attachment-document-name">{{ file.name || '文件' }}</span>
      </span>
    </template>
    <figure v-for="(file, index) in imageFiles" :key="file.id || file.name || index" class="attachment-image">
      <a
        v-if="originalUrl(file)"
        class="attachment-link"
        :href="originalUrl(file)"
        target="_blank"
        rel="noopener noreferrer"
        :aria-label="`查看原图：${file.name || '图片附件'}`"
      >
        <img
          v-if="thumbnailUrl(file) && !failedImages.has(fileKey(file, index))"
          :src="thumbnailUrl(file)"
          :alt="file.name || '图片附件'"
          class="attachment-img"
          width="200"
          height="150"
          loading="lazy"
          decoding="async"
          @error="markFailed(file, index)"
        />
        <span v-else class="attachment-fallback">图片预览不可用</span>
      </a>
      <img
        v-else-if="thumbnailUrl(file) && !failedImages.has(fileKey(file, index))"
        :src="thumbnailUrl(file)"
        :alt="file.name || '图片附件'"
        class="attachment-img"
        width="200"
        height="150"
        loading="lazy"
        decoding="async"
        @error="markFailed(file, index)"
      />
      <span v-else class="attachment-fallback">图片预览不可用</span>
      <figcaption class="attachment-name">{{ file.name || '图片附件' }}</figcaption>
    </figure>
  </div>
</template>

<script setup>
import { computed, reactive } from 'vue'

const props = defineProps({
  files: { type: Array, default: () => [] }
})

// 历史消息只存图片且没有 category，保留其为图片；显式的文档/代码才渲染成文件条目。
const isDocument = file => file.category === 'document' || file.category === 'code'
const imageFiles = computed(() => props.files.filter(file => !isDocument(file)))
const documentFiles = computed(() => props.files.filter(isDocument))

const failedImages = reactive(new Set())
const fileKey = (file, index) => file.id ?? file.name ?? index
const safeUrl = value => {
  if (typeof value !== 'string') return ''
  return /^(https?:|blob:|data:image\/|\/(?!\/))/.test(value) ? value : ''
}
const thumbnailUrl = file => safeUrl(file.thumbnail || file.preview || file.localUrl)
const originalUrl = file => safeUrl(file.originalUrl || file.downloadUrl || file.localUrl)
const markFailed = (file, index) => failedImages.add(fileKey(file, index))
</script>

<style scoped>
.message-attachments { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.attachment-document { display: inline-flex; align-items: center; gap: 6px; max-width: 240px; padding: 6px 10px; color: var(--text-secondary); font-size: 12px; text-decoration: none; background: var(--surface-subtle); border: 1px solid var(--control-border); border-radius: 8px; }
.attachment-document[href]:hover { border-color: var(--accent-primary); }
.attachment-document svg { flex: none; width: 14px; height: 14px; opacity: 0.8; }
.attachment-document-name { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.attachment-image { position: relative; max-width: 200px; margin: 0; overflow: hidden; border: 1px solid var(--control-border); border-radius: 8px; }
.attachment-link { display: block; color: inherit; }
.attachment-img { display: block; width: 200px; height: 150px; object-fit: cover; }
.attachment-fallback { display: grid; width: 200px; height: 150px; place-items: center; color: var(--content-muted); font-size: 12px; background: var(--surface-subtle); }
.attachment-name { display: block; padding: 4px 8px; overflow: hidden; color: var(--content-muted); font-size: 11px; white-space: nowrap; text-overflow: ellipsis; background: var(--surface-subtle); }
</style>
