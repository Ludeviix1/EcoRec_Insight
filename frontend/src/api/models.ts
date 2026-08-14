import { get } from './request'
import type { ModelDetail, ModelsMetrics } from '@/types'

export const modelsApi = {
  purchase: () => get<ModelDetail>('/models/purchase'),
  churn: (limit = 50) => get<ModelDetail>('/models/churn', { limit }),
  metrics: () => get<ModelsMetrics>('/models/metrics'),
}
