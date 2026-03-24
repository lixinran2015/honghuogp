<template>
  <button
    @click="$emit('click', $event)"
    :class="[
      'px-4 py-2 rounded-lg text-sm font-medium transition-colors relative flex items-center gap-2',
      active
        ? 'text-primary-700 bg-primary-50'
        : 'text-gray-700 hover:text-gray-900 hover:bg-gray-50'
    ]"
  >
    <component
      :is="iconComponent"
      :class="[
        'w-5 h-5 flex-shrink-0',
        active ? 'text-primary-600' : 'text-gray-500'
      ]"
    />
    <span>{{ item.label }}</span>
    <span
      v-if="active"
      class="absolute bottom-0 left-0 right-0 h-0.5 bg-primary-500 rounded-t-full"
    />
  </button>
</template>

<script setup>
import { computed } from 'vue'
import {
  SparklesIcon,
  FireIcon,
  StarIcon,
  CogIcon,
  BriefcaseIcon,
  ChartBarIcon,
} from '@heroicons/vue/24/outline'

const props = defineProps({
  item: {
    type: Object,
    required: true,
  },
  active: {
    type: Boolean,
    default: false,
  },
})

const iconMap = {
  SparklesIcon,
  FireIcon,
  StarIcon,
  CogIcon,
  BriefcaseIcon,
  ChartBarIcon,
}

const iconComponent = computed(() => iconMap[props.item.icon] || SparklesIcon)

defineEmits(['click'])
</script>

