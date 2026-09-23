import { useI18n } from 'vue-i18n'

/** Translate a `ProjectRole` (viewer/reviewer/operator) for display; shared by every project screen. */
export function useRoleLabel(): (role: string) => string {
  const { t } = useI18n()

  return (role: string): string => {
    switch (role) {
      case 'viewer':
        return t('projects.role.viewer')
      case 'reviewer':
        return t('projects.role.reviewer')
      case 'operator':
        return t('projects.role.operator')
      default:
        return role
    }
  }
}
