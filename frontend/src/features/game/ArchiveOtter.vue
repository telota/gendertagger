<script setup lang="ts">
import otterSprite from '@/assets/game/archive-otter.png'

// One transparent collage atlas keeps the character consistent across all three poses.
withDefaults(defineProps<{ pose?: 'rest' | 'stamp' | 'complete' }>(), { pose: 'rest' })
</script>

<template>
  <span class="archive-otter" :class="`archive-otter--${pose}`" aria-hidden="true">
    <span class="archive-otter__art" :style="{ backgroundImage: `url(${otterSprite})` }"></span>
  </span>
</template>

<style scoped>
.archive-otter {
  display: block;
  inline-size: 100%;
  aspect-ratio: 648 / 809;
  pointer-events: none;
}

.archive-otter__art {
  display: block;
  inline-size: 100%;
  block-size: 100%;
  background-size: 300% 100%;
  background-repeat: no-repeat;
  background-position: left top;
  /* Transparent guard bands keep neighbouring silhouettes outside this atlas cell. */
  clip-path: inset(0 3% 0 0);
}

.archive-otter--stamp .archive-otter__art {
  /* The stamped pose starts at source x631, slightly before the nominal middle cell. */
  background-position: 48.75% top;
  clip-path: inset(0 1% 0 0);
  transform-origin: center bottom;
  animation: archive-otter-stamp 520ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

.archive-otter--complete .archive-otter__art {
  background-position: right top;
  clip-path: none;
}

@keyframes archive-otter-stamp {
  0% {
    transform: translateY(-3px) rotate(-3deg);
  }
  45% {
    transform: translateY(1px) rotate(1deg);
  }
  100% {
    transform: translateY(0) rotate(0deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .archive-otter--stamp .archive-otter__art {
    animation: none;
  }
}
</style>
