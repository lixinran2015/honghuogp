<template>
  <div class="bg-dark-700 rounded-lg border border-border p-3 flex flex-wrap items-center gap-3">
    <!-- 搜索输入 -->
    <div v-if="showSearch" class="flex items-center gap-2">
      <span class="text-2xs text-dark-400 uppercase">搜索</span>
      <div class="relative">
        <MagnifyingGlassIcon class="w-4 h-4 text-dark-400 absolute left-2 top-1/2 -translate-y-1/2" />
        <input
          :value="searchValue"
          type="text"
          class="pl-8 pr-3 py-1.5 bg-dark-800 border border-border rounded-md text-sm text-white placeholder-dark-400 focus:outline-none focus:border-primary-700 transition-colors w-48"
          :placeholder="searchPlaceholder"
          @input="$emit('update:searchValue', $event.target.value)"
        />
      </div>
    </div>

    <!-- 下拉筛选 -->
    <div
      v-for="filter in filters"
      :key="filter.key"
      class="flex items-center gap-2"
    >
      <span class="text-2xs text-dark-400 uppercase">{{ filter.label }}</span>
      <select
        :value="modelValue[filter.key]"
        class="px-2 py-1.5 bg-dark-800 border border-border rounded-md text-sm text-white focus:outline-none focus:border-primary-700 transition-colors cursor-pointer"
        @change="$emit('update:modelValue', { ...modelValue, [filter.key]: $event.target.value })"
      >
        <option
          v-for="option in filter.options"
          :key="option.value"
          :value="option.value"
        >
          {{ option.label }}
        </option>
      </select>
    </div>

    <!-- 复选框 -->
    <div
      v-for="checkbox in checkboxes"
      :key="checkbox.key"
      class="flex items-center gap-2"
    >
      <label class="inline-flex items-center gap-1.5 text-sm text-dark-300 cursor-pointer hover:text-white transition-colors">
        <input
          :checked="modelValue[checkbox.key]"
          type="checkbox"
          class="w-3.5 h-3.5 rounded border-border bg-dark-800 text-cta focus:ring-cta focus:ring-offset-0"
          @change="$emit('update:modelValue', { ...modelValue, [checkbox.key]: $event.target.checked })"
        />
        <span>{{ checkbox.label }}</span>
      </label>
    </div>

    <!-- 操作按钮 -->
    <div v-if="showActions" class="ml-auto flex items-center gap-2">
      <button
        v-if="showReset"
        class="px-3 py-1.5 text-sm text-dark-400 hover:text-white transition-colors"
        @click="$emit('reset')"
      >
        重置
      </button>
      <button
        v-if="showRefresh"
        class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-cta hover:bg-cta-hover rounded-md transition-colors"
        :disabled="refreshing"
        @click="$emit('refresh')"
      >
        <ArrowPathIcon class="w-4 h-4" :class="{ 'animate-spin': refreshing }" />
        {{ refreshing ? '刷新中' : '刷新' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { MagnifyingGlassIcon, ArrowPathIcon } from '@heroicons/vue/24/outline'

defineProps({
  modelValue: {
    type: Object,
    default: () => ({})
  },
  searchValue: {
    type: String,
    default: ''
  },
  showSearch: {
    type: Boolean,
    default: true
  },
  searchPlaceholder: {
    type: String,
    default: '搜索...'
  },
  filters: {
    type: Array,
    default: () => []
  },
  checkboxes: {
    type: Array,
    default: () => []
  },
  showActions: {
    type: Boolean,
    default: true
  },
  showReset: {
    type: Boolean,
    default: true
  },
  showRefresh: {
    type: Boolean,
    default: true
  },
  refreshing: {
    type: Boolean,
    default: false
  }
})

defineEmits(['update:modelValue', 'update:searchValue', 'reset', 'refresh'])
</script>
