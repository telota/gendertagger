import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'

export type GameRound = components['schemas']['GameRound']
export type GameRoundCreate = components['schemas']['GameRoundCreate']
export type GameRoundEvent =
  | { kind: 'answer'; annotation_id: string; elapsed_milliseconds: number }
  | { kind: 'skip'; elapsed_milliseconds: number }
export type GameRoundSize = GameRoundCreate['round_size']
export type GameLeaderboard = components['schemas']['GameLeaderboard']

const BASE_POINTS = 10

/** Match the official fixed score without trusting browser-authored timing or streak state. */
export function gameAnswerPoints(): number {
  return BASE_POINTS
}

export function formatGameDuration(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1_000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = String(totalSeconds % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
}

export function gameLeaderboardKey(projectId: string, roundSize: GameRoundSize) {
  return ['projects', projectId, 'game-leaderboard', roundSize] as const
}

export function useGameLeaderboard(
  projectId: Ref<string>,
  roundSize: Ref<GameRoundSize>,
  enabled: Ref<boolean>,
) {
  const client = useApiClient()
  return useQuery({
    queryKey: computed(() => gameLeaderboardKey(projectId.value, roundSize.value)),
    queryFn: () =>
      unwrap(
        client.GET('/api/v1/projects/{project_id}/game-leaderboard', {
          params: {
            path: { project_id: projectId.value },
            query: { round_size: roundSize.value, limit: 10 },
          },
        }),
      ),
    enabled,
  })
}

export function useSaveGameRound(projectId: Ref<string>) {
  const client = useApiClient()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (command: GameRoundCreate): Promise<GameRound> =>
      unwrap(
        client.POST('/api/v1/projects/{project_id}/game-rounds', {
          params: { path: { project_id: projectId.value } },
          body: command,
        }),
      ),
    onSuccess: (round) => {
      void queryClient.invalidateQueries({
        queryKey: gameLeaderboardKey(round.project_id, round.round_size),
      })
    },
  })
}
