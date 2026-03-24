<template>
  <td :class="['darwin-table-td', alignClass]">
    <slot />
  </td>
</template>

<style scoped>
.darwin-table-td {
  padding: 16px;
  white-space: nowrap;
  font-size: 13px;
  color: #1e293b;
  border-bottom: 1px solid #f1f5f9;
}

.darwin-table-td:first-child {
  padding-left: 24px;
  font-weight: 500;
  color: #64748b;
}

.darwin-table-td:last-child {
  padding-right: 24px;
}
</style>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  align: {
    type: String,
    default: 'left', // left, center, right
    validator: (v) => ['left', 'center', 'right'].includes(v),
  },
})

const alignClass = computed(() => {
  const aligns = {
    left: 'text-left',
    center: 'text-center',
    right: 'text-right',
  }
  return aligns[props.align]
})
</script>

