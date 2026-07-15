export type ReplaySpeed = 0.5 | 1 | 2;

export type ReplayState = {
  index: number;
  isPlaying: boolean;
  speed: ReplaySpeed;
};

export type ReplayAction =
  | { type: "play" }
  | { type: "pause" }
  | { type: "next"; lastIndex: number }
  | { type: "previous" }
  | { type: "seek"; index: number }
  | { type: "reset" }
  | { type: "set-speed"; speed: ReplaySpeed };

export const initialReplayState: ReplayState = {
  index: 0,
  isPlaying: false,
  speed: 1,
};

export function replayReducer(
  state: ReplayState,
  action: ReplayAction,
): ReplayState {
  switch (action.type) {
    case "play":
      return { ...state, isPlaying: true };
    case "pause":
      return { ...state, isPlaying: false };
    case "next": {
      const index = Math.min(state.index + 1, action.lastIndex);
      return {
        ...state,
        index,
        isPlaying: index < action.lastIndex && state.isPlaying,
      };
    }
    case "previous":
      return {
        ...state,
        index: Math.max(0, state.index - 1),
        isPlaying: false,
      };
    case "seek":
      return { ...state, index: action.index, isPlaying: false };
    case "reset":
      return { ...initialReplayState, speed: state.speed };
    case "set-speed":
      return { ...state, speed: action.speed };
  }
}

export function playbackInterval(speed: ReplaySpeed): number {
  return 1200 / speed;
}
