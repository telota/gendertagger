<script setup lang="ts">
import { PhArrowCounterClockwise, PhArrowRight, PhClock, PhFire } from '@phosphor-icons/vue'
import { useQueryClient } from '@tanstack/vue-query'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import AppScrollRegion from '@/components/base/AppScrollRegion.vue'
import { privateQueryKey } from '@/composables/usePrivateQueryScope'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import { useImportedSnapshot } from '@/features/projects/useSnapshotData'
import { useProject } from '@/features/projects/useProjects'
import PersonRecordDetails from '@/features/review/PersonRecordDetails.vue'
import VocabBadge from '@/features/review/VocabBadge.vue'
import { retainedReviewData, isRecoverableReviewError } from '@/features/review/retainedReviewData'
import { reviewItemName } from '@/features/review/reviewItemName'
import { useCreateAnnotation } from '@/features/review/useAnnotate'
import {
  useAnnotationHistory,
  usePersonRecord,
  useResultPredictions,
  useReviewItems,
  type ReviewItem,
} from '@/features/review/useReviewData'
import type { ReviewFilters } from '@/features/review/useReviewFilters'
import {
  CANONICAL_LABELS,
  useVocabularyGloss,
  type CanonicalLabel,
} from '@/features/review/useVocabulary'
import { useAggregation } from '@/features/runs/useAggregations'
import { useRun } from '@/features/runs/useRunDetail'

import ArchiveOtter from './ArchiveOtter.vue'
import GameLeaderboard from './GameLeaderboard.vue'
import {
  formatGameDuration,
  gameAnswerPoints,
  useGameLeaderboard,
  useSaveGameRound,
  type GameRound,
  type GameRoundEvent,
  type GameRoundSize,
} from './useGameData'

const { n, t } = useI18n()
const { session, isSignedIn, retrySession } = useRequireSession()
const cache = useQueryClient()
const gloss = useVocabularyGloss()

const projectId = useRouteParam('projectId')
const runId = useRouteParam('runId')
const aggregationId = useRouteParam('aggregationId')

const project = useProject(projectId, isSignedIn)
const projectData = computed(() =>
  retainedReviewData(
    cache,
    ['projects', projectId.value, session.user?.id ?? 'anonymous'],
    session.canUsePrivateNavigation,
    project.status.value,
    project.data.value,
    project.error.value,
  ),
)
const canReview = computed(() => {
  const role = projectData.value?.current_user_role
  return role === 'reviewer' || role === 'operator'
})
const gameEnabled = computed(() => projectData.value?.game_mode_enabled === true)

const aggregation = useAggregation(aggregationId, isSignedIn)
const run = useRun(runId, isSignedIn)
const runData = computed(() =>
  retainedReviewData(
    cache,
    privateQueryKey(['runs', runId.value], session.user?.id),
    session.canUsePrivateNavigation && projectData.value?.id === projectId.value,
    run.status.value,
    run.data.value,
    run.error.value,
  ),
)
const aggregationData = computed(() =>
  retainedReviewData(
    cache,
    privateQueryKey(['aggregations', aggregationId.value], session.user?.id),
    session.canUsePrivateNavigation && projectData.value?.id === projectId.value,
    aggregation.status.value,
    aggregation.data.value,
    aggregation.error.value,
  ),
)
const snapshotId = computed(() =>
  runData.value?.id === runId.value ? runData.value.dataset_snapshot_id : '',
)
const snapshot = useImportedSnapshot(
  projectId,
  snapshotId,
  computed(() => isSignedIn.value && snapshotId.value !== ''),
)
const validContext = computed(
  () =>
    projectData.value?.id === projectId.value &&
    runData.value?.id === runId.value &&
    aggregationData.value?.id === aggregationId.value &&
    aggregationData.value.run_id === runId.value &&
    (!snapshot.isError.value || isRecoverableReviewError(snapshot.error.value)) &&
    snapshot.data.value?.id === snapshotId.value &&
    snapshot.data.value.project_id === projectId.value &&
    snapshot.data.value.status === 'ready',
)
const isCompleted = computed(
  () => validContext.value && aggregationData.value?.status === 'completed',
)
const contextFailed = computed(
  () =>
    project.isError.value ||
    run.isError.value ||
    aggregation.isError.value ||
    snapshot.isError.value,
)
const contextPending = computed(
  () =>
    aggregation.isPending.value ||
    project.isPending.value ||
    run.isPending.value ||
    (snapshotId.value !== '' && snapshot.isPending.value),
)
const contextFresh = computed(
  () =>
    validContext.value &&
    !contextFailed.value &&
    !project.isFetching.value &&
    !run.isFetching.value &&
    !aggregation.isFetching.value &&
    !snapshot.isFetching.value,
)

type GameQuestionPool = 'open' | 'all'

const questionPool = ref<GameQuestionPool>('open')
const allPoolOffset = ref(0)
const nextAllPoolOffset = ref<number | null>(null)
const roundStarting = ref(false)
const roundPreparationFailed = ref(false)
const gameFilters = computed<ReviewFilters>(() => ({
  queue: 'all',
  q: '',
  sort: questionPool.value === 'open' ? 'uncertainty' : 'tei_id',
  workflowStates: questionPool.value === 'open' ? ['unreviewed'] : [],
  finalLabel: null,
  agreementTiers: [],
  hasAuthorityConflict: null,
  hasPredictionError: null,
  methodName: null,
  methodLabel: null,
  predictionStatus: null,
}))
const queueEnabled = computed(() => isCompleted.value && canReview.value && gameEnabled.value)
const queue = useReviewItems(aggregationId, gameFilters, queueEnabled)
const availableItems = computed(() => queue.data.value?.pages.flatMap((page) => page.items) ?? [])
const allEligibleCount = computed(() =>
  Math.max(snapshot.data.value?.record_count ?? 0, availableItems.value.length),
)
const roundSize = ref<GameRoundSize>(10)
const timerEnabled = ref(true)
const leaderboardEnabled = computed(() => isCompleted.value && gameEnabled.value)
const leaderboard = useGameLeaderboard(projectId, roundSize, leaderboardEnabled)
const saveRoundMutation = useSaveGameRound(projectId)
const createAnnotation = useCreateAnnotation()

const phase = ref<'setup' | 'playing' | 'feedback' | 'complete'>('setup')
const questions = ref<ReviewItem[]>([])
const currentIndex = ref(0)
const roundEvents = ref<GameRoundEvent[]>([])
const roundId = ref('')
const activeRoundSize = ref<GameRoundSize | null>(null)
const provisionalScore = ref(0)
const streak = ref(0)
const longestStreak = ref(0)
const lastPoints = ref(0)
const lastLabel = ref<CanonicalLabel | null>(null)
const officialRound = ref<GameRound | null>(null)
const questionStartedAt = ref(0)
const frozenElapsed = ref<number | null>(null)
const now = ref(Date.now())
const conflictDetected = ref(false)
const questionHeading = ref<HTMLElement | null>(null)
const feedbackHeading = ref<HTMLElement | null>(null)
const completionHeading = ref<HTMLElement | null>(null)
let clockHandle: number | undefined
let roundStartRevision = 0

const currentItem = computed(() => questions.value[currentIndex.value] ?? null)
const activeSnapshotId = computed(() => currentItem.value?.snapshot_id ?? null)
const activeTeiId = computed(() => currentItem.value?.tei_id ?? null)
const person = usePersonRecord(activeSnapshotId, activeTeiId)
const history = useAnnotationHistory(activeSnapshotId, activeTeiId)
const revealedResultId = computed(() =>
  phase.value === 'feedback' ? (currentItem.value?.aggregated_result_id ?? null) : null,
)
const predictions = useResultPredictions(aggregationId, revealedResultId)

const activeElapsed = computed(() => {
  if (phase.value !== 'playing' && phase.value !== 'feedback') return 0
  return frozenElapsed.value ?? Math.max(0, now.value - questionStartedAt.value)
})
const completedCount = computed(() => roundEvents.value.length)
const progressPercentage = computed(() =>
  questions.value.length === 0 ? 0 : (completedCount.value / questions.value.length) * 100,
)
const staleQuestion = computed(() => {
  const item = currentItem.value
  const current = history.data.value
  return (
    item !== null &&
    current?.snapshot_id === item.snapshot_id &&
    current.tei_id === item.tei_id &&
    current.revision !== item.review_revision
  )
})
const decisionReady = computed(
  () =>
    phase.value === 'playing' &&
    currentItem.value !== null &&
    contextFresh.value &&
    !staleQuestion.value &&
    person.data.value?.tei_id === currentItem.value.tei_id &&
    person.data.value.dataset_snapshot_id === currentItem.value.snapshot_id &&
    history.data.value?.tei_id === currentItem.value.tei_id &&
    history.data.value.snapshot_id === currentItem.value.snapshot_id &&
    !person.isFetching.value &&
    !history.isFetching.value &&
    !person.isError.value &&
    !history.isError.value &&
    !createAnnotation.isPending.value,
)
const displayScore = computed(() => officialRound.value?.score ?? provisionalScore.value)
const completionDuration = computed(() =>
  roundEvents.value.reduce((total, event) => total + event.elapsed_milliseconds, 0),
)
const eligibleItemCount = computed(() =>
  questionPool.value === 'open' ? availableItems.value.length : allEligibleCount.value,
)
const actualRoundCount = computed(() => {
  if (questionPool.value === 'open') return Math.min(roundSize.value, availableItems.value.length)
  if (allEligibleCount.value === 0) return 0
  const offset = allPoolOffset.value % allEligibleCount.value
  return Math.min(roundSize.value, allEligibleCount.value - offset)
})
const currentName = computed(() =>
  currentItem.value === null ? '' : reviewItemName(currentItem.value),
)

const poolOptions = computed<readonly { value: GameQuestionPool; title: string; hint: string }[]>(
  () => [
    {
      value: 'open',
      title: t('game.pool.open'),
      hint: t('game.pool.openHint'),
    },
    {
      value: 'all',
      title: t('game.pool.all'),
      hint: t('game.pool.allHint'),
    },
  ],
)

const roundOptions = computed<readonly { size: GameRoundSize; title: string; hint: string }[]>(
  () => [
    {
      size: 10,
      title: t('game.rounds.short'),
      hint: t('game.rounds.shortHint', { count: n(10) }),
    },
    {
      size: 20,
      title: t('game.rounds.standard'),
      hint: t('game.rounds.standardHint', { count: n(20) }),
    },
    {
      size: 50,
      title: t('game.rounds.long'),
      hint: t('game.rounds.longHint', { count: n(50) }),
    },
  ],
)

function timerPreferenceKey(userId: string): string {
  return `gendertagger.game.timer.${userId}`
}

function restoreTimerPreference(): void {
  const userId = session.user?.id
  if (!userId) return
  try {
    const stored = window.localStorage.getItem(timerPreferenceKey(userId))
    if (stored !== null) timerEnabled.value = stored === 'true'
  } catch {
    // Storage is optional. The in-memory setting remains fully usable.
  }
}

function storeTimerPreference(enabled: boolean): void {
  const userId = session.user?.id
  if (!userId) return
  try {
    window.localStorage.setItem(timerPreferenceKey(userId), String(enabled))
  } catch {
    // Storage is optional. The in-memory setting remains fully usable.
  }
}

function retryContext(): void {
  void project.refetch()
  void run.refetch()
  void aggregation.refetch()
  if (snapshotId.value !== '') void snapshot.refetch()
}

function resetRoundState(): void {
  roundStartRevision += 1
  roundStarting.value = false
  roundPreparationFailed.value = false
  phase.value = 'setup'
  nextAllPoolOffset.value = null
  questions.value = []
  currentIndex.value = 0
  roundEvents.value = []
  roundId.value = ''
  activeRoundSize.value = null
  provisionalScore.value = 0
  streak.value = 0
  longestStreak.value = 0
  lastPoints.value = 0
  lastLabel.value = null
  officialRound.value = null
  questionStartedAt.value = 0
  frozenElapsed.value = null
  conflictDetected.value = false
  createAnnotation.reset()
  saveRoundMutation.reset()
}

async function focusQuestion(): Promise<void> {
  await nextTick()
  questionHeading.value?.focus()
}

async function roundQuestions(
  pool: GameQuestionPool,
  targetCount: number,
): Promise<{ items: ReviewItem[]; nextAllOffset: number } | null> {
  if (pool === 'open') {
    return {
      items: availableItems.value.slice(0, targetCount),
      nextAllOffset: allPoolOffset.value,
    }
  }

  const total = allEligibleCount.value
  const offset = total === 0 ? 0 : allPoolOffset.value % total
  while (availableItems.value.length < offset + targetCount && queue.hasNextPage.value) {
    const loadedCount = availableItems.value.length
    const result = await queue.fetchNextPage()
    if (result.isError || availableItems.value.length === loadedCount) {
      roundPreparationFailed.value = true
      return null
    }
  }
  const items = availableItems.value.slice(offset, offset + targetCount)
  if (items.length !== targetCount) {
    roundPreparationFailed.value = true
    return null
  }
  return { items, nextAllOffset: offset + items.length }
}

async function startRound(): Promise<void> {
  if (
    roundStarting.value ||
    !contextFresh.value ||
    queue.isFetching.value ||
    !canReview.value ||
    actualRoundCount.value === 0
  )
    return

  const revision = ++roundStartRevision
  const pool = questionPool.value
  const selectedRoundSize = roundSize.value
  const targetCount = actualRoundCount.value
  roundStarting.value = true
  roundPreparationFailed.value = false
  try {
    const selection = await roundQuestions(pool, targetCount)
    if (
      selection === null ||
      revision !== roundStartRevision ||
      pool !== questionPool.value ||
      !contextFresh.value ||
      selection.items.length === 0
    )
      return
    questions.value = selection.items
    if (pool === 'all') nextAllPoolOffset.value = selection.nextAllOffset
    activeRoundSize.value = selectedRoundSize
    currentIndex.value = 0
    roundEvents.value = []
    roundId.value = globalThis.crypto.randomUUID()
    provisionalScore.value = 0
    streak.value = 0
    longestStreak.value = 0
    lastPoints.value = 0
    lastLabel.value = null
    officialRound.value = null
    conflictDetected.value = false
    frozenElapsed.value = null
    createAnnotation.reset()
    saveRoundMutation.reset()
    phase.value = 'playing'
    questionStartedAt.value = Date.now()
    now.value = questionStartedAt.value
    await focusQuestion()
  } finally {
    if (revision === roundStartRevision) roundStarting.value = false
  }
}

async function persistRound(): Promise<void> {
  if (officialRound.value !== null || roundId.value === '' || activeRoundSize.value === null) return
  try {
    const saved = await saveRoundMutation.mutateAsync({
      id: roundId.value,
      aggregation_execution_id: aggregationId.value,
      round_size: activeRoundSize.value,
      annotation_ids: roundEvents.value.flatMap((event) =>
        event.kind === 'answer' ? [event.annotation_id] : [],
      ),
    })
    officialRound.value = saved
    provisionalScore.value = saved.score
    void leaderboard.refetch()
  } catch {
    // The completed round and its id stay mounted so the same idempotent command can be retried.
  }
}

async function finishRound(): Promise<void> {
  if (nextAllPoolOffset.value !== null) {
    allPoolOffset.value = nextAllPoolOffset.value
    nextAllPoolOffset.value = null
  }
  phase.value = 'complete'
  frozenElapsed.value = null
  await nextTick()
  completionHeading.value?.focus()
  await persistRound()
}

async function advanceQuestion(): Promise<void> {
  createAnnotation.reset()
  conflictDetected.value = false
  lastLabel.value = null
  lastPoints.value = 0
  frozenElapsed.value = null
  if (currentIndex.value + 1 >= questions.value.length) {
    await finishRound()
    return
  }
  currentIndex.value += 1
  phase.value = 'playing'
  questionStartedAt.value = Date.now()
  now.value = questionStartedAt.value
  await focusQuestion()
}

async function answer(label: CanonicalLabel): Promise<void> {
  const item = currentItem.value
  const visibleHistory = history.data.value
  if (!decisionReady.value || item === null || visibleHistory === undefined) return

  const elapsedMilliseconds = frozenElapsed.value ?? activeElapsed.value
  frozenElapsed.value = elapsedMilliseconds
  conflictDetected.value = false
  createAnnotation.reset()
  const activeRoundId = roundId.value
  try {
    const annotation = await createAnnotation.mutateAsync({
      item: {
        snapshot_id: item.snapshot_id,
        tei_id: item.tei_id,
        aggregated_result_id: item.aggregated_result_id,
      },
      action: item.machine_label === label ? 'verify' : 'correct',
      label,
      comment: '',
      expectedRevision: visibleHistory.revision,
    })
    if (roundId.value !== activeRoundId || currentItem.value?.tei_id !== item.tei_id) return
    const points = gameAnswerPoints()
    roundEvents.value.push({
      kind: 'answer',
      annotation_id: annotation.id,
      elapsed_milliseconds: elapsedMilliseconds,
    })
    provisionalScore.value += points
    streak.value += 1
    longestStreak.value = Math.max(longestStreak.value, streak.value)
    lastPoints.value = points
    lastLabel.value = label
    phase.value = 'feedback'
    await nextTick()
    feedbackHeading.value?.focus()
  } catch (error) {
    conflictDetected.value = error instanceof ApiError && error.code === 'annotation_conflict'
    if (!conflictDetected.value) frozenElapsed.value = null
  }
}

async function skipQuestion(): Promise<void> {
  if (phase.value !== 'playing' || currentItem.value === null || createAnnotation.isPending.value)
    return
  roundEvents.value.push({ kind: 'skip', elapsed_milliseconds: activeElapsed.value })
  streak.value = 0
  await advanceQuestion()
}
async function retryQuestionPool(): Promise<void> {
  roundPreparationFailed.value = false
  await queue.refetch()
}

async function refreshQuestionPool(): Promise<void> {
  resetRoundState()
  await queue.refetch()
}

async function playAgain(): Promise<void> {
  resetRoundState()
  await queue.refetch()
}

function onGameKeydown(event: KeyboardEvent): void {
  if (
    phase.value !== 'playing' ||
    event.altKey ||
    event.ctrlKey ||
    event.metaKey ||
    event.shiftKey ||
    event.repeat
  )
    return
  const target = event.target
  if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) return
  const label = CANONICAL_LABELS[Number(event.key) - 1]
  if (label === undefined || !decisionReady.value) return
  event.preventDefault()
  void answer(label)
}

function resetGameContext(): void {
  questionPool.value = 'open'
  allPoolOffset.value = 0
  resetRoundState()
}

watch(() => session.user?.id, restoreTimerPreference, { immediate: true })
watch(timerEnabled, storeTimerPreference)
watch(questionPool, () => {
  allPoolOffset.value = 0
  roundPreparationFailed.value = false
})
watch([projectId, runId, aggregationId, () => session.user?.id], resetGameContext)

onMounted(() => {
  clockHandle = window.setInterval(() => {
    if (phase.value === 'playing') now.value = Date.now()
  }, 250)
  window.addEventListener('keydown', onGameKeydown)
})
onBeforeUnmount(() => {
  if (clockHandle !== undefined) window.clearInterval(clockHandle)
  window.removeEventListener('keydown', onGameKeydown)
})
</script>

<template>
  <main class="game-mode app-page-frame">
    <AppFeedback
      v-if="session.status === 'idle' || session.status === 'loading'"
      class="game-mode__state app-card"
      announcement="polite"
    >
      {{ t('game.loading') }}
    </AppFeedback>
    <AppFeedback
      v-else-if="session.status === 'error'"
      class="game-mode__state app-card"
      tone="critical"
      announcement="assertive"
    >
      <p>{{ t('projects.sessionLoadError') }}</p>
      <template #actions>
        <AppButton @click="retrySession">{{ t('game.retry') }}</AppButton>
      </template>
    </AppFeedback>

    <template v-else-if="isSignedIn">
      <header class="game-mode__header app-page-heading">
        <div class="app-page-heading__copy">
          <div class="game-mode__title-row">
            <h1 class="app-page-heading__title">{{ t('game.title') }}</h1>
            <span class="game-mode__optional">{{ t('game.optional') }}</span>
          </div>
          <p class="app-page-heading__description">{{ t('game.intro') }}</p>
        </div>
      </header>

      <AppFeedback v-if="contextPending" class="game-mode__state app-card" announcement="polite">
        {{ t('game.loading') }}
      </AppFeedback>
      <AppFeedback
        v-else-if="!validContext"
        class="game-mode__state app-card"
        tone="critical"
        announcement="assertive"
      >
        <p>{{ t('taskEntry.selectionUnavailable') }}</p>
        <template #actions>
          <AppButton variant="ghost" @click="retryContext">{{ t('game.retry') }}</AppButton>
        </template>
      </AppFeedback>
      <AppFeedback v-else-if="!gameEnabled" class="game-mode__state app-card">
        <p>{{ t('game.disabled') }}</p>
      </AppFeedback>
      <AppFeedback v-else-if="!isCompleted" class="game-mode__state app-card">
        <p>{{ t('review.notCompleted') }}</p>
      </AppFeedback>

      <template v-else>
        <AppFeedback
          v-if="contextFailed"
          class="game-mode__state app-card"
          tone="critical"
          announcement="polite"
        >
          <p>{{ t('review.refreshError') }}</p>
          <template #actions>
            <AppButton variant="ghost" @click="retryContext">{{ t('game.retry') }}</AppButton>
          </template>
        </AppFeedback>

        <AppFeedback v-if="!canReview" class="game-mode__state app-card">
          <p>{{ t('game.reviewerRequired') }}</p>
        </AppFeedback>

        <template v-if="phase === 'setup'">
          <section v-if="canReview" class="game-setup app-card" aria-labelledby="game-setup-title">
            <div class="game-setup__heading">
              <ArchiveOtter class="game-setup__otter" />
              <div>
                <h2 id="game-setup-title">{{ t('game.setup.title') }}</h2>
                <p>{{ t('game.setup.hint') }}</p>
              </div>
            </div>

            <AppFeedback class="game-setup__principle">
              <p>{{ t('game.scoringPrinciple') }}</p>
            </AppFeedback>

            <fieldset class="game-pool-options">
              <legend>{{ t('game.pool.legend') }}</legend>
              <label
                v-for="option in poolOptions"
                :key="option.value"
                class="game-round-option"
                :class="{ 'game-round-option--selected': questionPool === option.value }"
              >
                <input
                  :id="`game-pool-${option.value}`"
                  v-model="questionPool"
                  type="radio"
                  name="game-question-pool"
                  :value="option.value"
                  :disabled="roundStarting"
                />
                <span class="game-round-option__copy">
                  <strong>{{ option.title }}</strong>
                  <span>{{ option.hint }}</span>
                </span>
              </label>
            </fieldset>

            <fieldset class="game-round-options">
              <legend>{{ t('game.rounds.legend') }}</legend>
              <label
                v-for="option in roundOptions"
                :key="option.size"
                class="game-round-option"
                :class="{ 'game-round-option--selected': roundSize === option.size }"
              >
                <input
                  v-model="roundSize"
                  type="radio"
                  name="game-round-size"
                  :value="option.size"
                  :disabled="roundStarting"
                />
                <span class="game-round-option__copy">
                  <strong>{{ option.title }}</strong>
                  <span>{{ option.hint }}</span>
                </span>
                <span class="game-round-option__count">{{ n(option.size) }}</span>
              </label>
            </fieldset>

            <label class="game-timer-option">
              <input v-model="timerEnabled" type="checkbox" :disabled="roundStarting" />
              <span>
                <strong>{{ t('game.timer.label') }}</strong>
                <span>{{ t('game.timer.hint') }}</span>
              </span>
            </label>

            <p
              v-if="queue.isPending.value || (queue.isFetching.value && !roundPreparationFailed)"
              role="status"
            >
              {{ t('game.queue.loading') }}
            </p>
            <AppFeedback
              v-else-if="queue.isError.value || roundPreparationFailed"
              tone="critical"
              announcement="polite"
            >
              <p>{{ t('game.queue.loadError') }}</p>
              <template #actions>
                <AppButton variant="ghost" @click="retryQuestionPool">
                  {{ t('game.retry') }}
                </AppButton>
              </template>
            </AppFeedback>
            <AppFeedback v-else-if="availableItems.length === 0">
              <p v-if="questionPool === 'open'">{{ t('game.queue.emptyOpen') }}</p>
              <p v-else>{{ t('game.queue.emptyAll') }}</p>
              <template #actions>
                <AppButton
                  variant="ghost"
                  :to="{
                    name: 'review',
                    params: { projectId, runId, aggregationId },
                  }"
                >
                  {{ t('game.backToReview') }}
                </AppButton>
              </template>
            </AppFeedback>
            <div v-else class="game-setup__start">
              <p v-if="questionPool === 'open'">
                {{
                  t('game.setup.availableOpen', {
                    available: n(eligibleItemCount),
                    count: n(actualRoundCount),
                  })
                }}
              </p>
              <p v-else>
                {{
                  t('game.setup.availableAll', {
                    available: n(eligibleItemCount),
                    count: n(actualRoundCount),
                  })
                }}
              </p>
              <AppButton
                :disabled="!contextFresh || roundStarting || queue.isFetching.value"
                @click="startRound"
              >
                <PhArrowRight :size="18" aria-hidden="true" />
                {{
                  roundStarting
                    ? t('game.setup.preparing')
                    : t('game.start', { count: n(actualRoundCount) })
                }}
              </AppButton>
            </div>
          </section>

          <GameLeaderboard
            :leaderboard="leaderboard.data.value"
            :current-user-id="session.user?.id ?? ''"
            :pending="leaderboard.isPending.value"
            :failed="leaderboard.isError.value"
            @retry="() => leaderboard.refetch()"
          />
        </template>

        <template v-else-if="phase === 'playing' || phase === 'feedback'">
          <section class="game-hud app-card" :aria-label="t('game.round.statusLabel')">
            <div class="game-hud__progress-copy">
              <span>
                {{
                  t('game.round.progress', {
                    current: n(Math.min(completedCount + 1, questions.length)),
                    total: n(questions.length),
                  })
                }}
              </span>
              <span>{{ n(progressPercentage / 100, 'percent') }}</span>
            </div>
            <div class="game-hud__otter-lane" aria-hidden="true">
              <div
                class="game-hud__otter-track"
                :style="{ '--game-progress': `${progressPercentage}%` }"
              >
                <ArchiveOtter :pose="phase === 'feedback' ? 'stamp' : 'rest'" />
              </div>
            </div>
            <progress
              class="game-hud__progress"
              :value="completedCount"
              :max="questions.length"
              :aria-label="
                t('game.round.progressLabel', {
                  complete: n(completedCount),
                  total: n(questions.length),
                })
              "
            ></progress>
            <dl class="game-hud__stats">
              <div>
                <dt>{{ t('game.round.score') }}</dt>
                <dd class="game-hud__score">
                  {{ n(provisionalScore) }}
                  <span v-if="phase === 'feedback'" class="game-hud__points" aria-hidden="true">
                    {{ t('game.feedback.earnedPoints', { points: n(lastPoints) }) }}
                  </span>
                </dd>
              </div>
              <div>
                <dt>
                  <PhFire aria-hidden="true" />
                  {{ t('game.round.streak') }}
                </dt>
                <dd>{{ n(streak) }}</dd>
              </div>
              <div v-if="timerEnabled">
                <dt>
                  <PhClock aria-hidden="true" />
                  {{ t('game.round.timer') }}
                </dt>
                <dd>{{ formatGameDuration(activeElapsed) }}</dd>
              </div>
            </dl>
          </section>

          <article
            v-if="currentItem"
            class="game-question app-card app-card--sectioned"
            :aria-labelledby="`game-person-${currentItem.tei_id}`"
          >
            <header class="game-question__header">
              <div>
                <p class="game-question__position">
                  {{
                    t('game.round.question', {
                      current: n(currentIndex + 1),
                      total: n(questions.length),
                    })
                  }}
                </p>
                <h2 :id="`game-person-${currentItem.tei_id}`" ref="questionHeading" tabindex="-1">
                  {{ currentName }}
                </h2>
              </div>
              <code>{{ currentItem.tei_id }}</code>
            </header>

            <section class="game-question__record" aria-labelledby="game-record-heading">
              <h3 id="game-record-heading">{{ t('game.record.title') }}</h3>
              <p v-if="person.isPending.value" role="status">{{ t('game.record.loading') }}</p>
              <AppFeedback v-else-if="person.isError.value" tone="critical" announcement="polite">
                <p>{{ t('game.record.loadError') }}</p>
                <template #actions>
                  <AppButton variant="ghost" @click="() => person.refetch()">
                    {{ t('game.retry') }}
                  </AppButton>
                </template>
              </AppFeedback>
              <PersonRecordDetails
                v-else-if="
                  person.data.value?.tei_id === currentItem.tei_id &&
                  person.data.value.dataset_snapshot_id === currentItem.snapshot_id
                "
                :record="person.data.value"
              />
            </section>

            <div class="game-question__response">
              <section
                class="game-decision"
                :inert="phase !== 'playing' ? true : undefined"
                :aria-hidden="phase !== 'playing' ? true : undefined"
                aria-labelledby="game-decision-heading"
              >
                <div class="game-decision__heading">
                  <h3 id="game-decision-heading">{{ t('game.decision.title') }}</h3>
                  <p>{{ t('game.decision.hint') }}</p>
                </div>

                <p v-if="phase === 'playing' && history.isPending.value" role="status">
                  {{ t('game.decision.loading') }}
                </p>
                <AppFeedback
                  v-else-if="phase === 'playing' && history.isError.value"
                  tone="critical"
                  announcement="polite"
                >
                  <p>{{ t('game.decision.loadError') }}</p>
                  <template #actions>
                    <AppButton variant="ghost" @click="() => history.refetch()">
                      {{ t('game.retry') }}
                    </AppButton>
                  </template>
                </AppFeedback>
                <AppFeedback
                  v-else-if="phase === 'playing' && (staleQuestion || conflictDetected)"
                  tone="critical"
                  announcement="assertive"
                >
                  <p>{{ t('game.decision.changed') }}</p>
                  <template #actions>
                    <AppButton variant="ghost" @click="refreshQuestionPool">
                      <PhArrowCounterClockwise :size="18" aria-hidden="true" />
                      {{ t('game.decision.refreshRound') }}
                    </AppButton>
                  </template>
                </AppFeedback>
                <template v-else>
                  <div class="game-answer-grid">
                    <button
                      v-for="(label, index) in CANONICAL_LABELS"
                      :key="label"
                      type="button"
                      class="game-answer"
                      :class="`game-answer--${label}`"
                      :disabled="!decisionReady"
                      :aria-keyshortcuts="String(index + 1)"
                      @click="answer(label)"
                    >
                      <span class="game-answer__key" aria-hidden="true">{{ index + 1 }}</span>
                      <span class="game-answer__label">{{ label }}</span>
                    </button>
                  </div>

                  <AppFeedback
                    v-if="createAnnotation.isError.value"
                    tone="critical"
                    announcement="assertive"
                  >
                    <p>{{ t('game.decision.saveError') }}</p>
                  </AppFeedback>

                  <div class="game-decision__secondary">
                    <AppButton
                      variant="ghost"
                      :disabled="createAnnotation.isPending.value"
                      @click="skipQuestion"
                    >
                      {{ t('game.decision.skip') }}
                    </AppButton>
                    <span v-if="createAnnotation.isPending.value" role="status">
                      {{ t('game.decision.saving') }}
                    </span>
                  </div>
                </template>
              </section>

              <section
                v-if="phase === 'feedback'"
                class="game-feedback"
                aria-labelledby="game-feedback-heading"
              >
                <AppFeedback announcement="polite">
                  <h3
                    id="game-feedback-heading"
                    ref="feedbackHeading"
                    class="game-feedback__saved"
                    tabindex="-1"
                  >
                    <span class="game-feedback__stamp" aria-hidden="true">
                      {{ t('game.feedback.stamp') }}
                    </span>
                    {{ t('game.feedback.saved', { points: n(lastPoints) }) }}
                    <VocabBadge
                      :value="lastLabel"
                      :gloss="lastLabel ? gloss.label(lastLabel) : ''"
                      kind="label"
                    />
                  </h3>
                </AppFeedback>
                <p class="game-feedback__explanation">{{ t('game.feedback.explanation') }}</p>

                <div class="game-feedback__machine">
                  <span>{{ t('game.feedback.machineLabel') }}</span>
                  <VocabBadge
                    :value="currentItem.machine_label"
                    :gloss="currentItem.machine_label ? gloss.label(currentItem.machine_label) : ''"
                    kind="label"
                  />
                </div>

                <details class="game-evidence">
                  <summary>{{ t('game.feedback.evidenceTitle') }}</summary>
                  <p>{{ t('game.feedback.evidenceHint') }}</p>
                  <p v-if="predictions.isPending.value" role="status">
                    {{ t('game.feedback.loading') }}
                  </p>
                  <AppFeedback
                    v-else-if="predictions.isError.value"
                    tone="critical"
                    announcement="polite"
                  >
                    <p>{{ t('game.feedback.loadError') }}</p>
                    <template #actions>
                      <AppButton variant="ghost" @click="() => predictions.refetch()">
                        {{ t('game.retry') }}
                      </AppButton>
                    </template>
                  </AppFeedback>
                  <AppFeedback v-else-if="predictions.data.value?.length === 0">
                    <p>{{ t('game.feedback.noEvidence') }}</p>
                  </AppFeedback>
                  <AppScrollRegion
                    v-else-if="predictions.data.value"
                    :label="t('game.feedback.evidenceTable')"
                  >
                    <table class="game-evidence__table">
                      <thead>
                        <tr>
                          <th scope="col">{{ t('review.detail.methods.method') }}</th>
                          <th scope="col">{{ t('review.detail.methods.label') }}</th>
                          <th scope="col">{{ t('review.detail.methods.status') }}</th>
                          <th scope="col">{{ t('review.detail.methods.confidence') }}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr
                          v-for="entry in predictions.data.value"
                          :key="entry.method_execution_id"
                        >
                          <th scope="row">{{ entry.method_name }}</th>
                          <template v-if="entry.prediction">
                            <td>
                              <VocabBadge
                                :value="entry.prediction.label"
                                :gloss="
                                  entry.prediction.label ? gloss.label(entry.prediction.label) : ''
                                "
                                kind="label"
                              />
                            </td>
                            <td>{{ entry.prediction.status }}</td>
                            <td>
                              <template v-if="entry.prediction.method_confidence != null">
                                {{ n(entry.prediction.method_confidence, 'confidence') }}
                              </template>
                              <span v-else>{{ t('review.none') }}</span>
                            </td>
                          </template>
                          <td v-else colspan="3">{{ t('review.detail.methods.noPrediction') }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </AppScrollRegion>
                </details>

                <div class="game-feedback__next">
                  <AppButton @click="advanceQuestion">
                    {{
                      currentIndex + 1 >= questions.length
                        ? t('game.feedback.finish')
                        : t('game.feedback.next')
                    }}
                    <PhArrowRight :size="18" aria-hidden="true" />
                  </AppButton>
                </div>
              </section>
            </div>
          </article>
        </template>

        <template v-else>
          <section class="game-complete app-card" aria-labelledby="game-complete-heading">
            <div class="game-complete__heading">
              <div class="game-complete__illustration" aria-hidden="true">
                <ArchiveOtter pose="complete" />
                <svg
                  v-if="officialRound"
                  class="game-complete__stars"
                  viewBox="0 0 160 140"
                  fill="currentColor"
                  focusable="false"
                >
                  <path
                    class="game-paper-star game-paper-star--first"
                    d="m20 26 3 7 7 3-7 3-3 7-3-7-7-3 7-3Z"
                  />
                  <path
                    class="game-paper-star game-paper-star--second"
                    d="m138 48 3 7 7 3-7 3-3 7-3-7-7-3 7-3Z"
                  />
                  <path
                    class="game-paper-star game-paper-star--third"
                    d="m116 12 2 5 5 2-5 2-2 5-2-5-5-2 5-2Z"
                  />
                </svg>
              </div>
              <div>
                <h2 id="game-complete-heading" ref="completionHeading" tabindex="-1">
                  {{ t('game.complete.title') }}
                </h2>
                <p>{{ t('game.complete.hint') }}</p>
              </div>
            </div>

            <dl class="game-complete__stats">
              <div>
                <dt>{{ t('game.complete.score') }}</dt>
                <dd>{{ n(displayScore) }}</dd>
              </div>
              <div>
                <dt>{{ t('game.complete.time') }}</dt>
                <dd>{{ formatGameDuration(completionDuration) }}</dd>
              </div>
              <div>
                <dt>{{ t('game.complete.answered') }}</dt>
                <dd>{{ n(roundEvents.filter((event) => event.kind === 'answer').length) }}</dd>
              </div>
              <div>
                <dt>{{ t('game.complete.skipped') }}</dt>
                <dd>{{ n(roundEvents.filter((event) => event.kind === 'skip').length) }}</dd>
              </div>
              <div>
                <dt>{{ t('game.complete.longestStreak') }}</dt>
                <dd>{{ n(longestStreak) }}</dd>
              </div>
            </dl>

            <p v-if="saveRoundMutation.isPending.value" role="status">
              {{ t('game.complete.saving') }}
            </p>
            <AppFeedback
              v-else-if="saveRoundMutation.isError.value"
              tone="critical"
              announcement="assertive"
            >
              <p>{{ t('game.complete.saveError') }}</p>
              <template #actions>
                <AppButton variant="ghost" @click="persistRound">
                  {{ t('game.complete.retrySave') }}
                </AppButton>
              </template>
            </AppFeedback>
            <AppFeedback
              v-else-if="officialRound"
              class="game-complete__receipt"
              announcement="polite"
            >
              <p>{{ t('game.complete.saved') }}</p>
            </AppFeedback>

            <div class="game-complete__actions">
              <AppButton :disabled="officialRound === null" @click="playAgain">
                <PhArrowCounterClockwise :size="18" aria-hidden="true" />
                {{ t('game.complete.playAgain') }}
              </AppButton>
              <AppButton
                variant="ghost"
                :to="{
                  name: 'review',
                  params: { projectId, runId, aggregationId },
                }"
              >
                {{ t('game.backToReview') }}
              </AppButton>
            </div>
          </section>

          <GameLeaderboard
            :leaderboard="leaderboard.data.value"
            :current-user-id="session.user?.id ?? ''"
            :pending="leaderboard.isPending.value"
            :failed="leaderboard.isError.value"
            @retry="() => leaderboard.refetch()"
          />
        </template>
      </template>
    </template>
  </main>
</template>

<style scoped>
.game-mode {
  display: grid;
  gap: var(--space-6);
}

.game-mode__header {
  margin-block-end: 0;
}

.game-mode__title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.game-mode__title-row h1 {
  margin: 0;
  font-size: var(--font-size-display);
  line-height: var(--line-height-display);
  letter-spacing: -0.025em;
}

.game-mode__header > p {
  margin: var(--space-2) 0 0;
  color: var(--text-secondary);
}

.game-mode__optional {
  padding: 0 var(--space-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  font-weight: var(--weight-semibold);
}

.game-setup,
.game-question,
.game-complete {
  min-inline-size: 0;
}

.game-setup,
.game-complete {
  display: grid;
  gap: var(--space-6);
}

.game-setup__heading,
.game-complete__heading {
  display: flex;
  align-items: start;
  gap: var(--space-3);
}

.game-setup__heading,
.game-complete__heading {
  align-items: center;
}

.game-setup__otter {
  flex: none;
  inline-size: 5rem;
}

.game-setup h2,
.game-complete h2 {
  margin: 0;
  font-size: var(--font-size-page);
  line-height: var(--line-height-page);
}

.game-setup__heading p,
.game-complete__heading p,
.game-setup__principle p {
  margin: var(--space-1) 0 0;
  color: var(--text-secondary);
}

.game-setup__principle {
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--surface-1);
}

.game-pool-options,
.game-round-options {
  display: grid;
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  border: 0;
}

.game-pool-options {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.game-round-options {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.game-pool-options legend,
.game-round-options legend {
  margin-block-end: var(--space-3);
  font-weight: var(--weight-semibold);
}

.game-round-option {
  position: relative;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: var(--space-3);
  min-height: var(--control-touch-size);
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--surface-1);
  cursor: pointer;
  transition:
    border-color var(--motion-state) ease-out,
    background-color var(--motion-state) ease-out;
}

.game-round-option:hover,
.game-round-option--selected {
  border-color: var(--accent);
}

.game-round-option--selected {
  background: color-mix(in srgb, var(--accent) 8%, var(--panel));
}

.game-round-option input {
  margin: var(--space-1) 0 0;
  accent-color: var(--accent);
}

.game-round-option__copy {
  display: grid;
  gap: var(--space-1);
  min-width: 0;
}

.game-round-option__copy span {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.game-round-option__count {
  color: var(--accent);
  font-size: var(--font-size-page);
  font-weight: var(--weight-bold);
  font-variant-numeric: tabular-nums;
}

.game-timer-option {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: start;
  gap: var(--space-3);
  cursor: pointer;
}

.game-timer-option input {
  margin: var(--space-1) 0 0;
  accent-color: var(--accent-b);
}

.game-timer-option span {
  display: grid;
  gap: var(--space-1);
}

.game-timer-option span span {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.game-setup__start {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding-block-start: var(--space-4);
  border-block-start: 1px solid var(--border);
}

.game-setup__start p {
  margin: 0;
  color: var(--text-secondary);
}

.game-hud {
  display: grid;
  gap: var(--space-3);
}

.game-hud__progress-copy {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  font-variant-numeric: tabular-nums;
}

.game-hud__progress {
  width: 100%;
  height: var(--space-2);
  accent-color: var(--accent);
}

.game-hud__stats,
.game-complete__stats {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4) var(--space-8);
  margin: 0;
}

.game-hud__stats div,
.game-complete__stats div {
  display: grid;
  gap: var(--space-1);
}

.game-hud__stats dt,
.game-complete__stats dt {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.game-hud__stats dd,
.game-complete__stats dd {
  margin: 0;
  color: var(--accent);
  font-size: var(--font-size-page);
  font-weight: var(--weight-bold);
  font-variant-numeric: tabular-nums;
}

.game-question {
  overflow: hidden;
}

.game-question__header {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-4);
  border-block-end: 1px solid var(--border);
  background: var(--surface-1);
}

.game-question__position {
  margin: 0 0 var(--space-1);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  font-variant-numeric: tabular-nums;
}

.game-question__header h2 {
  margin: 0;
  font-size: var(--font-size-page);
  line-height: var(--line-height-page);
}

.game-question__header code {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  overflow-wrap: anywhere;
}

.game-question__record,
.game-decision,
.game-feedback {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-4);
}

.game-question__record {
  border-block-end: 1px solid var(--border);
}

/* Keep the full answer geometry as a responsive floor beneath saved feedback. */
.game-question__response {
  display: grid;
}

.game-question__response > section {
  grid-area: 1 / 1;
  min-inline-size: 0;
  align-content: start;
}

.game-decision[inert] {
  visibility: hidden;
}

.game-question__record h3,
.game-decision h3 {
  margin: 0;
  font-size: var(--font-size-title);
  line-height: var(--line-height-title);
}

.game-decision__heading p,
.game-feedback__explanation,
.game-evidence > p {
  margin: var(--space-1) 0 0;
  color: var(--text-secondary);
}

.game-answer-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.game-answer {
  position: relative;
  display: grid;
  justify-items: start;
  align-content: center;
  gap: var(--space-1);
  min-width: 0;
  min-height: 4.25rem;
  padding: var(--space-3) var(--space-5);
  border: 1px solid;
  border-radius: var(--radius-input);
  font: inherit;
  text-align: start;
  cursor: pointer;
  transition:
    filter var(--motion-state) ease-out,
    transform var(--motion-state) ease-out;
}

.game-answer:hover:not(:disabled) {
  filter: saturate(1.12);
  transform: translateY(-1px);
}

.game-answer:disabled {
  opacity: 0.58;
  cursor: not-allowed;
}

.game-answer--male {
  border-color: var(--male);
  background: var(--male-tint);
  color: var(--male-text);
}

.game-answer--female {
  border-color: var(--female);
  background: var(--female-tint);
  color: var(--female-text);
}

.game-answer--unknown {
  border-color: var(--unknown);
  background: var(--unknown-tint);
  color: var(--unknown-text);
}

.game-answer--institution {
  border-color: var(--institution);
  background: var(--institution-tint);
  color: var(--institution-text);
}

.game-answer__key {
  position: absolute;
  inset-block-start: var(--space-2);
  inset-inline-end: var(--space-2);
  min-width: 1.5rem;
  padding-inline: var(--space-1);
  border: 1px solid currentColor;
  border-radius: var(--radius-control);
  font-family: var(--font-mono);
  font-size: var(--font-size-caption);
  line-height: 1.5;
  text-align: center;
}

.game-answer__label {
  font-family: var(--font-mono);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.game-decision__secondary,
.game-feedback__next,
.game-complete__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.game-decision__secondary span {
  color: var(--text-secondary);
}

.game-feedback__saved {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  color: var(--good);
  font-weight: var(--weight-semibold);
  font-size: inherit;
}

.game-feedback__machine {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.game-feedback__machine > span {
  color: var(--text-secondary);
}

.game-evidence {
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--surface-1);
}

.game-evidence summary {
  min-height: var(--control-min-size);
  font-weight: var(--weight-semibold);
  cursor: pointer;
}

.game-evidence__table {
  width: 100%;
  min-width: 34rem;
  margin-block-start: var(--space-3);
  border-collapse: collapse;
  font-variant-numeric: tabular-nums;
}

.game-evidence__table th,
.game-evidence__table td {
  padding: var(--space-2) var(--space-3);
  border-block-end: 1px solid var(--border);
  text-align: start;
}

.game-evidence__table thead th {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.game-feedback__next {
  justify-content: end;
  padding-block-start: var(--space-2);
}

.game-complete__stats {
  padding-block: var(--space-4);
  border-block: 1px dashed var(--border);
}

/* The companion follows completed records; evidence and controls never move with it. */
.game-hud__otter-lane {
  block-size: 5rem;
  margin-block-end: calc(-1 * var(--space-3));
  pointer-events: none;
}

.game-hud__otter-track {
  inline-size: calc(100% - 4rem);
  transform: translateX(var(--game-progress, 0%));
  transition: transform 300ms cubic-bezier(0.16, 1, 0.3, 1);
}

.game-hud__otter-track > .archive-otter {
  inline-size: 4rem;
}

.game-hud__score {
  position: relative;
}

.game-hud__points {
  position: absolute;
  inset-inline-start: 100%;
  margin-inline-start: var(--space-2);
  font-size: var(--font-size-small);
  animation: game-points 700ms ease-out both;
}

.game-feedback__stamp {
  display: inline-block;
  padding: var(--space-1) var(--space-2);
  border: 2px solid currentColor;
  border-radius: var(--radius-control);
  color: var(--accent);
  font-size: var(--font-size-caption);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  transform: rotate(-4deg);
  animation: game-saved-stamp 300ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

.game-complete {
  position: relative;
  border-color: color-mix(in srgb, var(--accent) 30%, var(--border));
  background: color-mix(in srgb, var(--accent) 3%, var(--panel));
}

.game-complete__illustration {
  position: relative;
  flex: none;
  inline-size: 7rem;
}

.game-complete__stars {
  position: absolute;
  inset: 0;
  inline-size: 100%;
  block-size: 100%;
  overflow: visible;
  color: var(--accent);
}

.game-paper-star {
  transform-box: fill-box;
  transform-origin: center;
  animation: game-paper-star 650ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

.game-paper-star--second {
  animation-delay: 70ms;
}

.game-paper-star--third {
  animation-delay: 140ms;
}

.game-complete__receipt {
  padding-inline-start: var(--space-3);
  border-inline-start: 1px solid var(--accent);
  color: var(--text-secondary);
}

@keyframes game-saved-stamp {
  from {
    transform: scale(1.16) rotate(-8deg);
    opacity: 0.5;
  }
  to {
    transform: scale(1) rotate(-4deg);
    opacity: 1;
  }
}

@keyframes game-points {
  0% {
    transform: translateY(var(--space-1));
    opacity: 0;
  }
  25%,
  65% {
    opacity: 1;
  }
  100% {
    transform: translateY(calc(-1 * var(--space-3)));
    opacity: 0;
  }
}

@keyframes game-paper-star {
  from {
    transform: translateY(var(--space-3)) rotate(-35deg) scale(0.6);
    opacity: 0;
  }
  to {
    transform: translateY(0) rotate(0deg) scale(1);
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .game-hud__otter-track {
    transition: none;
  }
  .game-feedback__stamp,
  .game-paper-star {
    animation: none;
  }
  .game-hud__points {
    display: none;
    animation: none;
  }
}

@media (max-width: 48rem) {
  .game-pool-options,
  .game-round-options {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 36rem) {
  .game-question__header {
    display: grid;
  }

  .game-complete__heading {
    flex-direction: column;
    align-items: start;
  }

  .game-answer-grid {
    grid-template-columns: 1fr;
  }

  .game-setup__start,
  .game-feedback__next {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
