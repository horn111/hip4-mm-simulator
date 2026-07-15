import { describe, expect, it } from "vitest";

import {
  initialReplayState,
  playbackInterval,
  replayReducer,
} from "./replay-machine";

describe("replayReducer", () => {
  it("plays to the final step and stops", () => {
    let state = replayReducer(initialReplayState, { type: "play" });
    for (let index = 0; index < 5; index += 1) {
      state = replayReducer(state, { type: "next", lastIndex: 5 });
    }
    expect(state).toEqual({ index: 5, isPlaying: false, speed: 1 });
  });

  it("seeks, steps backwards, and preserves speed on reset", () => {
    let state = replayReducer(initialReplayState, {
      type: "set-speed",
      speed: 2,
    });
    state = replayReducer(state, { type: "seek", index: 4 });
    state = replayReducer(state, { type: "previous" });
    expect(state.index).toBe(3);
    expect(replayReducer(state, { type: "reset" })).toEqual({
      index: 0,
      isPlaying: false,
      speed: 2,
    });
  });

  it("maps speed to deterministic playback intervals", () => {
    expect(playbackInterval(0.5)).toBe(2400);
    expect(playbackInterval(1)).toBe(1200);
    expect(playbackInterval(2)).toBe(600);
  });
});
