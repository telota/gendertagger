<script setup lang="ts">
// The route's own component. A separate component (rather than a route meta flag on the same one) so
// that moving between the review and the register never reuses one instance for two purposes.
import ReviewWorkbench from './ReviewWorkbench.vue'
</script>

<template>
  <ReviewWorkbench mode="people" />
</template>
