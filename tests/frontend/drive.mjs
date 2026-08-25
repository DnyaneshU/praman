/* Drive the arena in a real browser and assert that its controls work.
 *
 * Run by tests/test_frontend.py, which starts the server and Chrome. Talks the
 * Chrome DevTools Protocol directly over Node's built-in WebSocket, so there is
 * no Puppeteer and no node_modules — the same constraint the arena itself is
 * built under.
 *
 * `check.mjs` proves the templates compile and the helpers are correct. That is
 * not the same as the page working: every bug this file exists for was a
 * *wiring* bug. Two committed campaigns were unreachable because the rail
 * synthesised a campaign from a rail and a tier selection rather than listing
 * what had been run; switching campaigns mid-replay left the socket open, so
 * the old campaign kept pushing episodes into the list the new one had just
 * cleared. Both compiled fine. Both needed a click to find.
 *
 *   node drive.mjs <debuggerWsUrl> <pageUrl> [shotDir]
 */

const [, , wsUrl, pageUrl, shotDir] = process.argv;
const { writeFileSync } = await import("node:fs");

const socket = new WebSocket(wsUrl);
await new Promise((r, j) => { socket.onopen = r; socket.onerror = j; });

let nextId = 1;
const pending = new Map();
let sessionId = null;

socket.onmessage = ({ data }) => {
  const msg = JSON.parse(data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
  }
};

function send(method, params = {}, useSession = true) {
  const id = nextId++;
  const payload = { id, method, params };
  if (useSession && sessionId) payload.sessionId = sessionId;
  socket.send(JSON.stringify(payload));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

const { targetInfos } = await send("Target.getTargets", {}, false);
const page = targetInfos.find((t) => t.type === "page");
({ sessionId } = await send("Target.attachToTarget", { targetId: page.targetId, flatten: true }, false));

await send("Page.enable");
await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", {
  width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false,
});

const evaluate = async (expression) => {
  const { result, exceptionDetails } = await send("Runtime.evaluate", {
    expression, returnByValue: true, awaitPromise: true,
  });
  if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? "eval failed");
  return result.value;
};

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

/** Poll a page-side expression until it is true, or give up loudly.
 *
 * Fixed sleeps make this suite a coin flip on a cold CI runner: too short and
 * a healthy page fails, too long and every run pays for the worst case. A
 * flaky check is worse than no check, because the badge it turns red is the
 * one claiming the numbers reproduce.
 */
async function until(expression, { timeout = 20000, what = expression } = {}) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await evaluate(expression)) return;
    await wait(100);
  }
  throw new Error(`timed out after ${timeout}ms waiting for: ${what}`);
}

/** Screenshots are for looking at a change, not for the assertions. */
async function shot(name) {
  if (!shotDir) return;
  const { data } = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(`${shotDir}/${name}.png`, Buffer.from(data, "base64"));
}

await send("Page.navigate", { url: pageUrl });
await until(`document.querySelectorAll(".campaign").length > 0`, { what: "the rail to populate" });
await until(`document.querySelectorAll(".ep").length > 0`, { what: "the first campaign to load" });

const results = [];
const record = (name, ok, detail = "") => results.push({ name, ok, detail });

// -- the rail lists every campaign -----------------------------------------
const railCount = await evaluate(`document.querySelectorAll(".campaign").length`);
const apiCount = await evaluate(`fetch("/api/campaigns").then(r=>r.json()).then(c=>c.length)`);
record("rail lists every campaign", railCount === apiCount, `${railCount} of ${apiCount}`);

// -- clicking a campaign loads it ------------------------------------------
const before = await evaluate(`document.querySelector(".campaign-head h1").textContent.trim()`);
await evaluate(`document.querySelectorAll(".campaign")[0].click()`);
await until(`document.querySelector(".campaign-head h1").textContent.trim() !== ${JSON.stringify(before)}`, { what: "the header to change" });
await until(`document.querySelectorAll(".ep").length > 0`, { what: "the new campaign to load" });
const after = await evaluate(`document.querySelector(".campaign-head h1").textContent.trim()`);
const rowsAfter = await evaluate(`document.querySelectorAll(".ep").length`);
record("clicking a campaign switches it", before !== after, `${before} -> ${after}`);
record("clicking a campaign loads its episodes", rowsAfter > 0, `${rowsAfter} rows`);
record(
  "the selected campaign is the one marked current",
  await evaluate(`document.querySelectorAll('.campaign[aria-current="true"]').length === 1`)
);

// -- selecting an episode drives the chain and verdict ----------------------
await evaluate(`document.querySelectorAll(".ep")[1].click()`);
await until(`document.querySelectorAll('.ep[aria-selected="true"]').length === 1`, { what: "the episode to be selected" });
record(
  "clicking an episode selects it",
  await evaluate(`document.querySelectorAll('.ep[aria-selected="true"]').length === 1`)
);
record(
  "the chain pane renders the selected chain",
  await evaluate(`document.querySelectorAll(".chain-body .link").length === 3`)
);
record(
  "the verdict pane renders a stamp",
  await evaluate(`!!document.querySelector(".verdict-body .stamp")`)
);

// -- switching campaigns clears the previous selection ----------------------
await evaluate(`document.querySelectorAll(".campaign")[2].click()`);
await until(`document.querySelectorAll(".ep").length > 0`, { what: "the third campaign to load" });
record(
  "switching campaigns drops the previous episode selection",
  await evaluate(`document.querySelectorAll('.ep[aria-selected="true"]').length === 0`)
);

// -- round filter ----------------------------------------------------------
const adaptiveIndex = await evaluate(`
  [...document.querySelectorAll(".campaign")].findIndex(c => c.textContent.includes("adaptive"))
`);
await evaluate(`document.querySelectorAll(".campaign")[${adaptiveIndex}].click()`);
await until(`document.querySelectorAll(".feed .segments button").length > 1`, { what: "the round filter to appear" });

const roundButtons = await evaluate(`document.querySelectorAll(".feed .segments button").length`);
record("an adaptive campaign offers a round filter", roundButtons > 1, `${roundButtons} buttons`);

const allRows = await evaluate(`document.querySelectorAll(".ep").length`);
await evaluate(`document.querySelectorAll(".feed .segments button")[1].click()`);
await until(`document.querySelectorAll(".round-marker").length === 1`, { what: "the feed to narrow to one round" });
const r0Rows = await evaluate(`document.querySelectorAll(".ep").length`);
const r0Markers = await evaluate(`document.querySelectorAll(".round-marker").length`);
record("the round filter narrows the feed", r0Rows > 0 && r0Rows < allRows, `${allRows} -> ${r0Rows}`);
record("filtering to one round shows one round", r0Markers === 1, `${r0Markers} markers`);

await evaluate(`document.querySelectorAll(".feed .segments button")[0].click()`);
await until(`document.querySelectorAll(".ep").length === ${allRows}`, { what: "every round to come back" });
record(
  "the all button restores every round",
  (await evaluate(`document.querySelectorAll(".ep").length`)) === allRows
);

await shot("loaded");

// -- replay ----------------------------------------------------------------
await evaluate(`document.querySelector(".replay").click()`);
await until(`document.querySelector(".link-state .text").textContent.trim() === "streaming"`, { what: "the replay socket to open" });
await until(`document.querySelectorAll(".ep").length > 0`, { what: "the first replayed episode" });
const streaming = await evaluate(`document.querySelector(".link-state .text").textContent.trim()`);
const midRows = await evaluate(`document.querySelectorAll(".ep").length`);
record("replay opens the socket and streams", streaming === "streaming", streaming);
record("replay starts from an empty feed", midRows < allRows, `${midRows} rows so far`);
record(
  "replay disables its own button while running",
  await evaluate(`document.querySelector(".replay").disabled === true`)
);
// Let a few more land so the screenshot shows a replay in progress.
await until(`document.querySelectorAll(".ep").length >= 4`, { what: "a few episodes to stream" });
await shot("replaying");

// -- switching campaigns mid-replay must stop the stream --------------------
await evaluate(`document.querySelectorAll(".campaign")[0].click()`);
await until(`document.querySelectorAll(".ep").length > 0`, { what: "the switched-to campaign to load" });
const rowsA = await evaluate(`document.querySelectorAll(".ep").length`);
// Deliberately wall-clock: the assertion IS that no more episodes arrive.
// Several replay ticks (450ms each) have to pass with the count unmoved.
await wait(2500);
const rowsB = await evaluate(`document.querySelectorAll(".ep").length`);
record(
  "switching campaigns mid-replay stops the old stream",
  rowsA === rowsB,
  `${rowsA} then ${rowsB} rows`
);
record(
  "the replay button is usable again after switching",
  await evaluate(`document.querySelector(".replay").disabled === false`)
);

// --------------------------------------------------------------------------

for (const { name, ok, detail } of results) {
  console.log(`  ${ok ? "ok  " : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);
}
process.exit(results.every((r) => r.ok) ? 0 : 1);
