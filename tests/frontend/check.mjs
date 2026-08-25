/* Frontend checks, run by tests/test_frontend.py.
 *
 * The arena has no build step, which is the point — a judge clones the repo
 * and it runs. The cost is that nothing tells you a template stopped compiling
 * or a helper started disagreeing with the Python it mirrors; you find out by
 * opening the page, if you happen to open the right pane.
 *
 * So: compile every template against the vendored Vue, and assert the two
 * properties that were actually broken. The campaign rail must show every
 * campaign it is handed — the old facet lookup synthesised a campaign from a
 * rail and a tier selection, and two committed campaigns were unreachable
 * because the adaptive run shared their rail and tiers and won the tie. And
 * `asr()` must count exactly what praman/metrics.py counts, or the curve stops
 * describing the campaign it is drawing.
 *
 * Node has no DOM. Vue's compiler only needs one for decoding HTML entities in
 * attribute values, so that is all `stubDom` provides.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const STATIC = resolve(dirname(fileURLToPath(import.meta.url)), "../../praman/api/static");

const failures = [];
const check = (name, fn) => {
  try {
    fn();
  } catch (error) {
    failures.push(`${name}: ${error.message}`);
  }
};
const assert = (ok, message) => {
  if (!ok) throw new Error(message);
};
const equal = (actual, expected, message) =>
  assert(
    actual === expected,
    `${message ?? "value"}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`
  );

/* -- a DOM only large enough for the compiler ------------------------------ */

const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };

function stubDom() {
  const decode = (text) =>
    String(text).replace(/&(#x?[0-9a-f]+|[a-z]+);/gi, (whole, body) => {
      if (body[0] !== "#") return ENTITIES[body.toLowerCase()] ?? whole;
      const code = body[1] === "x" || body[1] === "X"
        ? parseInt(body.slice(2), 16)
        : parseInt(body.slice(1), 10);
      return Number.isFinite(code) ? String.fromCodePoint(code) : whole;
    });

  globalThis.document = {
    createElement: () => ({
      // Vue decodes an attribute by writing it into innerHTML and reading the
      // attribute back off the parsed child. Both halves have to be present or
      // every `&amp;` in a template surfaces as a compile error.
      innerHTML: "",
      get children() {
        const match = /=(["'])([\s\S]*?)\1/.exec(this.innerHTML);
        const value = match ? decode(match[2]) : "";
        return [{ getAttribute: () => value }];
      },
      get textContent() {
        return decode(this.innerHTML);
      },
    }),
  };
}

/* -- load the vendored Vue and the modules --------------------------------- */

stubDom();
// The build is `var Vue = (function(){...})({})`. In a browser that `var`
// lands on window; inside a Function body it is local, so hand it over.
const vueSource = readFileSync(resolve(STATIC, "vendor/vue.global.prod.js"), "utf8");
new Function(`${vueSource}\nglobalThis.Vue = Vue;`)();
assert(globalThis.Vue, "the vendored Vue build did not define Vue");

const format = await import(`file://${resolve(STATIC, "format.js")}`);
const components = await import(`file://${resolve(STATIC, "components.js")}`);

/* -- every template compiles ----------------------------------------------- */

for (const [name, component] of Object.entries(components)) {
  check(`${name} template compiles`, () => {
    assert(typeof component.template === "string", "has no template");
    Vue.compile(component.template);
  });
}

check("the app template compiles", () => {
  // arena.js mounts on import, which needs a real document. Read the template
  // out of the source instead — compiling it is the part worth checking.
  const source = readFileSync(resolve(STATIC, "arena.js"), "utf8");
  const match = /template:\s*`([\s\S]*?)`,\n\};/.exec(source);
  assert(match, "could not find the app template in arena.js");
  Vue.compile(match[1]);
});

/* -- the campaign rail shows every campaign -------------------------------- */

const CAMPAIGNS = [
  { id: "autopay-undefended", rail_name: "UPI Autopay", label: "undefended", tiers: [], adaptive: false, asr: 1 },
  { id: "autopay-tier1", rail_name: "UPI Autopay", label: "Tier 1", tiers: [1], adaptive: false, asr: 0.17 },
  { id: "autopay-adaptive", rail_name: "UPI Autopay", label: "Tier 1", tiers: [1], adaptive: true, asr: 0.44 },
  { id: "autopay-tier123", rail_name: "UPI Autopay", label: "Tier 1+2+3", tiers: [1, 2, 3], adaptive: false, asr: 0 },
  { id: "uap-tier1", rail_name: "NPCI UAP", label: "Tier 1", tiers: [1], adaptive: false, asr: 0.17 },
  { id: "uap-adaptive", rail_name: "NPCI UAP", label: "Tier 1", tiers: [1], adaptive: true, asr: 0.4 },
  { id: "convenience-fee", rail_name: "UPI Autopay", label: "Tier 1", tiers: [1], adaptive: false, asr: 0, authored: true, name: "Convenience-fee skim" },
];

const listed = () => {
  const { groups } = components.CampaignRail.setup({ campaigns: CAMPAIGNS, selectedId: null });
  return groups.value;
};

check("every campaign appears exactly once", () => {
  const ids = listed().flatMap((group) => group.items.map((c) => c.id));
  equal(ids.length, CAMPAIGNS.length, "campaigns listed");
  equal(new Set(ids).size, CAMPAIGNS.length, "distinct campaigns listed");
});

check("the static and adaptive runs of one control are both reachable", () => {
  const ids = listed().flatMap((group) => group.items.map((c) => c.id));
  assert(ids.includes("autopay-tier1"), "autopay-tier1 is missing");
  assert(ids.includes("autopay-adaptive"), "autopay-adaptive is missing");
});

check("authored scenarios are grouped apart from the generated matrix", () => {
  const groups = listed();
  const last = groups.at(-1);
  equal(last.title, "Authored scenarios");
  equal(last.items.length, 1);
  equal(last.items[0].id, "convenience-fee");
});

check("controls are ordered by how much is standing in the way", () => {
  const autopay = listed().find((g) => g.title === "UPI Autopay");
  equal(
    autopay.items.map((c) => c.id).join(","),
    "autopay-undefended,autopay-tier1,autopay-adaptive,autopay-tier123"
  );
});

/* -- format.js agrees with praman/metrics.py -------------------------------- */

const episode = (over) => ({
  attack_id: "S-02",
  outcome: "allow",
  rupees_moved: "0",
  escalated: false,
  ...over,
});

check("asr scores money moved, not the control's verdict", () => {
  equal(format.asr([episode({ rupees_moved: "394000" }), episode()]), 0.5);
});

check("asr excludes refusals and harness errors", () => {
  const scored = [episode({ rupees_moved: "394000" }), episode({ outcome: "refusal" })];
  equal(format.asr(scored), 1, "a refusal must not read as a defended attack");
  equal(format.asr([episode({ outcome: "error" })]), 0);
});

check("asr excludes benign traffic", () => {
  equal(format.asr([episode({ attack_id: "benign", rupees_moved: "394000" })]), 0);
});

check("money is grouped the Indian way", () => {
  equal(format.rupees("296800"), "₹2,968.00");
  equal(format.rupees("123456789"), "₹12,34,567.89");
  equal(format.rupees("0"), "₹0.00");
  equal(format.rupees(null), "₹0.00");
});

check("an episode reads as what the ledger did, not what the control said", () => {
  equal(format.classify(episode({ rupees_moved: "1" })), "through");
  equal(format.classify(episode({ outcome: "block" })), "blocked");
  equal(format.classify(episode({ escalated: true })), "held");
  equal(format.classify(episode({ attack_id: "benign" })), "benign");
});

check("honest traffic the control refused is not shown as a clean pass", () => {
  // The false-positive rate decides whether a control could ever ship. Both
  // states rendering the same is how a broken one looks like a working one.
  const refused = episode({ attack_id: "benign", outcome: "block" });
  equal(format.classify(refused), "refused");
  equal(format.outcomeLabel(refused), "refused");
  equal(format.outcomeLabel(episode({ attack_id: "benign" })), "settled");
});

check("an attack that never reached the control says so", () => {
  equal(format.outcomeLabel(episode({ outcome: "refusal" })), "declined");
  equal(format.outcomeLabel(episode({ outcome: "error" })), "error");
  equal(format.outcomeLabel(episode({ outcome: "block" })), "blocked");
  equal(format.outcomeLabel(episode({ rupees_moved: "296800" })), "₹2,968.00");
});

check("a delta keeps its sign", () => {
  equal(format.signed(0.271), "+27.1 pts");
  equal(format.signed(-0.04), "−4.0 pts");
  equal(format.signed(null), "—");
});

/* -------------------------------------------------------------------------- */

if (failures.length) {
  console.error(failures.map((f) => `  ${f}`).join("\n"));
  process.exit(1);
}
console.log(`ok — ${Object.keys(components).length} templates and the app compile`);
