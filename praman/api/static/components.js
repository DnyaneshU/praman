/* Arena components.
 *
 * Vue 3 Composition API against the vendored global build, so there is no
 * build step and no node_modules — a judge clones the repo and the arena runs.
 *
 * Two things carry the page. The campaign rail *lists* what has been run
 * rather than synthesising a campaign from a rail and a tier toggle: the
 * previous version did the latter and two committed campaigns were unreachable
 * because the adaptive run shared their rail and tiers and won the tie. A list
 * cannot hide a campaign the way a lookup can, and it has somewhere to put the
 * ones a teammate authors in a scenario file.
 *
 * The mandate chain is the centrepiece. Every attack in the corpus keeps its
 * signatures valid and breaks a *relationship* between documents, so the
 * drawing has to show the joints rather than the boxes: the failed link is
 * struck through with its correct value beside it.
 */

import { asr, classify, outcomeLabel, percent, rupees, signed } from "./format.js";

const { computed, ref, watch, nextTick } = Vue;

/* -- campaign rail --------------------------------------------------------- */

export const CampaignRail = {
  props: { campaigns: Array, selectedId: String },
  emits: ["select"],
  setup(props) {
    /** Grouped by rail, with authored scenarios last and under their own head.
     *
     * Scenarios are the answer to "how do I test something you did not think
     * of", so they need a visible home rather than being filed among the
     * generated matrix as though they were part of it.
     */
    const groups = computed(() => {
      const generated = new Map();
      const authored = [];

      for (const campaign of props.campaigns) {
        if (campaign.authored) {
          authored.push(campaign);
          continue;
        }
        if (!generated.has(campaign.rail_name)) generated.set(campaign.rail_name, []);
        generated.get(campaign.rail_name).push(campaign);
      }

      const out = [...generated].map(([title, items]) => ({ title, items: items.sort(byControl) }));
      if (authored.length) out.push({ title: "Authored scenarios", items: authored });
      return out;
    });

    return { groups, percent, rupees, heat };
  },
  template: `
    <aside class="rail">
      <div class="rail-head">
        <span class="label">Campaigns</span>
        <span class="count">{{ campaigns.length }}</span>
      </div>

      <div class="rail-list">
        <p v-if="!campaigns.length" class="empty">
          No campaigns committed. Run <code>python -m praman matrix</code>.
        </p>
        <template v-for="group in groups" :key="group.title">
          <div class="rail-group">{{ group.title }}</div>
          <!-- The control names itself, adaptive included: two rows reading
               "Tier 1" are two campaigns nobody can tell apart. -->
          <button v-for="c in group.items" :key="c.id"
                  class="campaign"
                  :aria-current="c.id === selectedId"
                  @click="$emit('select', c)">
            <span class="top">
              <span class="control">
                {{ c.authored ? c.name : c.label }}<template v-if="c.adaptive"> · adaptive</template>
              </span>
              <span class="asr" :class="heat(c.asr)">{{ percent(c.asr) }}</span>
            </span>
            <span class="sub">
              <span>{{ c.episodes }} episodes</span>
              <template v-if="c.adaptive">
                <span class="sep">·</span><span>{{ c.rounds }} rounds</span>
              </template>
              <span class="sep">·</span>
              <span>{{ rupees(c.moved) }}</span>
              <span v-if="c.authored" class="chip authored">scenario</span>
            </span>
          </button>
        </template>
      </div>

      <div class="rail-foot">
        Add your own with <code>python -m praman run &lt;scenario.yaml&gt;</code> —
        see <code>scenarios/README.md</code>.
      </div>
    </aside>
  `,
};

/** undefended first, then by how many tiers are standing in the way. */
function byControl(a, b) {
  const weight = (c) => (c.tiers?.length ?? 0) * 2 + (c.adaptive ? 1 : 0);
  return weight(a) - weight(b);
}

/** Attack success reads as bad news high and good news low, not as a hue. */
function heat(rate) {
  if (rate === null || rate === undefined) return "";
  if (rate >= 0.5) return "hot";
  if (rate > 0) return "warm";
  return "cool";
}

/* -- campaign header and metrics ------------------------------------------- */

export const CampaignHead = {
  props: { campaign: { type: Object, default: null } },
  template: `
    <header class="campaign-head" v-if="campaign">
      <div>
        <h1>{{ campaign.name }}</h1>
        <p class="note" v-if="campaign.description">{{ campaign.description }}</p>
      </div>
      <div class="facts">
        <div class="fact"><span class="label">rail</span><span class="v">{{ campaign.rail }}</span></div>
        <div class="fact"><span class="label">control</span><span class="v">{{ campaign.label }}</span></div>
        <div class="fact"><span class="label">rounds</span><span class="v">{{ campaign.rounds }}</span></div>
        <div class="fact"><span class="label">episodes</span><span class="v">{{ campaign.episodes }}</span></div>
      </div>
    </header>
  `,
};

export const MetricBand = {
  props: { summary: { type: Object, default: null }, campaign: { type: Object, default: null } },
  setup(props) {
    /* Read from the streamed summary when there is one, and from the campaign
     * itself before that. Both are computed by praman/metrics.py over the same
     * episodes, so they agree — and selecting a campaign fills the scoreboard
     * immediately, where a row of em-dashes waiting on a replay read as broken
     * rather than as ready.
     *
     * The two names differ because one dict is a campaign description and the
     * other a metrics summary; mapping them here is the only place that has to
     * know. */
    const value = (summaryKey, campaignKey) =>
      computed(() => props.summary?.[summaryKey] ?? props.campaign?.[campaignKey ?? summaryKey]);

    return {
      asrValue: value("asr"),
      moved: value("rupees_moved", "moved"),
      benign: value("benign_pass_rate", "benign"),
      broke: value("rounds_to_break"),
      staticAsr: value("static_asr"),
      adaptiveAsr: value("adaptive_asr"),

      /* The delta is the project's headline claim, and it only exists for a
       * campaign that let the attacker adapt. Showing "+0.0 pts" for a
       * single-round run would report a measurement nobody made. */
      delta: computed(() => {
        if (!props.campaign?.adaptive) return null;
        return props.summary?.adaptive_delta ?? props.campaign?.adaptive_delta ?? null;
      }),
      loaded: computed(() => !!(props.summary || props.campaign)),
      percent,
      rupees,
      signed,
      heat,
    };
  },
  template: `
    <section class="band">
      <div class="metric headline">
        <div class="label">attack success</div>
        <div class="v" :class="heat(asrValue)">{{ percent(asrValue) }}</div>
        <div class="foot">of scored attempts moved money</div>
      </div>

      <div class="metric">
        <div class="label">rupees moved</div>
        <div class="v" :class="!loaded ? 'muted' : Number(moved) > 0 ? 'hot' : 'cool'">
          {{ loaded ? rupees(moved) : '—' }}
        </div>
        <div class="foot">ledger-verified, to the attacker</div>
      </div>

      <div class="metric">
        <div class="label">honest traffic</div>
        <div class="v" :class="benign === 1 ? 'cool' : benign ? 'hot' : 'muted'">
          {{ percent(benign) }}
        </div>
        <div class="foot">real purchases still settling</div>
      </div>

      <div class="metric">
        <div class="label">adaptive delta</div>
        <div class="v" :class="delta === null ? 'muted' : delta > 0 ? 'hot' : 'cool'">
          {{ delta === null ? '—' : signed(delta) }}
        </div>
        <div class="foot">
          <template v-if="delta === null">single round, not measured</template>
          <template v-else>{{ percent(staticAsr) }} → {{ percent(adaptiveAsr) }} once it adapts</template>
        </div>
      </div>

      <!-- null means "never broke", which is a result. Not-loaded is not. -->
      <div class="metric">
        <div class="label">rounds to break</div>
        <div class="v" :class="!loaded ? 'muted' : broke === null ? 'cool' : 'hot'">
          {{ !loaded ? '—' : broke === null ? 'held' : broke }}
        </div>
        <div class="foot">
          <template v-if="!loaded">no campaign selected</template>
          <template v-else-if="broke === null">never got through</template>
          <template v-else>first round money moved</template>
        </div>
      </div>
    </section>
  `,
};

/* -- attack feed ----------------------------------------------------------- */

export const AttackFeed = {
  props: {
    episodes: Array,
    selectedId: String,
    rounds: Array,
    arrived: { type: Set, default: () => new Set() },
    round: { default: null },
  },
  emits: ["select", "update:round"],
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

    return { rows, list, onScroll, classify, outcomeLabel };
  },
  template: `
    <section class="pane feed">
      <div class="pane-head">
        <h2>Attack feed</h2>
        <!-- Every round the campaign has, so the control does not grow under
             the cursor mid-replay. One that has not streamed yet is disabled
             rather than filtering the feed to nothing. -->
        <div class="segments" v-if="rounds.length > 1">
          <button :aria-pressed="round === null" @click="$emit('update:round', null)">all</button>
          <button v-for="r in rounds" :key="r"
                  :aria-pressed="round === r"
                  :disabled="!arrived.has(r)"
                  @click="$emit('update:round', r)">r{{ r }}</button>
        </div>
      </div>

      <p v-if="!episodes.length" class="empty">
        Pick a campaign in the rail and press Replay.
      </p>

      <ol v-else class="feed-list" ref="list" role="listbox" @scroll="onScroll">
        <template v-for="row in rows" :key="row.key">
          <li v-if="row.marker" class="round-marker">
            <span class="n">round {{ row.round }}</span>
            <span class="what">
              {{ row.round === 0 ? 'documented attacks' : 'after reading the refusal' }}
            </span>
          </li>
          <li v-else
              class="ep" :class="classify(row.episode)"
              role="option" tabindex="0"
              :aria-selected="row.episode.episode_id === selectedId"
              @click="$emit('select', row.episode)"
              @keydown.enter.prevent="$emit('select', row.episode)"
              @keydown.space.prevent="$emit('select', row.episode)">
            <span class="stripe"></span>
            <span class="what">
              <span class="line">
                <span class="aid">{{ row.episode.attack_id }}</span>
                <span class="rule" v-if="row.episode.violated_invariant">
                  {{ row.episode.violated_invariant }}
                </span>
              </span>
              <span class="lineage" v-if="row.episode.lineage && row.episode.lineage.length > 1">
                ↳ {{ row.episode.lineage.slice(1).join(' → ') }}
              </span>
            </span>
            <span class="amt">{{ outcomeLabel(row.episode) }}</span>
          </li>
        </template>
      </ol>
    </section>
  `,
};

/* -- mandate chain --------------------------------------------------------- */

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
      overcharged: computed(
        () =>
          !!snapshot.value && String(snapshot.value.payment_amount) !== String(snapshot.value.cart_total)
      ),
      concealed: computed(() => (snapshot.value?.items ?? []).some(([, , visible]) => !visible)),
      moved: computed(() => Number(props.episode?.rupees_moved ?? 0) > 0),
      rupees,
    };
  },
  template: `
    <section class="pane chain">
      <div class="pane-head"><h2>Mandate chain</h2></div>
      <div class="chain-body">
        <p v-if="!episode" class="empty">Select an episode to inspect what was signed.</p>
        <p v-else-if="!snapshot" class="empty">
          This campaign predates chain capture — re-run it to see the chain.
        </p>
        <template v-else>
          <div class="link" :class="{ broken: failed === 'inv-01' }">
            <header><span class="who">Intent</span><span class="what">what the human authorised</span></header>
            <div class="rows">
              <div class="row"><span class="k">asked for</span><span class="v">{{ snapshot.intent_description }}</span></div>
              <div class="row"><span class="k">ceiling</span><span class="v mono">{{ rupees(snapshot.intent_ceiling) }}</span></div>
            </div>
          </div>

          <div class="joint" :class="{ broken: failed === 'inv-01' }">
            <span class="stem"></span>the cart must stay inside the intent
          </div>

          <div class="link" :class="{ broken: failed === 'inv-03' || failed === 'inv-06' }">
            <header><span class="who">Cart</span><span class="what">{{ snapshot.cart_merchant }}</span></header>
            <div class="rows">
              <div class="row" v-for="(item, i) in snapshot.items" :key="i">
                <span class="k">{{ item[2] ? 'item' : 'item · hidden' }}</span>
                <span class="v" :class="{ concealed: !item[2] }">{{ item[0] }} — {{ rupees(item[1]) }}</span>
              </div>
              <div class="row"><span class="k">charged</span><span class="v mono">{{ rupees(snapshot.cart_total) }}</span></div>
              <div class="row">
                <span class="k">shown to user</span>
                <span class="v" :class="{ concealed: concealed || failed === 'inv-06' }">{{ snapshot.display_summary }}</span>
              </div>
            </div>
          </div>

          <div class="joint" :class="{ broken: failed === 'inv-02' || failed === 'inv-03' }">
            <span class="stem"></span>the payment must match the cart, and go to its issuer
          </div>

          <div class="link" :class="{ broken: failed === 'inv-02' || failed === 'inv-03' }">
            <header><span class="who">Payment</span><span class="what">where the money goes</span></header>
            <div class="rows">
              <div class="row">
                <span class="k">beneficiary</span>
                <span class="v mono">
                  <span :class="{ strike: rebound }">{{ snapshot.payment_beneficiary }}</span>
                  <template v-if="rebound">
                    <br><span class="correct">expected {{ snapshot.expected_beneficiary }}</span>
                  </template>
                </span>
              </div>
              <div class="row">
                <span class="k">amount</span>
                <span class="v mono">
                  <span :class="{ strike: overcharged }">{{ rupees(snapshot.payment_amount) }}</span>
                  <template v-if="overcharged">
                    <br><span class="correct">expected {{ rupees(snapshot.cart_total) }}</span>
                  </template>
                </span>
              </div>
            </div>
          </div>

          <div class="settle" :class="moved ? 'moved' : 'stopped'">
            <span class="k">Ledger</span>
            <span>
              <template v-if="moved">
                {{ rupees(episode.rupees_moved) }} reached {{ episode.beneficiary }}
              </template>
              <template v-else>₹0.00 moved</template>
            </span>
          </div>
        </template>
      </div>
    </section>
  `,
};

/* -- verdict --------------------------------------------------------------- */

const STAMPS = {
  through: { cls: "through", label: "Got through" },
  blocked: { cls: "blocked", label: "Blocked" },
  held: { cls: "held", label: "Held for review" },
  benign: { cls: "clean", label: "Honest purchase" },
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
        if (e.violated_invariant) return "The control named the rule it enforced.";
        return e.attack_id === "benign"
          ? "Honest traffic, and every check passed. This is the false-positive signal."
          : "Every check passed and the attack settled.";
      }),
    };
  },
  template: `
    <section class="pane verdict">
      <div class="pane-head"><h2>Verdict &amp; evidence</h2></div>
      <div class="verdict-body">
        <p v-if="!episode" class="empty">No episode selected.</p>
        <template v-else>
          <div class="stamp" :class="stamp.cls"><span class="dot"></span>{{ stamp.label }}</div>

          <div class="ruling">
            <div class="rule-id">
              <template v-if="episode.violated_invariant">
                {{ episode.violated_invariant }}<template v-if="episode.blocked_by_tier"> · tier {{ episode.blocked_by_tier }}</template>
              </template>
              <template v-else>no rule objected</template>
            </div>
            <div class="rule-text">{{ explanation }}</div>
          </div>

          <div v-if="episode.detail" class="evidence">{{ episode.detail }}</div>

          <div class="meta">
            <div class="row"><span class="k">attack</span><span class="v">{{ episode.attack_id }}</span></div>
            <div class="row"><span class="k">lineage</span><span class="v">{{ (episode.lineage || []).join(' → ') || '—' }}</span></div>
            <div class="row"><span class="k">rail profile</span><span class="v">{{ episode.rail_profile }}</span></div>
            <div class="row"><span class="k">victim model</span><span class="v">{{ episode.victim_model }}</span></div>
            <div class="row"><span class="k">control latency</span>
              <span class="v">{{ latency !== undefined ? latency.toFixed(2) + ' ms' : '—' }}</span></div>
            <div class="row"><span class="k">seed</span><span class="v">{{ episode.seed }}</span></div>
          </div>
        </template>
      </div>
    </section>
  `,
};

/* -- curve ----------------------------------------------------------------- */

export const AsrCurve = {
  props: { episodes: Array },
  setup(props) {
    const W = 760;
    const H = 176;
    const pad = { l: 54, r: 30, t: 20, b: 26 };

    const series = computed(() => {
      const attacks = props.episodes.filter((e) => e.attack_id !== "benign");
      const rounds = [...new Set(attacks.map((e) => e.round))].sort((a, b) => a - b);
      return rounds.map((round) => ({
        round,
        rate: asr(attacks.filter((e) => e.round === round)),
      }));
    });

    const x = (i) => pad.l + (i * (W - pad.l - pad.r)) / Math.max(series.value.length - 1, 1);
    const y = (v) => pad.t + (1 - v) * (H - pad.t - pad.b);

    const line = computed(() =>
      series.value.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.rate)}`).join(" ")
    );

    return {
      W,
      H,
      series,
      right: W - pad.r,
      gridlines: [0, 0.25, 0.5, 0.75, 1].map((v) => ({ v, y: y(v), label: `${v * 100}%` })),
      line,
      area: computed(() =>
        series.value.length
          ? `${line.value} L${x(series.value.length - 1)},${y(0)} L${x(0)},${y(0)} Z`
          : ""
      ),
      points: computed(() =>
        series.value.map((p, i) => {
          const last = i === series.value.length - 1;
          return {
            ...p,
            cx: x(i),
            cy: y(p.rate),
            label: percent(p.rate),
            last,
            // The end points' labels are anchored inward. Centred, the first
            // one lands on the percentage axis and the last runs off the plot.
            anchor: i === 0 ? "start" : last ? "end" : "middle",
            labelX: i === 0 ? x(i) + 8 : last ? x(i) - 8 : x(i),
          };
        })
      ),
      percent,
    };
  },
  template: `
    <section class="pane curve">
      <div class="pane-head"><h2>Attack success by round</h2></div>
      <div class="curve-body">
        <svg :viewBox="'0 0 ' + W + ' ' + H" preserveAspectRatio="xMidYMid meet" role="img"
             aria-label="Attack success rate by adaptation round">
          <defs>
            <linearGradient id="curveFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#F05A72" stop-opacity="0.24"/>
              <stop offset="100%" stop-color="#F05A72" stop-opacity="0"/>
            </linearGradient>
          </defs>

          <template v-for="g in gridlines" :key="g.v">
            <line :x1="54" :y1="g.y" :x2="right" :y2="g.y" stroke="#1B222C"/>
            <text :x="44" :y="g.y + 3.5" fill="#5B6675" font-size="10" text-anchor="end"
                  font-family="IBM Plex Mono">{{ g.label }}</text>
          </template>

          <path v-if="series.length" :d="area" fill="url(#curveFill)"/>
          <path v-if="series.length" :d="line" fill="none" stroke="#F05A72" stroke-width="1.75"
                stroke-linejoin="round"/>

          <template v-for="p in points" :key="p.round">
            <circle :cx="p.cx" :cy="p.cy" :r="p.last ? 4.5 : 3" fill="#090C11" stroke="#F05A72"
                    stroke-width="1.75"/>
            <text :x="p.labelX" :y="p.cy - 11" fill="#F05A72" font-size="11" :text-anchor="p.anchor"
                  font-family="IBM Plex Mono" font-weight="500">{{ p.label }}</text>
            <text :x="p.cx" :y="H - 7" fill="#5B6675" font-size="10" text-anchor="middle"
                  font-family="IBM Plex Mono">r{{ p.round }}</text>
          </template>
        </svg>

        <p class="caption">
          <strong>Round 0</strong> is the documented attack against a control that already
          knows it. Every later round is the same attacker having read the rejection and
          searched for a way around the rule that produced it.
        </p>
      </div>
    </section>
  `,
};
