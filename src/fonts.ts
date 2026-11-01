import { continueRender, delayRender } from "remotion";
import { loadFont } from "@remotion/fonts";
// Bundled with the project (no network needed at render time)
import w700 from "@fontsource/montserrat/files/montserrat-latin-700-normal.woff2";
import w800 from "@fontsource/montserrat/files/montserrat-latin-800-normal.woff2";
import w900 from "@fontsource/montserrat/files/montserrat-latin-900-normal.woff2";

export const MONTSERRAT = "Montserrat";

const handle = delayRender("Loading Montserrat");
Promise.all(
  [
    ["700", w700],
    ["800", w800],
    ["900", w900],
  ].map(([weight, url]) => loadFont({ family: MONTSERRAT, url, weight })),
)
  .then(() => continueRender(handle))
  .catch((err) => {
    console.error(err);
    continueRender(handle);
  });
