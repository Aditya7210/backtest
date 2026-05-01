export interface IndicatorParamMeta {
  name: string;
  type: 'number' | 'string' | 'boolean';
  default?: number | string | boolean | null;
  min?: number;
  max?: number;
}

export interface IndicatorPreset {
  label: string;
  params: Record<string, number | string | boolean>;
}

export interface IndicatorMetadata {
  name: string;
  label: string;
  category: string;
  pane: 'price' | 'oscillator' | string;
  params: IndicatorParamMeta[];
  presets?: IndicatorPreset[];
}

export interface IndicatorSelection {
  id: string;
  name: string;
  label: string;
  pane: 'price' | 'oscillator' | string;
  params: Record<string, number | string | boolean>;
}

export interface IndicatorSeriesPoint {
  time: number;
  value: number;
}

export interface IndicatorSeries {
  id: string;
  name: string;
  label: string;
  pane: 'price' | 'oscillator' | string;
  params: Record<string, number | string | boolean>;
  color: string;
  points: IndicatorSeriesPoint[];
}

