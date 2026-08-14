import { get } from './request'
import type { Page, ItemRow, Rankings, ItemStatistics } from '@/types'

export interface ItemDetail extends ItemRow {
  statistics: ItemStatistics
}

export type ItemListParams = {
  keyword?: string
  category_id?: string
  brand?: string
  status?: 0 | 1
  sort_by?: 'brand' | 'price' | 'stock'
  order?: 'asc' | 'desc'
  on_shelf_only?: boolean
  limit?: number
  offset?: number
}

export const itemsApi = {
  list: (params: ItemListParams = {}) =>
    get<Page<ItemRow>>('/items', params),
  detail: (itemId: string) => get<ItemDetail>(`/items/${itemId}`),
  statistics: (itemId: string) => get<ItemStatistics>(`/items/${itemId}/statistics`),
  ranking: (topN = 10) => get<Rankings>('/items/ranking', { top_n: topN }),
}
