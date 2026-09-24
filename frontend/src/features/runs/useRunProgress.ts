import { useQueryClient } from '@tanstack/vue-query'
import { onScopeDispose, ref, watch, type Ref } from 'vue'

import { type components } from '@/api'

import { runExecutionsKey, runKey, type MethodExecutionSummary } from './useRunDetail'
import type { Run } from './useRuns'

type Progress = components['schemas']['Progress']

/**
 * Not in the OpenAPI document (the stream's response is an untyped `200`), so declared here from
 * `api/routes/run_events.py`. Every event is a complete state, never a delta.
 */
interface RunStateEvent {
  run_id: string
  status: Run['status']
  progress: Progress
}
interface MethodExecutionStateEvent {
  method_execution_id: string
  method_name: string
  status: MethodExecutionSummary['status']
  progress: Progress
}

export type RunStreamState = 'idle' | 'connecting' | 'live' | 'reconnecting' | 'ended'

const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30_000

function parse<T>(event: Event): T | null {
  try {
    const data: unknown = JSON.parse((event as MessageEvent<string>).data)
    return typeof data === 'object' && data !== null ? (data as T) : null
  } catch {
    return null
  }
}

/**
 * Live run progress over `GET /runs/{id}/events`, written into the same query cache the run and
 * execution queries read, so a screen never has two sources of truth.
 *
 * Persisted state is authoritative and the server keeps no event log (no `Last-Event-ID`), so:
 * - progress events patch the cached counts directly (cheap, no request);
 * - state changes and terminal events refetch the resource, which also brings timestamps and
 *   failure details the stream does not carry;
 * - every *re*-connection refetches, because events may have been missed in between.
 *
 * The server ends the stream at a terminal state and after a fixed maximum duration. The browser
 * reconnects by itself after a clean close or a network error; when the connection is refused
 * outright (`CLOSED`, e.g. an expired session) this retries with backoff and refetches through the
 * API client first, which is where an expired session is recovered.
 */
export function useRunProgress(runId: Ref<string>, enabled: Ref<boolean>) {
  const queryClient = useQueryClient()
  const state = ref<RunStreamState>('idle')

  let source: EventSource | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let attempt = 0
  let hasOpened = false

  function refetch(id: string): void {
    void queryClient.invalidateQueries({ queryKey: runKey(id) })
  }

  function patchRun(id: string, event: RunStateEvent): void {
    queryClient.setQueryData<Run>(runKey(id), (run) =>
      run ? { ...run, status: event.status, progress: event.progress } : run,
    )
  }

  function patchExecution(id: string, event: MethodExecutionStateEvent): void {
    queryClient.setQueryData<MethodExecutionSummary[]>(runExecutionsKey(id), (executions) =>
      executions?.map((execution) =>
        execution.id === event.method_execution_id
          ? { ...execution, status: event.status, progress: event.progress }
          : execution,
      ),
    )
  }

  function close(): void {
    if (retryTimer !== null) clearTimeout(retryTimer)
    retryTimer = null
    source?.close()
    source = null
  }

  function stop(next: RunStreamState = 'idle'): void {
    close()
    hasOpened = false
    attempt = 0
    state.value = next
  }

  function scheduleRetry(id: string): void {
    if (retryTimer !== null) return
    const delay = Math.min(RECONNECT_BASE_MS * 2 ** attempt, RECONNECT_MAX_MS)
    attempt += 1
    retryTimer = setTimeout(() => {
      retryTimer = null
      // Through the API client first: an expired session is recovered there, not in EventSource.
      refetch(id)
      connect(id)
    }, delay)
  }

  function connect(id: string): void {
    close()
    state.value = hasOpened ? 'reconnecting' : 'connecting'
    const stream = new EventSource(`/api/v1/runs/${id}/events`, { withCredentials: true })
    source = stream

    stream.onopen = () => {
      state.value = 'live'
      attempt = 0
      if (hasOpened) {
        refetch(id)
        void queryClient.invalidateQueries({ queryKey: runExecutionsKey(id) })
      }
      hasOpened = true
    }

    stream.onerror = () => {
      if (source !== stream) return
      state.value = 'reconnecting'
      if (stream.readyState === EventSource.CLOSED) {
        stream.close()
        source = null
        scheduleRetry(id)
      }
      // Otherwise the browser is already retrying on its own.
    }

    const onRunState = (event: Event): void => {
      const payload = parse<RunStateEvent>(event)
      if (payload) patchRun(id, payload)
    }
    const onExecutionState = (event: Event): void => {
      const payload = parse<MethodExecutionStateEvent>(event)
      if (payload) patchExecution(id, payload)
    }
    // Progress is patched in place; a state change also refetches for timestamps and failures.
    stream.addEventListener('run.progress', onRunState)
    stream.addEventListener('method_execution.progress', onExecutionState)
    stream.addEventListener('run.state_changed', (event) => {
      onRunState(event)
      refetch(id)
    })
    stream.addEventListener('method_execution.state_changed', (event) => {
      onExecutionState(event)
      void queryClient.invalidateQueries({ queryKey: runExecutionsKey(id) })
    })
    const onTerminal = (event: Event): void => {
      onRunState(event)
      refetch(id)
      void queryClient.invalidateQueries({ queryKey: runExecutionsKey(id) })
      stop('ended')
    }
    stream.addEventListener('run.completed', onTerminal)
    stream.addEventListener('run.failed', onTerminal)
  }

  watch(
    [runId, enabled],
    ([id, isEnabled], [previousId]) => {
      // A run that just ended disables the stream; its `ended` state must survive that, but not
      // a switch to another run.
      const keepEnded = state.value === 'ended' && id === previousId
      stop(keepEnded ? 'ended' : 'idle')
      if (isEnabled && id !== '' && !keepEnded) connect(id)
    },
    { immediate: true },
  )

  onScopeDispose(() => stop())

  return { state }
}
