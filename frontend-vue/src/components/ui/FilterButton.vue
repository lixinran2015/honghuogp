<template>
  <button
    :class="[
      'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
      active
        ? 'bg-primary-500 text-white'
        : 'bg-white text-gray-700 border border-gray-200 hover:bg-gray-50'
    ]"
    @click="$emit('click', $event)"
  >
    {{ label }}
  </button>
</template>

<script setup>
defineProps({
  label: {
    type: String,
    required: true,
  },
  active: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['click'])
</script>

