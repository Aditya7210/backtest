import type { LiveTick, OHLCVBar } from '../../types/market';
import type { LiveTimeframe } from '../../types/market';
import { timeframeBucketSeconds } from './timeframes';

export function applyLiveTickToBars(
  bars: OHLCVBar[],
  tick: LiveTick | null,
  timeframe: LiveTimeframe,
): OHLCVBar[] {
  if (!tick || !Number.isFinite(tick.last_price) || tick.time <= 0) return bars;
  const bucketSeconds = timeframeBucketSeconds(timeframe);
  const bucketStart = Math.floor(tick.time / bucketSeconds) * bucketSeconds;
  const price = Number(tick.last_price);
  if (!Number.isFinite(price)) return bars;

  const next = bars.slice();
  const last = next.length ? next[next.length - 1] : null;
  if (!last || last.time < bucketStart) {
    next.push({
      time: bucketStart,
      open: price,
      high: price,
      low: price,
      close: price,
      volume: 0,
      oi: tick.oi ?? null,
    });
    return next;
  }
  if (last.time > bucketStart) return next;

  next[next.length - 1] = {
    ...last,
    high: Math.max(last.high, price),
    low: Math.min(last.low, price),
    close: price,
    oi: tick.oi ?? last.oi ?? null,
  };
  return next;
}
