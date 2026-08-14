import { get } from './request'
import type { Page, ItemRow, Rankings, ItemStatistics } from '@/types'

export interface ItemDetail extends ItemRow {
  statistics: ItemStatistics
}

export const itemsApi = {
  list: (params: { keyword?: string; category_id?: string; on_shelf_only?: boolean; limit?: number; offset?: number } = {}) =>
    get<Page<ItemRow>>('/items', params),
  detail: (itemId: string) => get<ItemDetail>(`/items/${itemId}`),
  statistics: (itemId: string) => get<ItemStatistics>(`/items/${itemId}/statistics`),
  ranking: (topN = 10) => get<Rankings>('/items/ranking', { top_n: topN }),
}
