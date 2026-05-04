import { useEffect, useRef } from 'react';
import {
  isBusinessDay,
  ColorType,
  LineStyle,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
} from 'lightweight-charts';
import { formatUnixIst } from '../features/time/ist';

export interface LinePoint {
  time: number;
  value: number;
}

export interface LineSeriesConfig {
  id: string;
  label: string;
  color: string;
  data: LinePoint[];
}

interface Props {
  title: string;
  series: LineSeriesConfig[];
  height?: number;
}

export default function LightweightLineChart({ title, series, height = 260 }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRefs = useRef<Array<{ id: string; api: ISeriesApi<'Line'> }>>([]);

  useEffect(() => {
    if (!containerRef.current || chartRef.current) return;
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
      height,
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
    });
    chartRef.current = chart;

    const ro = new ResizeObserver(() => {
      if (!containerRef.current || !chartRef.current) return;
      chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRefs.current = [];
    };
  }, [height]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    for (const item of seriesRefs.current) {
      chart.removeSeries(item.api);
    }
    seriesRefs.current = [];

    for (const cfg of series) {
      const s = chart.addLineSeries({
        color: cfg.color,
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        priceLineVisible: false,
        lastValueVisible: true,
        title: cfg.label,
      });
      const lineData: LineData<Time>[] = cfg.data
        .slice()
        .sort((a, b) => a.time - b.time)
        .map((p) => ({ time: p.time as Time, value: p.value }));
      s.setData(lineData);
      seriesRefs.current.push({ id: cfg.id, api: s });
    }
    chart.timeScale().fitContent();
  }, [series]);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <span style={{ fontSize: '0.9rem', fontWeight: 600 }}>{title}</span>
        <span className="badge badge-neutral">TradingView Lightweight Charts</span>
      </div>
      <div ref={containerRef} className="chart-container" />
    </div>
  );
}
