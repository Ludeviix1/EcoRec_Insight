import { get } from './request'
import type { RecResult, RecCompare, RecMetrics } from '@/types'

export const ALGORITHMS = ['popular', 'itemcf', 'usercf', 'content', 'hybrid'] as const
export type Algorithm = (typeof ALGORITHMS)[number]

export const ALGORITHM_LABELS: Record<Algorithm, string> = {
  popular: '热门推荐',
  itemcf: '物品协同过滤',
  usercf: '用户协同过滤',
  content: '内容推荐',
  hybrid: '混合推荐',
}

export const recommendationsApi = {
  recommend: (userId: string, algorithm: Algorithm | string = 'popular', topK = 10) =>
    get<RecResult>(`/recommendations/${userId}`, { algorithm, top_k: topK }),
  compare: (userId: string, algorithms?: string[], topK = 10) =>
    get<RecCompare>(`/recommendations/${userId}/compare`, { algorithms: algorithms?.join(','), top_k: topK }),
  metrics: () => get<RecMetrics>('/recommendations/metrics'),
}
