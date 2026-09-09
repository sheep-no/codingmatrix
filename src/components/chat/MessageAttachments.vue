<template>
  <div v-if="files.length" class="message-attachments" aria-label="消息附件">
    <figure v-for="(file, index) in files" :key="file.id || file.name || index" class="attachment-image">
      <a
        v-if="originalUrl(file)"
        class="attachment-link"
        :href="originalUrl(file)"
        target="_blank"
        rel="noopener noreferrer"
        :aria-label="`查看原图: ${file.name || '图片附件'}`"
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
import { reactive } from 'vue'

defineProps({
  files: { type: Array, default: () => [] }
})

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
.attachment-image { position: relative; max-width: 200px; margin: 0; overflow: hidden; border: 1px solid var(--control-border); border-radius: 8px; }
.attachment-link { display: block; color: inherit; }
.attachment-img { display: block; width: 200px; height: 150px; object-fit: cover; }
.attachment-fallback { display: grid; width: 200px; height: 150px; place-items: center; color: var(--content-muted); font-size: 12px; background: var(--surface-subtle); }
.attachment-name { display: block; padding: 4px 8px; overflow: hidden; color: var(--content-muted); font-size: 11px; white-space: nowrap; text-overflow: ellipsis; background: var(--surface-subtle); }
</style>
