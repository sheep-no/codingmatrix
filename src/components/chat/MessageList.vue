<template>
  <div class="message-list">
    <MessageItem
      v-for="(message, index) in messages"
      :key="message.id || `${startIndex + index}`"
      :message="message"
      :item-key="message.id ?? `message-${startIndex + index}`"
      @resize="$emit('item-resize', $event)"
    >
      <slot :message="message" :index="startIndex + index" />
    </MessageItem>
  </div>
</template>

<script setup>
import MessageItem from './MessageItem.vue'

defineEmits(['item-resize'])

defineProps({
  messages: { type: Array, default: () => [] },
  startIndex: { type: Number, default: 0 }
})
</script>

<style scoped>
.message-list { display: contents; }
</style>
