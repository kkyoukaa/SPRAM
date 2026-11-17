export function probabilityPercentages(probabilities) {
  const keys = ["Dropout", "Enrolled", "Graduate"];
  const scaled = keys.map(
    (key) => Math.max(0, Number(probabilities[key] || 0)) * 1000,
  );
  const units = scaled.map(Math.floor);
  let remaining = 1000 - units.reduce((a, b) => a + b, 0);
  const order = scaled
    .map((n, i) => ({ i, remainder: n - units[i] }))
    .sort((a, b) => b.remainder - a.remainder);
  if (remaining < 0 || remaining > keys.length)
    return Object.fromEntries(keys.map((key) => [key, "—"]));
  for (let i = 0; i < remaining; i++) units[order[i].i]++;
  return Object.fromEntries(
    keys.map((key, i) => [key, `${(units[i] / 10).toFixed(1)}%`]),
  );
}
