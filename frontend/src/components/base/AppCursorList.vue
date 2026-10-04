<script setup lang="ts">
import AppButton from './AppButton.vue'
import AppFeedback from './AppFeedback.vue'

// Presentation only: callers own the query, cursor, rows, labels, and recovery requests.
defineProps<{
  isPending: boolean
  hasData: boolean
  isError: boolean
  isFetching: boolean
  isFetchingNextPage: boolean
  isNextPageError: boolean
  hasNextPage: boolean
  loadingLabel: string
  errorLabel: string
  retryLabel: string
  moreLabel: string
  stateClass?: string
  errorClass?: string
  feedbackClass?: string
  retryClass?: string
  moreClass?: string
}>()
defineEmits<{ retry: []; next: [] }>()
</script>

<template>
  <AppFeedback v-if="isPending" :class="['app-card', stateClass]" announcement="polite">
    {{ loadingLabel }}
  </AppFeedback>
  <AppFeedback
    v-else-if="isError && !hasData"
    :class="['app-card', errorClass]"
    announcement="assertive"
    tone="critical"
  >
    {{ errorLabel }}
    <template #actions>
      <AppButton :class="retryClass" variant="ghost" :disabled="isFetching" @click="$emit('retry')">
        {{ retryLabel }}
      </AppButton>
    </template>
  </AppFeedback>
  <template v-else>
    <slot />
    <AppFeedback
      v-if="isError"
      :class="['app-card', 'app-cursor-list-feedback', feedbackClass]"
      announcement="assertive"
      tone="critical"
    >
      {{ errorLabel }}
      <template v-if="!isNextPageError" #actions>
        <AppButton
          :class="retryClass"
          variant="ghost"
          :disabled="isFetching"
          @click="$emit('retry')"
        >
          {{ retryLabel }}
        </AppButton>
      </template>
    </AppFeedback>
    <AppFeedback
      v-if="isFetchingNextPage"
      :class="['app-card', 'app-cursor-list-feedback', feedbackClass]"
      announcement="polite"
    >
      {{ loadingLabel }}
    </AppFeedback>
    <AppButton
      v-if="hasNextPage"
      :class="moreClass"
      variant="ghost"
      :disabled="isFetching"
      @click="$emit('next')"
    >
      {{ isNextPageError ? retryLabel : moreLabel }}
    </AppButton>
  </template>
</template>

<style scoped>
.app-cursor-list-feedback {
  margin-block-end: var(--space-4);
}
</style>
