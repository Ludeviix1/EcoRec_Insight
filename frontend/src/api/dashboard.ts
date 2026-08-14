import { get } from './request'
import type { Overview, UserTrend, GmvTrend, BehaviorTrend, Funnel, Retention, Rankings } from '@/types'

export const dashboardApi = {
  overview: () => get<Overview>('/dashboard/overview'),
  userTrend: () => get<UserTrend>('/dashboard/user-trend'),
  gmvTrend: () => get<GmvTrend>('/dashboard/gmv-trend'),
  behaviorTrend: () => get<BehaviorTrend>('/dashboard/behavior-trend'),
  funnel: () => get<Funnel>('/dashboard/funnel'),
  retention: () => get<Retention>('/dashboard/retention'),
  rankings: (topN = 10) => get<Rankings>('/dashboard/rankings', { top_n: topN }),
}
