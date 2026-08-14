import { get } from './request'
import type {
  RfmResponse,
  LifecycleResponse,
  Retention,
  PathResponse,
  ChannelResponse,
  PriceResponse,
  AssociationResponse,
  SegmentsResponse,
  DeviceResponse,
  FindingsResponse,
} from '@/types'

export const analysisApi = {
  rfm: () => get<RfmResponse>('/analysis/rfm'),
  lifecycle: () => get<LifecycleResponse>('/analysis/lifecycle'),
  cohort: () => get<Retention>('/analysis/cohort'),
  path: () => get<PathResponse>('/analysis/path'),
  channel: () => get<ChannelResponse>('/analysis/channel'),
  price: () => get<PriceResponse>('/analysis/price'),
  association: () => get<AssociationResponse>('/analysis/association'),
  segments: () => get<SegmentsResponse>('/analysis/segments'),
  device: () => get<DeviceResponse>('/analysis/device'),
  findings: () => get<FindingsResponse>('/analysis/findings'),
  meta: () => get<Record<string, unknown>>('/analysis/meta'),
}
