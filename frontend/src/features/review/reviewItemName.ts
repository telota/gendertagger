import type { ReviewItem } from './useReviewData'

/** "Surname, Forenames", falling back to whichever part exists and finally to the TEI id. */
export function reviewItemName(item: Pick<ReviewItem, 'surname' | 'forenames' | 'tei_id'>): string {
  const forenames = (item.forenames ?? []).join(' ')
  if (item.surname && forenames) return `${item.surname}, ${forenames}`
  return item.surname ?? (forenames || item.tei_id)
}
