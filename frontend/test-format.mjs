import assert from "node:assert/strict";
import { probabilityPercentages } from "./src/format.js";
for (const p of [
  { Dropout: 1 / 3, Enrolled: 1 / 3, Graduate: 1 / 3 },
  { Dropout: 0.9999, Enrolled: 0.0001, Graduate: 0 },
  { Dropout: 0.74125, Enrolled: 0.18525, Graduate: 0.0735 },
]) {
  const result = probabilityPercentages(p);
  assert.equal(
    Object.values(result).reduce(
      (n, v) => n + Math.round(parseFloat(v) * 10),
      0,
    ),
    1000,
  );
}
console.log("PASS: displayed probabilities sum to 100.0%");
