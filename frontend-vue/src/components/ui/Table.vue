<template>
  <Card padding="none" :className="className">
    <div class="overflow-x-auto">
      <table class="w-full darwin-stock-table">
        <thead v-if="headers" class="darwin-table-header">
          <tr>
            <th
              v-for="(header, index) in headers"
              :key="index"
              class="darwin-table-th"
            >
              {{ header }}
            </th>
          </tr>
        </thead>
        <tbody class="darwin-table-body">
          <slot />
        </tbody>
      </table>
    </div>
  </Card>
</template>

<style scoped>
.darwin-stock-table {
  border-collapse: separate;
  border-spacing: 0;
}

.darwin-table-header {
  background: linear-gradient(to bottom, #f8fafc, #f1f5f9);
  border-bottom: 2px solid #e2e8f0;
}

.darwin-table-th {
  padding: 14px 16px;
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  text-transform: none;
  letter-spacing: 0.3px;
  white-space: nowrap;
  border-bottom: 2px solid #e2e8f0;
  position: sticky;
  top: 0;
  z-index: 10;
}

.darwin-table-th:first-child {
  padding-left: 24px;
}

.darwin-table-th:last-child {
  padding-right: 24px;
}

.darwin-table-body {
  background: white;
}

.darwin-table-body tr {
  border-bottom: 1px solid #f1f5f9;
  transition: all 0.2s ease;
}

.darwin-table-body tr:hover {
  background: #f8fafc;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.darwin-table-body tr:last-child {
  border-bottom: none;
}
</style>

<script setup>
import Card from './Card.vue'

defineProps({
  headers: {
    type: Array,
    default: null,
  },
  className: {
    type: String,
    default: '',
  },
})
</script>

