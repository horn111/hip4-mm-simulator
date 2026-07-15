"use client";

import { track } from "@vercel/analytics";
import type { ComponentProps } from "react";

type TrackedLinkProps = ComponentProps<"a"> & {
  eventName:
    | "github_opened"
    | "pypi_opened"
    | "report_opened"
    | "replay_started";
};

export function TrackedLink({ eventName, onClick, ...props }: TrackedLinkProps) {
  return (
    <a
      {...props}
      onClick={(event) => {
        track(eventName);
        onClick?.(event);
      }}
    />
  );
}

export function ReplayLaunchLink({ className }: { className?: string }) {
  return (
    <TrackedLink
      className={className}
      eventName="replay_started"
      href="#replay"
      onClick={() => {
        window.dispatchEvent(new Event("hip4-replay-start"));
      }}
    >
      Run the 6-event replay
    </TrackedLink>
  );
}
