import { z } from "zod";

const decimal = z.string().regex(/^-?\d+(?:\.\d+)?$/);
const side = z.enum(["BUY", "SELL"]);

const bookLevel = z.object({
  price: decimal,
  size: decimal,
  count: z.number().int().nonnegative(),
});

const book = z.object({
  coin: z.string(),
  bids: z.array(bookLevel),
  asks: z.array(bookLevel),
  timestamp: z.iso.datetime(),
});

const order = z.object({
  order_ref: z.string(),
  side,
  price: decimal,
  size: decimal,
  status: z.enum([
    "PENDING",
    "OPEN",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELLED",
    "REJECTED",
  ]),
  filled_size: decimal,
  remaining: decimal,
  queue_ahead: decimal,
  activated_at: z.iso.datetime().nullable(),
});

const fill = z.object({
  order_ref: z.string(),
  side,
  price: decimal,
  size: decimal,
  aggressor_trade_id: z.string().nullable(),
});

const trade = z.object({
  trade_id: z.string().nullable(),
  side,
  price: decimal,
  size: decimal,
  duplicate: z.boolean(),
});

const wallet = z.object({
  quote_token: z.string(),
  available_balances: z.record(z.string(), decimal),
  reserved_balances: z.record(z.string(), decimal),
  nav: decimal,
  initial_nav: decimal,
  pnl: decimal,
  timestamp: z.iso.datetime(),
});

const replaySummary = z.object({
  schema_version: z.string(),
  source_sha256: z.string().length(64),
  coin: z.string(),
  quote_token: z.string(),
  start: z.iso.datetime(),
  end: z.iso.datetime(),
  metadata_events: z.number().int(),
  book_events: z.number().int(),
  trade_events: z.number().int(),
  feed_gaps_over_5s: z.number().int(),
  orders_submitted: z.number().int(),
  orders_rejected: z.number().int(),
  fills: z.number().int(),
  filled_volume: decimal,
  queue_volume_consumed: decimal,
  duplicate_trades_ignored: z.number().int(),
  final_nav: decimal,
  pnl: decimal,
  invariants: z.record(z.string(), z.boolean()),
  limitations: z.array(z.string()),
});

export const demoReplaySchema = z.object({
  schema_version: z.literal("demo-1"),
  source_sha256: z.string().length(64),
  engine_version: z.literal("0.2.0"),
  parameters: z.record(z.string(), z.string()),
  steps: z.array(
    z.object({
      sequence: z.number().int().nonnegative(),
      kind: z.enum(["metadata", "book", "trade"]),
      timestamp: z.iso.datetime(),
      headline: z.string(),
      explanation: z.string(),
      book: book.nullable(),
      trade: trade.nullable(),
      orders: z.array(order),
      fills: z.array(fill),
      wallet,
      queue_consumed_delta: decimal,
      duplicate_ignored: z.boolean(),
    }),
  ),
  summary: replaySummary,
});

export const validationSchema = replaySummary;

export type DemoReplay = z.infer<typeof demoReplaySchema>;
export type ReplayStep = DemoReplay["steps"][number];
export type ValidationReport = z.infer<typeof validationSchema>;
