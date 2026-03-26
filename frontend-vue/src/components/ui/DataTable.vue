<template>
  <div class="bg-dark-700 rounded-lg border border-border overflow-hidden">
    <!-- 表头 -->
    <div class="overflow-x-auto">
      <table class="w-full">
        <thead>
          <tr class="bg-dark-800 border-b border-border">
            <th
              v-for="column in columns"
              :key="column.key"
              :class="[
                'px-3 py-2.5 text-left text-2xs font-semibold text-dark-400 uppercase tracking-wider',
                column.sortable && 'cursor-pointer hover:text-white select-none',
                column.align === 'center' && 'text-center',
                column.align === 'right' && 'text-right'
              ]"
              @click="column.sortable && handleSort(column.key)"
            >
              <div class="flex items-center gap-1" :class="column.align === 'right' ? 'justify-end' : column.align === 'center' ? 'justify-center' : ''">
                {{ column.title }}
                <template v-if="column.sortable">
                  <ChevronUpIcon v-if="sortKey === column.key && sortOrder === 'asc'" class="w-3 h-3" />
                  <ChevronDownIcon v-else-if="sortKey === column.key && sortOrder === 'desc'" class="w-3 h-3" />
                  <div v-else class="w-3 h-3 opacity-30">
                    <ChevronUpIcon class="w-3 h-3 -mb-1" />
                    <ChevronDownIcon class="w-3 h-3" />
                  </div>
                </template>
              </div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, index) in sortedData"
            :key="rowKey ? row[rowKey] : index"
            :class="[
              'border-b border-border-light last:border-b-0 transition-colors duration-150',
              rowClass(row),
              clickable && 'cursor-pointer hover:bg-dark-600/50'
            ]"
            @click="clickable && $emit('row-click', row)"
          >
            <td
              v-for="column in columns"
              :key="column.key"
              :class="[
                'px-3 py-2.5 text-sm',
                column.align === 'center' && 'text-center',
                column.align === 'right' && 'text-right'
              ]"
            >
              <slot
                :name="`cell-${column.key}`"
                :row="row"
                :value="getCellValue(row, column)"
                :column="column"
              >
                <span :class="getCellClass(row, column)">
                  {{ formatCellValue(getCellValue(row, column), column) }}
                </span>
              </slot>
            </td>
          </tr>
          <tr v-if="sortedData.length === 0">
            <td :colspan="columns.length" class="px-3 py-8 text-center text-dark-400">
              {{ emptyText }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 分页 -->
    <div v-if="showPagination && total > pageSize" class="flex items-center justify-between px-3 py-2 border-t border-border bg-dark-800">
      <div class="text-2xs text-dark-400">
        共 {{ total }} 条
      </div>
      <div class="flex items-center gap-1">
        <button
          :disabled="currentPage <= 1"
          class="p-1 rounded text-dark-400 hover:text-white hover:bg-dark-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          @click="$emit('update:currentPage', currentPage - 1)"
        >
          <ChevronLeftIcon class="w-4 h-4" />
        </button>
        <span class="text-sm text-dark-300 px-2">
          {{ currentPage }} / {{ Math.ceil(total / pageSize) }}
        </span>
        <button
          :disabled="currentPage >= Math.ceil(total / pageSize)"
          class="p-1 rounded text-dark-400 hover:text-white hover:bg-dark-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          @click="$emit('update:currentPage', currentPage + 1)"
        >
          <ChevronRightIcon class="w-4 h-4" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import {
  ChevronUpIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon
} from '@heroicons/vue/24/outline'

const props = defineProps({
  data: {
    type: Array,
    default: () => []
  },
  columns: {
    type: Array,
    required: true
  },
  rowKey: {
    type: String,
    default: ''
  },
  clickable: {
    type: Boolean,
    default: false
  },
  rowClass: {
    type: Function,
    default: () => ''
  },
  emptyText: {
    type: String,
    default: '暂无数据'
  },
  showPagination: {
    type: Boolean,
    default: false
  },
  currentPage: {
    type: Number,
    default: 1
  },
  pageSize: {
    type: Number,
    default: 20
  },
  total: {
    type: Number,
    default: 0
  }
})

defineEmits(['row-click', 'update:currentPage'])

const sortKey = ref('')
const sortOrder = ref('desc')

const handleSort = (key) => {
  if (sortKey.value === key) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortOrder.value = 'desc'
  }
}

const sortedData = computed(() => {
  let result = [...props.data]

  if (sortKey.value) {
    result.sort((a, b) => {
      const aVal = a[sortKey.value]
      const bVal = b[sortKey.value]

      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortOrder.value === 'asc' ? aVal - bVal : bVal - aVal
      }

      const aStr = String(aVal || '').toLowerCase()
      const bStr = String(bVal || '').toLowerCase()

      if (sortOrder.value === 'asc') {
        return aStr.localeCompare(bStr)
      }
      return bStr.localeCompare(aStr)
    })
  }

  return result
})

const getCellValue = (row, column) => {
  if (column.formatter) {
    return column.formatter(row)
  }
  return row[column.key]
}

const formatCellValue = (value, column) => {
  if (value === null || value === undefined) return '-'

  if (column.type === 'number' && typeof value === 'number') {
    return value.toFixed(column.decimals || 2)
  }

  if (column.type === 'percent' && typeof value === 'number') {
    return (value * 100).toFixed(column.decimals || 2) + '%'
  }

  if (column.type === 'price' && typeof value === 'number') {
    return value.toFixed(2)
  }

  return value
}

const getCellClass = (row, column) => {
  const classes = []

  if (column.type === 'number' || column.type === 'price' || column.type === 'percent') {
    classes.push('font-mono')
  }

  if (column.color) {
    const color = column.color(row)
    if (color) classes.push(color)
  }

  return classes.join(' ')
}
</script>
