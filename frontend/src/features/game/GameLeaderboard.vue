<script setup lang="ts">
import { PhTrophy } from '@phosphor-icons/vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import AppScrollRegion from '@/components/base/AppScrollRegion.vue'

import type { GameLeaderboard } from './useGameData'

defineProps<{
  leaderboard: GameLeaderboard | undefined
  currentUserId: string
  pending: boolean
  failed: boolean
}>()

const emit = defineEmits<{ retry: [] }>()
const { n, t } = useI18n()
</script>

<template>
  <section class="game-leaderboard app-card" aria-labelledby="game-leaderboard-title">
    <header class="game-leaderboard__header">
      <div>
        <h2 id="game-leaderboard-title">
          <PhTrophy aria-hidden="true" />
          {{ t('game.leaderboard.title') }}
        </h2>
        <p>{{ t('game.leaderboard.hint') }}</p>
      </div>
      <span v-if="leaderboard" class="game-leaderboard__count">
        {{ t('game.leaderboard.playerCount', { count: n(leaderboard.total_players) }) }}
      </span>
    </header>

    <p v-if="pending" class="game-leaderboard__status" role="status">
      {{ t('game.leaderboard.loading') }}
    </p>

    <AppFeedback v-else-if="failed" tone="critical" announcement="polite">
      <p>{{ t('game.leaderboard.loadError') }}</p>
      <template #actions>
        <AppButton variant="ghost" @click="emit('retry')">
          {{ t('game.retry') }}
        </AppButton>
      </template>
    </AppFeedback>

    <AppFeedback v-else-if="leaderboard?.entries.length === 0">
      <p>{{ t('game.leaderboard.empty') }}</p>
    </AppFeedback>

    <AppScrollRegion v-else-if="leaderboard" :label="t('game.leaderboard.tableLabel')">
      <table>
        <thead>
          <tr>
            <th scope="col">{{ t('game.leaderboard.rank') }}</th>
            <th scope="col">{{ t('game.leaderboard.member') }}</th>
            <th scope="col">{{ t('game.leaderboard.score') }}</th>
            <th scope="col">{{ t('game.leaderboard.answered') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="entry in leaderboard.entries"
            :key="entry.round_id"
            :class="{ 'game-leaderboard__current': entry.reviewer_user_id === currentUserId }"
          >
            <td class="game-leaderboard__rank">{{ n(entry.rank) }}</td>
            <th scope="row">
              {{ entry.reviewer_display_name }}
              <span v-if="entry.reviewer_user_id === currentUserId" class="game-leaderboard__you">
                {{ t('game.leaderboard.you') }}
              </span>
            </th>
            <td class="game-leaderboard__score">{{ n(entry.score) }}</td>
            <td>{{ n(entry.answered_count) }}</td>
          </tr>
        </tbody>
      </table>
    </AppScrollRegion>
  </section>
</template>

<style scoped>
.game-leaderboard {
  display: grid;
  gap: var(--space-4);
  min-inline-size: 0;
}

.game-leaderboard__header {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: var(--space-4);
}

.game-leaderboard__header h2 {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0 0 var(--space-1);
  font-size: var(--font-size-page);
  line-height: var(--line-height-page);
}

.game-leaderboard__header h2 svg {
  color: var(--accent);
}

.game-leaderboard__header p,
.game-leaderboard__status {
  margin: 0;
  color: var(--text-secondary);
}

.game-leaderboard__count {
  flex: none;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  font-variant-numeric: tabular-nums;
}

table {
  width: 100%;
  min-width: 28rem;
  border-collapse: collapse;
  font-variant-numeric: tabular-nums;
}

th,
td {
  padding: var(--space-3);
  border-block-end: 1px solid var(--border);
  text-align: start;
  white-space: nowrap;
}

thead th {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  font-weight: var(--weight-semibold);
}

tbody th {
  font-weight: var(--weight-semibold);
}

.game-leaderboard__current {
  background: color-mix(in srgb, var(--accent) 10%, var(--panel));
}

.game-leaderboard__rank,
.game-leaderboard__score {
  color: var(--accent);
  font-weight: var(--weight-bold);
}

.game-leaderboard__you {
  margin-inline-start: var(--space-1);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  font-weight: var(--weight-regular);
}

@media (max-width: 40rem) {
  .game-leaderboard__header {
    display: grid;
  }
}
</style>
