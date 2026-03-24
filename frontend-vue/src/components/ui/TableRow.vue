<template>
  <tr
    :class="[
      'darwin-table-row',
      hoverable && 'darwin-table-row-hoverable',
      selected && 'darwin-table-row-selected'
    ]"
    @click="$emit('click', $event)"
  >
    <slot />
  </tr>
</template>

<style scoped>
.darwin-table-row {
  transition: all 0.2s ease;
}

.darwin-table-row-hoverable {
  cursor: pointer;
}

.darwin-table-row-hoverable:hover {
  background: #f8fafc;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.darwin-table-row-selected {
  background: #eff6ff;
  border-left: 3px solid #3b82f6;
}
</style>

<script setup>
defineProps({
  hoverable: {
    type: Boolean,
    default: false,
  },
  selected: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['click'])
</script>

