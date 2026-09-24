import { useI18n } from 'vue-i18n'

/**
 * One label per lifecycle status shared by runs, method executions and aggregations. Written as a
 * switch because the i18n lint rule requires every message key to appear literally in the source.
 */
export function useStatusLabel(): (status: string) => string {
  const { t } = useI18n()

  return (status) => {
    switch (status) {
      case 'created':
        return t('runs.status.created')
      case 'pending':
        return t('runs.status.pending')
      case 'queued':
        return t('runs.status.queued')
      case 'running':
        return t('runs.status.running')
      case 'completed':
        return t('runs.status.completed')
      case 'completed_with_errors':
        return t('runs.status.completedWithErrors')
      case 'failed':
        return t('runs.status.failed')
      case 'cancelled':
        return t('runs.status.cancelled')
    }
    return status
  }
}
