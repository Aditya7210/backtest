import { useEffect, useMemo, useRef } from 'react';
import {
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

interface OverlaySeries {
  key: string;
  label: string;
  color: string;
  data: Array<{ time: number; value: number }>;
}

interface Props {
  bars: OHLCVBar[];
  symbol: string;
  overlays?: OverlaySeries[];
  markers?: Array<{
    time: number;
    position: 'aboveBar' | 'belowBar' | 'inBar';
    color: string;
    shape: 'arrowUp' | 'arrowDown' | 'circle' | 'square';
    text?: string;
  }>;
  onCrosshairTime?: (time: number | null) => void;
}

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
  overlays = [],
  markers = [],
  onCrosshairTime,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const overlayRefs = useRef<Array<{ key: string; series: ISeriesApi<'Line'> }>>([]);
  const data = useMemo(() => toSeriesData(bars), [bars]);

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
      timeScale: { borderColor: '#E5E7EB', timeVisible: true, secondsVisible: false },
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
      if (!onCrosshairTime) return;
      const t = param.time;
      if (typeof t === 'number') {
        onCrosshairTime(t);
      } else {
        onCrosshairTime(null);
      }
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
    };
  }, [onCrosshairTime]);

  useEffect(() => {
    if (!seriesRef.current) return;
    if (!data.length) {
      seriesRef.current.setData([]);
      const markerApi = seriesRef.current as unknown as {
        setMarkers?: (markers: Array<Record<string, unknown>>) => void;
      };
      markerApi.setMarkers?.([]);
      return;
    }
    seriesRef.current.setData(data);
    const markerApi = seriesRef.current as unknown as {
      setMarkers?: (markers: Array<Record<string, unknown>>) => void;
    };
    if (markers.length) {
      markerApi.setMarkers?.(
        markers.map((m) => ({
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
  }, [data, markers]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    for (const entry of overlayRefs.current) {
      chart.removeSeries(entry.series);
    }
    overlayRefs.current = [];

    for (const overlay of overlays) {
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
  }, [overlays]);

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
