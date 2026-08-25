/* Arena components.
 *
 * Vue 3 Composition API against the vendored global build, so there is no
 * build step and no node_modules — a judge clones the repo and the arena runs.
 *
 * The mandate chain is the centrepiece. Every attack in the corpus keeps its
 * signatures valid and breaks a *relationship* between documents, so the
 * drawing has to show the joints rather than the boxes: the failed link is
 * struck through with its correct value beside it.
 */

import { asr, classify, percent, rupees } from "./format.js";

const { computed, ref, watch, nextTick } = Vue;

export const Scoreboard = {
  props: { summary: { type: Object, default: null } },
  setup(props) {
    const stat = (key) => computed(() => props.summary?.[key]);
    return {
      staticAsr: stat("static_asr"),
      adaptiveAsr: stat("adaptive_asr"),
      moved: stat("rupees_moved"),
      benign: stat("benign_pass_rate"),
      broke: stat("rounds_to_break"),
      delta: computed(() => {
        const d = props.summary?.adaptive_delta;
        if (d === null || d === undefined) return "—";
        return `${d >= 0 ? "+" : ""}${(d * 100).toFixed(1)} pts`;
      }),
      percent,
      rupees,
    };
  },
  template: `
    <section class="scoreboard">
      <div class="stat"><dt>static ASR</dt><dd>{{ percent(staticAsr) }}</dd></div>
      <div class="stat"><dt>adaptive ASR</dt><dd class="hot">{{ percent(adaptiveAsr) }}</dd></div>
      <div class="stat"><dt>adaptive delta</dt><dd>{{ delta }}</dd></div>
      <div class="stat"><dt>moved</dt><dd class="hot">{{ moved ? rupees(moved) : '—' }}</dd></div>
      <div class="stat"><dt>benign pass</dt><dd>{{ percent(benign) }}</dd></div>
      <div class="stat"><dt>rounds to break</dt>
        <dd>{{ broke === null || broke === undefined ? 'never' : broke }}</dd></div>
    </section>
  `,
};

export const AttackFeed = {
  props: { episodes: Array, selectedId: String },
  emits: ["select"],
  setup(props) {
    const list = ref(null);

    // Follow the run as it streams, but never yank the view away from someone
    // who has scrolled up to read an earlier episode.
    const pinned = ref(true);
    const onScroll = () => {
      const node = list.value;
      if (!node) return;
      pinned.value = node.scrollHeight - node.scrollTop - node.clientHeight < 40;
    };
    watch(
      () => props.episodes.length,
      async () => {
        if (!pinned.value) return;
        await nextTick();
        if (list.value) list.value.scrollTop = list.value.scrollHeight;
      }
    );

    const rows = computed(() => {
      const out = [];
      let round = null;
      for (const episode of props.episodes) {
        if (episode.round !== round) {
          round = episode.round;
          out.push({ marker: true, round, key: `r${round}` });
        }
        out.push({ marker: false, episode, key: episode.episode_id });
      }
      return out;
    });

    return { rows, list, onScroll, classify, rupees };
  },
  template: `
    <section class="pane feed">
      <h2>Attack feed</h2>
      <ol class="episodes" ref="list" role="listbox" @scroll="onScroll">
        <template v-for="row in rows" :key="row.key">
          <li v-if="row.marker" class="round-marker">
            {{ row.round === 0 ? 'round 0 · documented attacks' : 'round ' + row.round + ' · after adapting' }}
          </li>
          <li v-else
              class="ep" :class="classify(row.episode)"
              role="option" tabindex="0"
              :aria-selected="row.episode.episode_id === selectedId"
              @click="$emit('select', row.episode)"
              @keydown.enter.prevent="$emit('select', row.episode)"
              @keydown.space.prevent="$emit('select', row.episode)">
            <span class="id">{{ row.episode.episode_id.replace(/^ep-/, '') }}</span>
            <span class="what">
              <span class="aid">{{ row.episode.attack_id }}</span>
              <span v-if="row.episode.lineage && row.episode.lineage.length > 1" class="lin">
                ↳ {{ row.episode.lineage.slice(1).join(' → ') }}
              </span>
            </span>
            <span class="amt">
              {{ Number(row.episode.rupees_moved) > 0 ? rupees(row.episode.rupees_moved) : 'blocked' }}
            </span>
          </li>
        </template>
      </ol>
      <p v-if="!episodes.length" class="empty">Pick a campaign and press Replay.</p>
    </section>
  `,
};

export const MandateChain = {
  props: { episode: { type: Object, default: null } },
  setup(props) {
    const snapshot = computed(() => props.episode?.snapshot ?? null);
    const failed = computed(() => props.episode?.violated_invariant ?? null);

    return {
      snapshot,
      failed,
      rebound: computed(
        () =>
          !!snapshot.value &&
          snapshot.value.payment_beneficiary !== snapshot.value.expected_beneficiary
      ),
      concealed: computed(() => (snapshot.value?.items ?? []).some(([, , visible]) => !visible)),
      moved: computed(() => Number(props.episode?.rupees_moved ?? 0) > 0),
      rupees,
    };
  },
  template: `
    <section class="pane chain">
      <h2>Mandate chain</h2>
      <div class="chain-body">
        <p v-if="!episode" class="empty">Select an episode to inspect its chain.</p>
        <p v-else-if="!snapshot" class="empty">
          This campaign predates chain capture — re-run it to see the chain.
        </p>
        <template v-else>
          <div class="link" :class="{ broken: failed === 'inv-01' }">
            <header><span>Intent</span><span>what the human authorised</span></header>
            <div class="rows">
              <div class="row"><span>asked for</span><span>{{ snapshot.intent_description }}</span></div>
              <div class="row"><span>ceiling</span><span class="num">{{ rupees(snapshot.intent_ceiling) }}</span></div>
            </div>
          </div>
          <div class="joint" :class="{ broken: failed === 'inv-01' }">↓ cart must stay inside the intent</div>

          <div class="link" :class="{ broken: failed === 'inv-03' || failed === 'inv-06' }">
            <header><span>Cart</span><span>{{ snapshot.cart_merchant }}</span></header>
            <div class="rows">
              <div class="row" v-for="(item, i) in snapshot.items" :key="i">
                <span>{{ item[2] ? 'item' : 'item · hidden' }}</span>
                <span :class="{ 'hidden-item': !item[2] }">{{ item[0] }} — {{ rupees(item[1]) }}</span>
              </div>
              <div class="row"><span>charged</span><span class="num">{{ rupees(snapshot.cart_total) }}</span></div>
              <div class="row">
                <span>shown to user</span>
                <span :class="{ 'hidden-item': concealed || failed === 'inv-06' }">{{ snapshot.display_summary }}</span>
              </div>
            </div>
          </div>
          <div class="joint" :class="{ broken: failed === 'inv-02' }">
            ↓ money must go to the merchant that issued the cart
          </div>

          <div class="link" :class="{ broken: failed === 'inv-02' }">
            <header><span>Payment</span><span>where the money goes</span></header>
            <div class="rows">
              <div class="row">
                <span>beneficiary</span>
                <span>
                  <span :class="{ strike: rebound }">{{ snapshot.payment_beneficiary }}</span>
                  <template v-if="rebound">
                    <br><span class="correct">expected {{ snapshot.expected_beneficiary }}</span>
                  </template>
                </span>
              </div>
              <div class="row"><span>amount</span><span class="num">{{ rupees(snapshot.payment_amount) }}</span></div>
            </div>
          </div>

          <div class="settle" :class="moved ? 'moved' : 'stopped'">
            <template v-if="moved">
              LEDGER · {{ rupees(episode.rupees_moved) }} reached {{ episode.beneficiary }}
            </template>
            <template v-else>LEDGER · ₹0.00 moved</template>
          </div>
        </template>
      </div>
    </section>
  `,
};

const STAMPS = {
  through: { cls: "through", label: "GOT THROUGH" },
  blocked: { cls: "blocked", label: "BLOCKED" },
  held: { cls: "held", label: "HELD FOR REVIEW" },
  benign: { cls: "clean", label: "HONEST PURCHASE" },
};

export const VerdictPanel = {
  props: { episode: { type: Object, default: null } },
  setup(props) {
    return {
      stamp: computed(() => (props.episode ? STAMPS[classify(props.episode)] : null)),
      latency: computed(() => props.episode?.latency_ms?.control),
      explanation: computed(() => {
        const e = props.episode;
        if (!e) return "";
        if (e.escalated) {
          return "Held for a human rather than refused — Tier 3 escalates, it does not decide.";
        }
        return e.violated_invariant
          ? "The control named the rule it enforced."
          : "Every check passed.";
      }),
    };
  },
  template: `
    <section class="pane verdict">
      <h2>Verdict &amp; evidence</h2>
      <div class="verdict-body">
        <p v-if="!episode" class="empty">No episode selected.</p>
        <template v-else>
          <div class="stamp" :class="stamp.cls">{{ stamp.label }}</div>
          <div class="rule-name">
            <template v-if="episode.violated_invariant">
              {{ episode.violated_invariant }}<template v-if="episode.blocked_by_tier"> · tier {{ episode.blocked_by_tier }}</template>
            </template>
            <template v-else>no rule objected</template>
          </div>
          <div class="rule-text">{{ explanation }}</div>

          <div v-if="episode.detail" class="evidence">
            <div class="row"><span>observed</span><span class="observed">{{ episode.detail }}</span></div>
          </div>

          <div class="meta">
            <div class="row"><span>attack</span><span>{{ episode.attack_id }}</span></div>
            <div class="row"><span>lineage</span><span>{{ (episode.lineage || []).join(' → ') || '—' }}</span></div>
            <div class="row"><span>rail profile</span><span>{{ episode.rail_profile }}</span></div>
            <div class="row"><span>victim model</span><span>{{ episode.victim_model }}</span></div>
            <div class="row"><span>control latency</span>
              <span>{{ latency !== undefined ? latency.toFixed(2) + ' ms' : '—' }}</span></div>
            <div class="row"><span>seed</span><span>{{ episode.seed }}</span></div>
          </div>
        </template>
      </div>
    </section>
  `,
};

export const AsrCurve = {
  props: { episodes: Array },
  setup(props) {
    const W = 720;
    const H = 200;
    const pad = { l: 44, r: 18, t: 22, b: 30 };

    const series = computed(() => {
      const attacks = props.episodes.filter((e) => e.attack_id !== "benign");
      const rounds = [...new Set(attacks.map((e) => e.round))].sort((a, b) => a - b);
      return rounds.map((round) => ({
        round,
        rate: asr(attacks.filter((e) => e.round === round)),
      }));
    });

    const x = (i) =>
      pad.l + (i * (W - pad.l - pad.r)) / Math.max(series.value.length - 1, 1);
    const y = (v) => pad.t + (1 - v) * (H - pad.t - pad.b);

    const line = computed(() =>
      series.value.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.rate)}`).join(" ")
    );

    return {
      W,
      H,
      series,
      gridlines: [0, 0.25, 0.5, 0.75, 1].map((v) => ({ v, y: y(v), label: `${v * 100}%` })),
      line,
      area: computed(() =>
        series.value.length
          ? `${line.value} L${x(series.value.length - 1)},${y(0)} L${x(0)},${y(0)} Z`
          : ""
      ),
      points: computed(() =>
        series.value.map((p, i) => ({ ...p, cx: x(i), cy: y(p.rate), label: percent(p.rate) }))
      ),
      percent,
    };
  },
  template: `
    <section class="pane curve">
      <h2>Attack success by round</h2>
      <div class="curve-body">
        <svg :viewBox="'0 0 ' + W + ' ' + H" preserveAspectRatio="none" role="img"
             aria-label="Attack success rate by adaptation round">
          <defs>
            <linearGradient id="curveFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#FF6B84" stop-opacity="0.28"/>
              <stop offset="100%" stop-color="#FF6B84" stop-opacity="0"/>
            </linearGradient>
          </defs>
          <template v-for="g in gridlines" :key="g.v">
            <line :x1="44" :y1="g.y" :x2="W - 18" :y2="g.y" stroke="#202836"/>
            <text :x="36" :y="g.y + 4" fill="#66717F" font-size="10" text-anchor="end"
                  font-family="IBM Plex Mono">{{ g.label }}</text>
          </template>
          <path v-if="series.length" :d="area" fill="url(#curveFill)"/>
          <path v-if="series.length" :d="line" fill="none" stroke="#FF6B84" stroke-width="2"/>
          <template v-for="p in points" :key="p.round">
            <circle :cx="p.cx" :cy="p.cy" r="4" fill="#FF6B84"/>
            <text :x="p.cx" :y="p.cy - 12" fill="#FF6B84" font-size="11" text-anchor="middle"
                  font-family="IBM Plex Mono">{{ p.label }}</text>
            <text :x="p.cx" :y="H - 8" fill="#66717F" font-size="10" text-anchor="middle"
                  font-family="IBM Plex Mono">round {{ p.round }}</text>
          </template>
        </svg>
        <p class="caption">
          Round 0 is the documented attack against a control that knows it.
          Every later round is the same attacker having read the rejection.
        </p>
      </div>
    </section>
  `,
};

export const Controls = {
  /* Rail, control and round, as facets over the committed campaign set.
   *
   * The arena replays results rather than re-running them, so a switch on the
   * page is only honest if a campaign was actually run for that combination.
   * `python -m praman matrix` generates the full grid, and these controls are
   * a view onto what exists: a combination with no campaign behind it is shown
   * disabled rather than silently doing nothing.
   */
  props: { campaigns: Array, rail: String, tiersKey: String, round: { default: null }, rounds: Array },
  emits: ["update:rail", "update:tiersKey", "update:round"],
  setup(props) {
    const rails = computed(() => [...new Set(props.campaigns.map((c) => c.rail))].sort());

    const controls = computed(() => {
      const seen = new Map();
      for (const c of props.campaigns) {
        const key = (c.tiers ?? []).join(",");
        if (!seen.has(key)) seen.set(key, { key, label: c.label, adaptive: c.adaptive });
      }
      return [...seen.values()].sort((a, b) => a.key.length - b.key.length);
    });

    const available = (rail, key) =>
      props.campaigns.some((c) => c.rail === rail && (c.tiers ?? []).join(",") === key);

    return { rails, controls, available };
  },
  template: `
    <section class="facets">
      <div class="facet">
        <span class="label">rail</span>
        <div class="segments">
          <button v-for="r in rails" :key="r"
                  :aria-pressed="r === rail"
                  @click="$emit('update:rail', r)">{{ r }}</button>
        </div>
      </div>

      <div class="facet">
        <span class="label">control</span>
        <div class="segments">
          <button v-for="c in controls" :key="c.key"
                  :aria-pressed="c.key === tiersKey"
                  :disabled="!available(rail, c.key)"
                  @click="$emit('update:tiersKey', c.key)">{{ c.label }}</button>
        </div>
      </div>

      <div class="facet" v-if="rounds.length > 1">
        <span class="label">round</span>
        <div class="segments">
          <button :aria-pressed="round === null" @click="$emit('update:round', null)">all</button>
          <button v-for="r in rounds" :key="r"
                  :aria-pressed="round === r"
                  @click="$emit('update:round', r)">{{ r }}</button>
        </div>
      </div>

      <span class="note" v-if="round !== null">showing round {{ round }} only</span>
    </section>
  `,
};
