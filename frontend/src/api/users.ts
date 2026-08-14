import { get } from './request'
import type { Page, UserRow, UserDetail, UserProfile, UserBehaviorPage, OrderPage, RecResult } from '@/types'

export const usersApi = {
  list: (params: { keyword?: string; limit?: number; offset?: number } = {}) =>
    get<Page<UserRow>>('/users', params),
  detail: (userId: string) => get<UserDetail>(`/users/${userId}`),
  profile: (userId: string) => get<UserProfile>(`/users/${userId}/profile`),
  behaviors: (userId: string, limit = 100) =>
    get<UserBehaviorPage>(`/users/${userId}/behaviors`, { limit }),
  orders: (userId: string) => get<OrderPage>(`/users/${userId}/orders`),
  recommendations: (userId: string, algorithm = 'popular', topK = 10) =>
    get<RecResult>(`/users/${userId}/recommendations`, { algorithm, top_k: topK }),
  prediction: (userId: string) =>
    get<{ user_id: string; purchase: unknown; churn: unknown }>(`/users/${userId}/prediction`),
}
