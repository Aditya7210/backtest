import type { LiveInstrumentItem } from '../../types/market';
import type { SearchableOption } from '../../components/SearchableDropdown';
import type { MarketViewFuture, MarketViewResponse as MarketViewPayload, MarketViewSide } from '../../types/market';

export type { MarketViewPayload };

function asObj(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' ? (v as Record<string, unknown>) : {};
}

function asNum(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string') {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function asText(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

function parseSide(raw: unknown): MarketViewSide {
  const src = asObj(raw);
  const spotObj = asObj(src.spot);
  const spot = Object.keys(spotObj).length
    ? {
        price: asNum(spotObj.price),
        tradingsymbol: asText(spotObj.tradingsymbol),
        updated_at: asText(spotObj.updated_at) || null,
      }
    : null;

  const futuresRaw = Array.isArray(src.futures) ? src.futures : [];
  const futures = futuresRaw
    .map((row) => {
      const rec = asObj(row);
      return {
        price: asNum(rec.price),
        tradingsymbol: asText(rec.tradingsymbol),
        expiry: asText(rec.expiry) || null,
        oi: asNum(rec.oi) ?? 0,
        updated_at: asText(rec.updated_at) || null,
      } satisfies MarketViewFuture;
    })
    .sort((a, b) => String(a.expiry || '').localeCompare(String(b.expiry || '')));

  return { spot, futures };
}

export function parseMarketViewPayload(raw: unknown): MarketViewPayload {
  const root = asObj(raw);
  const marketViewRoot = asObj(root.market_view);
  return {
    generated_at: asText(root.generated_at) || null,
    market_view: {
      NIFTY: parseSide(marketViewRoot.NIFTY),
      BANKNIFTY: parseSide(marketViewRoot.BANKNIFTY),
    },
  };
}

export function basisFromSpotAndFuture(spot: number | null, future: number | null): number | null {
  if (spot == null || future == null) return null;
  return future - spot;
}

export function buildInventoryOptions(items: LiveInstrumentItem[], showOptionsInDropdown: boolean): SearchableOption[] {
  const typeOrder = (instrumentType: string): number => {
    const t = String(instrumentType || '').toLowerCase();
    if (t === 'index') return 0;
    if (t === 'future') return 1;
    if (t === 'vix') return 2;
    if (t === 'option') return 3;
    return 4;
  };

  return items
    .filter((item) => showOptionsInDropdown || String(item.instrument_type).toLowerCase() !== 'option')
    .slice()
    .sort((a, b) => {
      const rank = typeOrder(a.instrument_type) - typeOrder(b.instrument_type);
      if (rank !== 0) return rank;
      return String(a.tradingsymbol).localeCompare(String(b.tradingsymbol));
    })
    .map((item) => {
      const type = String(item.instrument_type || '').toLowerCase();
      const tag = type === 'index' ? '[SPOT]' : type === 'future' ? '[FUT]' : type === 'vix' ? '[VIX]' : '[OPT]';
      const expiry = item.expiry ? ` ${item.expiry}` : '';
      return {
        id: `${item.instrument_token}|${item.timeframe}|${item.trading_date}`,
        label: `${tag} ${item.tradingsymbol}${expiry}`,
        searchText: `${item.instrument_token} ${item.tradingsymbol} ${item.underlying || ''} ${item.expiry || ''} ${item.option_type || ''} ${item.instrument_type || ''}`,
      } satisfies SearchableOption;
    });
}
