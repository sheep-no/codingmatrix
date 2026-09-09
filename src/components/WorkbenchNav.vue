<template>
  <nav
    class="workbench-nav"
    :class="{ 'workbench-nav-collapsed': collapsed }"
    aria-label="工作台主导航"
  >
    <RouterLink
      v-for="item in navigationItems"
      :key="item.name"
      :to="item.to"
      class="workbench-nav-link"
      :aria-label="item.label"
      :title="item.label"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path :d="item.icon" />
      </svg>
      <span class="workbench-nav-label">{{ item.label }}</span>
    </RouterLink>
  </nav>
</template>

<script setup>
defineProps({
  collapsed: { type: Boolean, default: false }
})

const navigationItems = [
  { name: 'conversations', label: '会话', to: '/', icon: 'M4 5h16v11H7l-3 3V5z' },
  { name: 'projects', label: '项目', to: '/agent', icon: 'M3 6h7l2 2h9v11H3V6z' },
  { name: 'capabilities', label: '能力', to: '/capabilities', icon: 'M8 3h8v4H8V3zM4 10h6v4H4v-4zM14 10h6v4h-6v-4zM8 17h8v4H8v-4zM12 7v3M7 14v3h10v-3' },
  { name: 'documentation', label: '文档', to: '/docs', icon: 'M5 3h10l4 4v14H5V3zM15 3v5h4M8 12h8M8 16h8' },
  { name: 'settings', label: '设置', to: '/settings', icon: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM4 12h2M18 12h2M12 4v2M12 18v2M6.3 6.3l1.4 1.4M16.3 16.3l1.4 1.4M17.7 6.3l-1.4 1.4M7.7 16.3l-1.4 1.4' }
]
</script>

<style scoped>
.workbench-nav {
  display: grid;
  gap: var(--spacing-1);
  padding: var(--spacing-2);
  border: 1px solid var(--control-border);
  border-radius: var(--radius-lg);
  background: var(--surface-subtle);
}

.workbench-nav-link {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  min-width: var(--control-min-size);
  min-height: var(--control-min-size);
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-md);
  color: var(--content-secondary);
  font-size: var(--text-sm);
  font-weight: 600;
  text-decoration: none;
  transition:
    color var(--motion-fast),
    background var(--motion-fast);
}

.workbench-nav-link:hover {
  color: var(--content-primary);
  background: var(--surface-raised);
}

.workbench-nav-link.router-link-active {
  color: var(--accent-primary);
  background: color-mix(in srgb, var(--accent-primary) 12%, transparent);
}

.workbench-nav-link:focus-visible {
  outline: 3px solid color-mix(in srgb, var(--control-border-focus) 45%, transparent);
  outline-offset: 2px;
}

.workbench-nav-link svg {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
}

.workbench-nav-collapsed {
  padding: var(--spacing-1);
  border-color: transparent;
  background: transparent;
}

.workbench-nav-collapsed .workbench-nav-link {
  justify-content: center;
  padding: var(--spacing-2);
}

.workbench-nav-collapsed .workbench-nav-label {
  display: none;
}
</style>
