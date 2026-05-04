import { useEffect, useMemo, useRef } from 'react';
import {
  isBusinessDay,
  ColorType,
  CrosshairMode,
  LineStyle,
  type LineData,
  type MouseEventParams,
  createChart,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from 'lightweight-charts';
import type { OHLCVBar } from '../types/market';
import { formatUnixIst } from '../features/time/ist';

interface OverlaySeries {
  key: string;
  label: string;
  color: string;
  data: Array<{ time: number; value: number }>;
}

interface CandleOverlaySeries {
  key: string;
  label: string;
  bars: OHLCVBar[];
  upColor?: string;
  downColor?: string;
}

interface Props {
  bars: OHLCVBar[];
  symbol: string;
  overlays?: OverlaySeries[];
  candleOverlays?: CandleOverlaySeries[];
  markers?: Array<{
    time: number;
    position: 'aboveBar' | 'belowBar' | 'inBar';
    color: string;
    shape: 'arrowUp' | 'arrowDown' | 'circle' | 'square';
    text?: string;
  }>;
  onCrosshairTime?: (time: number | null) => void;
  autoScroll?: boolean;
}

const EMPTY_OVERLAYS: OverlaySeries[] = [];
const EMPTY_CANDLE_OVERLAYS: CandleOverlaySeries[] = [];
const EMPTY_MARKERS: Array<{
  time: number;
  position: 'aboveBar' | 'belowBar' | 'inBar';
  color: string;
  shape: 'arrowUp' | 'arrowDown' | 'circle' | 'square';
  text?: string;
}> = [];

function toSeriesData(bars: OHLCVBar[]): CandlestickData<Time>[] {
  const sorted = [...bars].sort((a, b) => a.time - b.time);
  return sorted.map((bar) => ({
    time: bar.time as Time,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
  }));
}

export default function LightweightCandlestickChart({
  bars,
  symbol,
  overlays,
  candleOverlays,
  markers,
  onCrosshairTime,
  autoScroll = true,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const overlayRefs = useRef<Array<{ key: string; series: ISeriesApi<'Line'> }>>([]);
  const candleOverlayRefs = useRef<Array<{ key: string; series: ISeriesApi<'Candlestick'> }>>([]);
  const crosshairCbRef = useRef<Props['onCrosshairTime']>(onCrosshairTime);
  const overlaysSafe = overlays ?? EMPTY_OVERLAYS;
  const candleOverlaysSafe = candleOverlays ?? EMPTY_CANDLE_OVERLAYS;
  const markersSafe = markers ?? EMPTY_MARKERS;
  const data = useMemo(() => toSeriesData(bars), [bars]);

  useEffect(() => {
    crosshairCbRef.current = onCrosshairTime;
  }, [onCrosshairTime]);

  useEffect(() => {
    if (!containerRef.current) return;
    if (chartRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#FFFFFF' },
        textColor: '#374151',
      },
      grid: {
        vertLines: { color: '#EEF2F7' },
        horzLines: { color: '#EEF2F7' },
      },
      width: containerRef.current.clientWidth,
      height: 420,
      rightPriceScale: { borderColor: '#E5E7EB' },
      timeScale: {
        borderColor: '#E5E7EB',
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time: Time) => {
          if (typeof time === 'number') return formatUnixIst(time, 'time');
          if (isBusinessDay(time)) return `${time.day}/${time.month}`;
          return '';
        },
      },
      localization: {
        locale: 'en-IN',
        timeFormatter: (time: Time) => {
          if (typeof time === 'number') return formatUnixIst(time, 'datetime');
          if (isBusinessDay(time)) return `${time.year}-${String(time.month).padStart(2, '0')}-${String(time.day).padStart(2, '0')}`;
          return '';
        },
      },
      crosshair: { mode: CrosshairMode.Normal },
    });

    const series = chart.addCandlestickSeries({
      upColor: '#089981',
      downColor: '#F23645',
      borderUpColor: '#089981',
      borderDownColor: '#F23645',
      wickUpColor: '#089981',
      wickDownColor: '#F23645',
    });

    chartRef.current = chart;
    seriesRef.current = series;

    chart.subscribeCrosshairMove((param: MouseEventParams<Time>) => {
      const callback = crosshairCbRef.current;
      if (!callback) return;
      const t = param.time;
      if (typeof t === 'number') callback(t);
      else callback(null);
    });

    const ro = new ResizeObserver(() => {
      if (!containerRef.current || !chartRef.current) return;
      chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      overlayRefs.current = [];
      candleOverlayRefs.current = [];
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current) return;
    if (!data.length) {
      seriesRef.current.setData([]);
      const markerApi = seriesRef.current as unknown as {
        setMarkers?: (nextMarkers: Array<Record<string, unknown>>) => void;
      };
      markerApi.setMarkers?.([]);
      return;
    }
    seriesRef.current.setData(data);
    const markerApi = seriesRef.current as unknown as {
      setMarkers?: (nextMarkers: Array<Record<string, unknown>>) => void;
    };
    if (markersSafe.length) {
      markerApi.setMarkers?.(
        markersSafe.map((m) => ({
          time: m.time as Time,
          position: m.position,
          color: m.color,
          shape: m.shape,
          text: m.text,
        })),
      );
    } else {
      markerApi.setMarkers?.([]);
    }
    if (chartRef.current && autoScroll) {
      chartRef.current.timeScale().scrollToRealTime();
    }
  }, [autoScroll, data, markersSafe]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    for (const entry of candleOverlayRefs.current) {
      chart.removeSeries(entry.series);
    }
    candleOverlayRefs.current = [];

    for (const overlay of candleOverlaysSafe) {
      const candleSeries = chart.addCandlestickSeries({
        upColor: overlay.upColor ?? 'rgba(59,130,246,0.32)',
        downColor: overlay.downColor ?? 'rgba(239,68,68,0.28)',
        borderVisible: false,
        wickUpColor: overlay.upColor ?? 'rgba(59,130,246,0.45)',
        wickDownColor: overlay.downColor ?? 'rgba(239,68,68,0.4)',
        priceLineVisible: false,
        lastValueVisible: false,
        title: overlay.label,
      });
      candleSeries.setData(toSeriesData(overlay.bars));
      candleOverlayRefs.current.push({ key: overlay.key, series: candleSeries });
    }

    for (const entry of overlayRefs.current) {
      chart.removeSeries(entry.series);
    }
    overlayRefs.current = [];

    for (const overlay of overlaysSafe) {
      const lineSeries = chart.addLineSeries({
        color: overlay.color,
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        priceLineVisible: false,
        lastValueVisible: true,
        title: overlay.label,
      });
      const lineData: LineData<Time>[] = overlay.data
        .slice()
        .sort((a, b) => a.time - b.time)
        .map((point) => ({ time: point.time as Time, value: point.value }));
      lineSeries.setData(lineData);
      overlayRefs.current.push({ key: overlay.key, series: lineSeries });
    }

    chart.timeScale().fitContent();
  }, [candleOverlaysSafe, overlaysSafe]);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <span style={{ fontSize: '0.9rem', fontWeight: 600 }}>{symbol || 'Instrument'}</span>
        <span className="badge badge-neutral">TradingView Lightweight Charts</span>
      </div>
      <div ref={containerRef} className="chart-container" />
    </div>
  );
}
