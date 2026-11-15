import type { ComponentProps } from "react";
import { Link } from "react-router";

/** Starts loading the statistics engine, so it is ready by the time the page opens. */
const warm = () =>
  void import("@/lib/stats/engine").then((m) => m.getStatsEngine().warmUp()).catch(() => {});

/** A link to the Statistics page that warms up the engine when someone points at or focuses it. */
export function StatsLink(props: ComponentProps<typeof Link>) {
  return <Link {...props} onPointerEnter={warm} onFocus={warm} />;
}
