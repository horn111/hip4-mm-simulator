import {
  ArrowUpRight,
  Check,
  CircleDot,
  Clock3,
  Code2,
  ExternalLink,
  FileCheck2,
  GitFork,
  Package,
  ShieldCheck,
} from "lucide-react";

import { ReplayWalkthrough } from "@/components/replay-walkthrough";
import { ReplayLaunchLink, TrackedLink } from "@/components/tracked-link";
import { Badge } from "@/components/ui/badge";
import { replayData, validationData } from "@/lib/data";
import { links } from "@/lib/links";

const totalEvents =
  validationData.metadata_events +
  validationData.book_events +
  validationData.trade_events;

const metrics = [
  { value: totalEvents.toLocaleString("en-US"), label: "recorded events" },
  {
    value: validationData.book_events.toLocaleString("en-US"),
    label: "L2 snapshots",
  },
  {
    value: validationData.trade_events.toLocaleString("en-US"),
    label: "trade messages",
  },
  { value: String(validationData.fills), label: "simulated fills" },
  {
    value: validationData.duplicate_trades_ignored.toLocaleString("en-US"),
    label: "duplicate IDs ignored",
  },
];

function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <span />
      <span />
      <span />
      <span />
      <span />
    </span>
  );
}

function ExternalAction({
  href,
  eventName,
  icon,
  children,
}: {
  href: string;
  eventName: "github_opened" | "pypi_opened" | "report_opened";
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <TrackedLink
      className="external-action"
      eventName={eventName}
      href={href}
      target="_blank"
      rel="noreferrer"
    >
      {icon}
      <span>{children}</span>
      <ArrowUpRight className="action-arrow" aria-hidden="true" />
    </TrackedLink>
  );
}

export default function Home() {
  return (
    <>
      <header className="site-header">
        <div className="site-container header-inner">
          <a className="brand" href="#top" aria-label="HIP-4 MM Simulator home">
            <BrandMark />
            <span>HIP-4 MM Simulator</span>
          </a>
          <nav aria-label="Primary navigation">
            <a href="#validation">24h validation</a>
            <TrackedLink
              eventName="github_opened"
              href={links.github}
              target="_blank"
              rel="noreferrer"
            >
              <GitFork aria-hidden="true" />
              GitHub
            </TrackedLink>
          </nav>
        </div>
      </header>

      <main id="top">
        <section className="hero site-container">
          <div className="hero-copy">
            <Badge variant="outline" className="release-badge">
              v0.2.0 · experimental alpha
            </Badge>
            <h1>See exactly when a HIP-4 paper order earns a fill.</h1>
            <p className="hero-lede">
              A deterministic execution simulator that seeds queue-ahead from
              observed L2 and advances it only with aggressor trades.
            </p>
            <div className="hero-actions">
              <ReplayLaunchLink className="primary-action" />
              <TrackedLink
                className="secondary-action"
                eventName="report_opened"
                href={links.validation}
                target="_blank"
                rel="noreferrer"
              >
                Read the 24h validation
                <ArrowUpRight aria-hidden="true" />
              </TrackedLink>
            </div>
            <p className="hero-caveat">
              No live orders. No hidden liquidity assumptions. No profitability
              claim.
            </p>
          </div>

          <aside className="model-sequence" aria-label="Execution model summary">
            <div className="sequence-intro">
              <CircleDot aria-hidden="true" />
              <p>
                <strong>The missing layer is execution.</strong>
                SDKs reach the market. This simulator tests whether a passive
                order should have filled.
              </p>
            </div>
            <ol>
              <li>
                <span>1</span>
                <div>
                  <strong>Observe the book</strong>
                  <p>Join behind visible size at the order&apos;s price.</p>
                </div>
              </li>
              <li>
                <span>2</span>
                <div>
                  <strong>Conserve trade volume</strong>
                  <p>Only aggressor trades consume queue and virtual orders.</p>
                </div>
              </li>
              <li>
                <span>3</span>
                <div>
                  <strong>Audit the ledger</strong>
                  <p>Every reservation, fill, balance, and invariant is exposed.</p>
                </div>
              </li>
            </ol>
          </aside>
        </section>

        <div className="site-container">
          <ReplayWalkthrough replay={replayData} />
        </div>

        <section className="validation-section" id="validation">
          <div className="site-container">
            <div className="validation-intro">
              <div>
                <Badge variant="outline" className="mainnet-badge">
                  <Clock3 aria-hidden="true" /> 24h mainnet run
                </Badge>
                <h2>A longer run tests the invariants, not the alpha.</h2>
              </div>
              <p>
                From July 13–14, 2026, the recorder followed coin <code>#8220</code>
                for a full wall-clock day. The aggregate report is public; the raw
                recording remains outside git and is anchored by its SHA-256.
              </p>
            </div>

            <div className="evidence-layout">
              <div className="metric-ledger" aria-label="24-hour validation metrics">
                {metrics.map((metric) => (
                  <div className="metric-row" key={metric.label}>
                    <strong className="mono">{metric.value}</strong>
                    <span>{metric.label}</span>
                  </div>
                ))}
              </div>

              <div className="invariant-ledger">
                <div className="ledger-heading">
                  <ShieldCheck aria-hidden="true" />
                  <div>
                    <h3>All release invariants passed</h3>
                    <p>Checked after deterministic replay and final cancellation.</p>
                  </div>
                </div>
                <ul>
                  {Object.entries(validationData.invariants).map(([name]) => (
                    <li key={name}>
                      <Check aria-hidden="true" />
                      <code>{name}</code>
                      <span>PASS</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="reproducibility-block">
              <div className="repro-copy">
                <FileCheck2 aria-hidden="true" />
                <div>
                  <h3>Exact reproducibility</h3>
                  <p>
                    The same JSONL replay produces byte-identical JSON reports.
                  </p>
                </div>
              </div>
              <dl>
                <div>
                  <dt>Coin / quote</dt>
                  <dd className="mono">{validationData.coin} / {validationData.quote_token}</dd>
                </div>
                <div>
                  <dt>Source SHA-256</dt>
                  <dd><code>{validationData.source_sha256}</code></dd>
                </div>
                <div>
                  <dt>Window</dt>
                  <dd className="mono">2026-07-13 19:21 UTC → 2026-07-14 19:21 UTC</dd>
                </div>
              </dl>
              <TrackedLink
                className="report-link"
                eventName="report_opened"
                href={links.validation}
                target="_blank"
                rel="noreferrer"
              >
                Open the complete validation report
                <ExternalLink aria-hidden="true" />
              </TrackedLink>
              <details className="accounting-detail">
                <summary>Show baseline accounting output</summary>
                <p>
                  Final NAV <code>{validationData.final_nav}</code> · PnL{" "}
                  <code>{validationData.pnl}</code>. This is a baseline accounting
                  output, not an alpha claim or estimate of live performance.
                </p>
              </details>
            </div>
          </div>
        </section>

        <section className="boundaries-section site-container">
          <div className="boundaries-copy">
            <Badge variant="outline">Model boundaries</Badge>
            <h2>What this does not prove.</h2>
            <p>
              L2 cannot reveal exact order-level causality. The simulator stays
              deliberately conservative and publishes where the model stops.
            </p>
          </div>
          <ul className="limitations-list">
            {validationData.limitations.map((limitation) => (
              <li key={limitation}>
                <span aria-hidden="true" />
                {limitation}
              </li>
            ))}
          </ul>
        </section>

        <section className="handoff-section">
          <div className="site-container handoff-inner">
            <div>
              <h2>Inspect the assumptions. Challenge the trace.</h2>
              <p>
                The useful contribution is a reproducible edge case, not a star.
              </p>
            </div>
            <div className="handoff-actions">
              <ExternalAction
                href={links.github}
                eventName="github_opened"
                icon={<GitFork aria-hidden="true" />}
              >
                Source on GitHub
              </ExternalAction>
              <ExternalAction
                href={links.pypi}
                eventName="pypi_opened"
                icon={<Package aria-hidden="true" />}
              >
                Install from PyPI
              </ExternalAction>
              <ExternalAction
                href={links.validation}
                eventName="report_opened"
                icon={<FileCheck2 aria-hidden="true" />}
              >
                Validation report
              </ExternalAction>
            </div>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="site-container footer-inner">
          <div className="brand footer-brand">
            <BrandMark />
            <span>HIP-4 MM Simulator</span>
          </div>
          <p>Experimental alpha · MIT licensed · package v0.2.0</p>
          <TrackedLink
            eventName="github_opened"
            href={links.github}
            target="_blank"
            rel="noreferrer"
          >
            <Code2 aria-hidden="true" /> horn111/hip4-mm-simulator
          </TrackedLink>
        </div>
      </footer>
    </>
  );
}
