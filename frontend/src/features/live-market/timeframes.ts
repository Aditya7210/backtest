import type { LiveTimeframe } from '../../types/market';

export const LIVE_TIMEFRAMES: LiveTimeframe[] = [
  '1min',
  '3min',
  '5min',
  '10min',
  '15min',
  '20min',
  '30min',
  '45min',
  '60min',
  '1day',
];

export function timeframeBucketSeconds(tf: LiveTimeframe): number {
  if (tf === '1day') return 24 * 60 * 60;
  return Number(tf.replace('min', '')) * 60;
}
