"use client";

import { track } from "@vercel/analytics";
import {
  ArrowDown,
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  CirclePause,
  CirclePlay,
  CopyCheck,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useReducer, useRef } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  initialReplayState,
  playbackInterval,
  replayReducer,
  type ReplaySpeed,
} from "@/lib/replay-machine";
import type { DemoReplay, ReplayStep } from "@/lib/replay-schema";

type ReplayWalkthroughProps = {
  replay: DemoReplay;
};

function formatTimestamp(timestamp: string): string {
  return `${timestamp.split("T")[1]?.replace("Z", "")} UTC`;
}

function formatBalance(value: string | undefined): string {
  if (value === undefined) return "—";
  return Number(value).toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
}

function StageConnector() {
  return (
    <div className="stage-connector" aria-hidden="true">
      <ArrowRight className="connector-horizontal" />
      <ArrowDown className="connector-vertical" />
    </div>
  );
}

function QueueStrip({ value }: { value: string }) {
  const numeric = Math.max(0, Math.min(25, Number(value)));
  return (
    <div className="queue-strip" aria-label={`${numeric} tokens ahead in queue`}>
      <div className="queue-track" aria-hidden="true">
        <span style={{ transform: `scaleX(${numeric / 25})` }} />
      </div>
      <span className="mono queue-value">{numeric} / 25</span>
    </div>
  );
}

function OrderBookStage({ step }: { step: ReplayStep }) {
  const buyOrder = step.orders.find((order) => order.side === "BUY");

  return (
    <article className="causal-stage book-stage">
      <div className="stage-heading">
        <span className="stage-number">1</span>
        <div>
          <h3>Observed L2</h3>
          <p>What the simulator can actually see</p>
        </div>
      </div>

      {step.book ? (
        <>
          <div className="book-columns" aria-label="Level 2 order book">
            <div>
              <span className="book-side buy-text">Bids</span>
              {step.book.bids.map((level) => (
                <div className="book-level" key={`bid-${level.price}`}>
                  <span className="mono">{level.price}</span>
                  <span className="mono">{level.size}</span>
                </div>
              ))}
            </div>
            <div>
              <span className="book-side sell-text">Asks</span>
              {step.book.asks.map((level) => (
                <div className="book-level" key={`ask-${level.price}`}>
                  <span className="mono">{level.price}</span>
                  <span className="mono">{level.size}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="stage-detail">
            <div className="detail-row">
              <span>Virtual BUY</span>
              <strong className="mono">
                {buyOrder ? `${buyOrder.size} @ ${buyOrder.price}` : "pending"}
              </strong>
            </div>
            <span className="detail-label">Queue ahead</span>
            <QueueStrip value={buyOrder?.queue_ahead ?? "0"} />
          </div>
        </>
      ) : (
        <div className="stage-empty">
          <span className="pulse-dot" aria-hidden="true" />
          Waiting for the first two-sided book snapshot.
        </div>
      )}
    </article>
  );
}

function TradeStage({ step }: { step: ReplayStep }) {
  const consumed = step.queue_consumed_delta;
  const residual = step.trade
    ? Math.max(0, Number(step.trade.size) - Number(consumed))
    : 0;

  return (
    <article className="causal-stage trade-stage">
      <div className="stage-heading">
        <span className="stage-number">2</span>
        <div>
          <h3>Aggressor trade</h3>
          <p>The only event allowed to advance queue</p>
        </div>
      </div>

      {step.trade ? (
        <div className="trade-body">
          <div className="trade-ticket">
            <Badge
              className={step.trade.side === "BUY" ? "buy-badge" : "sell-badge"}
            >
              {step.trade.side}
            </Badge>
            <strong className="mono">{step.trade.size}</strong>
            <span className="mono muted">@ {step.trade.price}</span>
          </div>
          <div className="trade-math" aria-label="Trade volume allocation">
            {step.trade.duplicate ? (
              <>
                <CopyCheck aria-hidden="true" />
                <strong>Already processed</strong>
                <span>No queue movement. No second fill.</span>
              </>
            ) : (
              <>
                <span className="mono">{step.trade.size}</span>
                <span className="math-operator">−</span>
                <span className="mono">{consumed} queue</span>
                <span className="math-operator">=</span>
                <strong className="mono">{residual} eligible</strong>
              </>
            )}
          </div>
          <div className="detail-row trade-id">
            <span>Exchange trade ID</span>
            <strong className="mono">{step.trade.trade_id}</strong>
          </div>
        </div>
      ) : (
        <div className="stage-empty">
          <span className="pulse-dot" aria-hidden="true" />
          No aggressor trade has reached the replay yet.
        </div>
      )}
    </article>
  );
}

function ResultStage({ step }: { step: ReplayStep }) {
  const fill = step.fills[0];
  const buyOrder = step.orders.find((order) => order.side === "BUY");

  return (
    <article className="causal-stage result-stage">
      <div className="stage-heading">
        <span className="stage-number">3</span>
        <div>
          <h3>Virtual result</h3>
          <p>Spot-safe ledger after this event</p>
        </div>
      </div>

      {step.duplicate_ignored ? (
        <div className="result-message pass-message">
          <ShieldCheck aria-hidden="true" />
          <div>
            <strong>Duplicate safely ignored</strong>
            <span>All remaining reservations released.</span>
          </div>
        </div>
      ) : fill ? (
        <div className="fill-result">
          <span className="fill-label">Partial fill</span>
          <div className="fill-amount">
            <strong className="mono">{fill.size}</strong>
            <span className="mono">{fill.side} @ {fill.price}</span>
          </div>
          <div className="detail-row">
            <span>Remaining order</span>
            <strong className="mono">
              {step.orders.find((order) => order.order_ref === fill.order_ref)
                ?.remaining ?? "0"}
            </strong>
          </div>
        </div>
      ) : (
        <div className="result-message">
          <span className="pulse-dot" aria-hidden="true" />
          <div>
            <strong>{buyOrder?.status ?? "No fill yet"}</strong>
            <span>
              {buyOrder
                ? `${buyOrder.queue_ahead} visible tokens remain ahead.`
                : "The ledger is ready; no order has been submitted."}
            </span>
          </div>
        </div>
      )}

      <div className="mini-ledger">
        <div>
          <span>Available USDC</span>
          <strong className="mono">
            {formatBalance(step.wallet.available_balances.USDC)}
          </strong>
        </div>
        <div>
          <span>Reserved USDC</span>
          <strong className="mono">
            {formatBalance(step.wallet.reserved_balances.USDC)}
          </strong>
        </div>
        <div>
          <span>Token inventory</span>
          <strong className="mono">
            {formatBalance(step.wallet.available_balances["#8050"])}
          </strong>
        </div>
      </div>
    </article>
  );
}

export function ReplayWalkthrough({ replay }: ReplayWalkthroughProps) {
  const [state, dispatch] = useReducer(replayReducer, initialReplayState);
  const completionTracked = useRef(false);
  const lastIndex = replay.steps.length - 1;
  const step = replay.steps[state.index];

  useEffect(() => {
    const start = () => {
      completionTracked.current = false;
      dispatch({ type: "reset" });
      dispatch({ type: "play" });
    };
    window.addEventListener("hip4-replay-start", start);
    return () => window.removeEventListener("hip4-replay-start", start);
  }, []);

  useEffect(() => {
    if (!state.isPlaying) return;
    const timer = window.setTimeout(() => {
      dispatch({ type: "next", lastIndex });
    }, playbackInterval(state.speed));
    return () => window.clearTimeout(timer);
  }, [lastIndex, state.index, state.isPlaying, state.speed]);

  useEffect(() => {
    if (state.index === lastIndex && !completionTracked.current) {
      completionTracked.current = true;
      track("replay_completed");
    }
  }, [lastIndex, state.index]);

  const togglePlayback = () => {
    if (state.isPlaying) {
      dispatch({ type: "pause" });
      return;
    }
    if (state.index === lastIndex) {
      completionTracked.current = false;
      dispatch({ type: "reset" });
    }
    track("replay_started");
    dispatch({ type: "play" });
  };

  return (
    <section className="replay-section" id="replay" aria-labelledby="replay-title">
      <div className="replay-heading-row">
        <div>
          <h2 id="replay-title">One fixture. Every causal step.</h2>
          <p>
            This six-event recording is replayed through the actual Python
            engine. TypeScript only renders the resulting trace.
          </p>
        </div>
        <Badge variant="outline" className="fixture-badge">
          <span className="mono">#8050</span> · short fixture
        </Badge>
      </div>

      <div className="replay-shell">
        <div className="replay-toolbar">
          <div className="playback-controls" aria-label="Replay controls">
            <Tooltip>
              <TooltipTrigger
                render={
                  <Button
                    variant="outline"
                    size="icon-lg"
                    aria-label="Previous event"
                    disabled={state.index === 0}
                    onClick={() => dispatch({ type: "previous" })}
                  />
                }
              >
                <ChevronLeft aria-hidden="true" />
              </TooltipTrigger>
              <TooltipContent>Previous event</TooltipContent>
            </Tooltip>

            <Button className="play-button" size="lg" onClick={togglePlayback}>
              {state.isPlaying ? (
                <CirclePause aria-hidden="true" />
              ) : (
                <CirclePlay aria-hidden="true" />
              )}
              {state.isPlaying ? "Pause" : state.index === lastIndex ? "Replay" : "Play"}
            </Button>

            <Tooltip>
              <TooltipTrigger
                render={
                  <Button
                    variant="outline"
                    size="icon-lg"
                    aria-label="Next event"
                    disabled={state.index === lastIndex}
                    onClick={() => dispatch({ type: "next", lastIndex })}
                  />
                }
              >
                <ChevronRight aria-hidden="true" />
              </TooltipTrigger>
              <TooltipContent>Next event</TooltipContent>
            </Tooltip>

            <Tooltip>
              <TooltipTrigger
                render={
                  <Button
                    variant="ghost"
                    size="icon-lg"
                    aria-label="Reset replay"
                    onClick={() => dispatch({ type: "reset" })}
                  />
                }
              >
                <RotateCcw aria-hidden="true" />
              </TooltipTrigger>
              <TooltipContent>Reset replay</TooltipContent>
            </Tooltip>
          </div>

          <div className="event-readout">
            <span className="mono">
              Event {state.index + 1} / {replay.steps.length}
            </span>
            <span className="toolbar-rule" aria-hidden="true" />
            <span className="mono muted">{formatTimestamp(step.timestamp)}</span>
          </div>

          <Select
            value={String(state.speed)}
            onValueChange={(value) => {
              const speed = Number(value) as ReplaySpeed;
              if ([0.5, 1, 2].includes(speed)) {
                dispatch({ type: "set-speed", speed });
              }
            }}
          >
            <SelectTrigger className="speed-select" aria-label="Playback speed">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="0.5">0.5×</SelectItem>
              <SelectItem value="1">1×</SelectItem>
              <SelectItem value="2">2×</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="event-narrative" aria-live="polite">
          <div>
            <Badge variant="secondary">{step.kind}</Badge>
            {step.duplicate_ignored && (
              <Badge className="pass-badge"><Check /> guarded</Badge>
            )}
          </div>
          <h3>{step.headline}</h3>
          <p>{step.explanation}</p>
        </div>

        <div className="causal-flow">
          <OrderBookStage step={step} />
          <StageConnector />
          <TradeStage step={step} />
          <StageConnector />
          <ResultStage step={step} />
        </div>

        <ol className="event-rail" aria-label="Replay events">
          {replay.steps.map((item, index) => (
            <li key={item.sequence}>
              <button
                aria-current={index === state.index ? "step" : undefined}
                aria-label={`Go to event ${index + 1}: ${item.headline}`}
                onClick={() => dispatch({ type: "seek", index })}
              >
                <span className="event-dot" aria-hidden="true" />
                <span className="event-index mono">{index + 1}</span>
                <span className="event-kind">{item.kind}</span>
              </button>
            </li>
          ))}
        </ol>

        <div className="trace-proof">
          <span>Generated from fixture</span>
          <code>{replay.source_sha256}</code>
          <span className="trace-version">engine v{replay.engine_version}</span>
        </div>
      </div>
    </section>
  );
}
