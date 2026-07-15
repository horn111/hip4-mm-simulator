import sampleReplay from "../../public/data/sample-replay.json";
import validation24h from "../../public/data/validation-24h.json";

import { demoReplaySchema, validationSchema } from "@/lib/replay-schema";

export const replayData = demoReplaySchema.parse(sampleReplay);
export const validationData = validationSchema.parse(validation24h);
