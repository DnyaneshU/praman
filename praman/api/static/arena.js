/* The arena's root component: campaign selection, replay, state.
 *
 * Vue 3 Composition API against the vendored global build. No build step, no
 * node_modules, no committed bundle — `git clone` then run the server, and the
 * arena is there.
 *
 * The arena *replays* committed results rather than computing them, so the
 * only honest control is one that picks among campaigns that were actually
 * run. `python -m praman matrix` generates the shipped grid and
 * `python -m praman run <scenario.yaml>` adds to it; both land in `results/`
 * and both appear in the rail without anything here knowing the difference.
 *
 * -- on how little of this is reactive ------------------------------------
 *
 * A campaign is a file that was written once and will not change. Handing it
 * to `ref()` made Vue walk every episode and wrap it, its snapshot, its items
 * and its latency map in Proxies — thousands of them, to track mutations that
 * never come. Worse, the replay appended with `episodes.value = [...episodes
 * .value, e]`, so each of a hundred ticks rebuilt the array and invalidated
 * every pane that read it.
 *
 * So the episodes live in a `shallowRef`, frozen, and the replay advances a
 * single integer. What is on screen is a computed slice of data Vue never
 * looks inside. The reactive surface of a running replay is one number.
 */

import {
  AsrCurve,
  AttackFeed,
  CampaignHead,
  CampaignRail,
  MandateChain,
  MetricBand,
  VerdictPanel,
} from "./components.js";
import { asr } from "./format.js";

const { createApp, computed, onMounted, onBeforeUnmount, ref, shallowRef, watch } = Vue;

// The speed a room can follow. These were praman/api/replay.py's EPISODE_DELAY
// and ROUND_DELAY; the longer pause at a round boundary is what makes the
// story legible — blocked, blocked, then through.
const EPISODE_DELAY = 450;
const ROUND_DELAY = 1200;

const App = {
  components: {
    CampaignRail,
    CampaignHead,
    MetricBand,
    AttackFeed,
    MandateChain,
    VerdictPanel,
    AsrCurve,
  },

  setup() {
    const campaigns = shallowRef([]);
    const selected = shallowRef(null);

    const mode = ref("—");
    const link = shallowRef({ text: "idle", state: "" });
    const running = ref(false);
    const roundFilter = ref(null);

    /** The campaign being shown: `{ id, summary, episodes }`, frozen.
     *
     * Shallow on purpose — see the note at the top of the file. Nothing in
     * here is ever written to, so there is nothing for Vue to track.
     */
    const loaded = shallowRef(null);

    /** How many of its episodes the replay has reached.
     *
     * This is the whole of the replay's state. Selecting a campaign sets it to
     * every episode at once; pressing Replay walks it up from zero.
     */
    const visible = ref(0);

    // Null until the viewer clicks. While it stays null the panes follow the
    // stream; once they choose an episode, the view stops moving under them.
    const picked = shallowRef(null);

    /** Fetched campaigns, kept for the session.
     *
     * A plain Map, deliberately outside Vue: it is a cache, not state anything
     * renders. Replay used to re-fetch a campaign already on screen — a second
     * round trip for bytes we were holding — so pressing it now costs nothing
     * and starts on the same frame.
     */
    const cache = new Map();

    const episodes = computed(() =>
      loaded.value ? loaded.value.episodes.slice(0, visible.value) : []
    );

    /** Rounds this campaign has, from the campaign itself.
     *
     * Not from the episodes on screen: derived that way the buttons appear one
     * at a time as a replay reaches each round, and the control jitters under
     * the cursor mid-replay.
     */
    const rounds = computed(() =>
      selected.value ? [...Array(selected.value.rounds).keys()] : []
    );

    /** Rounds actually on screen. Filtering to one that has not been reached
     *  yet would empty the feed and read as a broken button.
     *
     *  Episodes are written in round order, so the last one that has arrived
     *  names the high-water mark and this costs a walk of the rounds rather
     *  than of every episode. */
    const arrived = computed(() => {
      const last = episodes.value.at(-1);
      return new Set(last === undefined ? [] : rounds.value.filter((r) => r <= last.round));
    });

    const shown = computed(() =>
      roundFilter.value === null
        ? episodes.value
        : episodes.value.filter((e) => e.round === roundFilter.value)
    );

    /** Attack success per round, over the whole campaign.
     *
     * Computed once when a campaign loads rather than once per episode: the
     * numbers come from a file that is already complete, and recomputing them
     * on every tick of the replay was arithmetic over the same rows a hundred
     * times to arrive at the same answer.
     */
    const series = computed(() => {
      if (!loaded.value) return [];
      const byRound = new Map();
      for (const episode of loaded.value.episodes) {
        if (episode.attack_id === "benign") continue;
        if (!byRound.has(episode.round)) byRound.set(episode.round, []);
        byRound.get(episode.round).push(episode);
      }
      return [...byRound.keys()]
        .sort((a, b) => a - b)
        .map((round) => ({ round, rate: asr(byRound.get(round)) }));
    });

    /** The part of that curve the replay has reached. */
    const curve = computed(() => {
      const last = episodes.value.at(-1);
      return last === undefined ? [] : series.value.filter((p) => p.round <= last.round);
    });

    /** What the chain and verdict panes describe.
     *
     * A viewer's pick always wins. Failing that, a running replay follows the
     * feed — watching each episode land as it arrives is the whole point. A
     * campaign that is merely loaded opens on the last episode that took
     * money instead, because "here is the one that got through" is a more
     * useful first view than whichever episode happened to be last.
     */
    const current = computed(() => {
      if (picked.value) return picked.value;
      if (running.value) return shown.value.at(-1) ?? null;
      const through = shown.value.filter((e) => Number(e.rupees_moved) > 0);
      return through.at(-1) ?? shown.value.at(-1) ?? null;
    });

    const setLink = (text, state = "") => (link.value = { text, state });

    // One token guards loading and replaying alike. A viewer clicking through
    // the rail faster than the network answers, or switching campaigns
    // mid-replay, must not have the previous campaign's episodes land on top
    // of the new selection — which is exactly the bug the WebSocket version
    // had when its socket outlived the switch.
    let generation = 0;

    const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    /** Fetch a campaign once, then serve it from memory.
     *
     * Frozen on arrival: it says the data is read-only, and it lets Vue skip
     * the object entirely if one ever reaches a deep `ref`.
     */
    async function fetchCampaign(id) {
      const held = cache.get(id);
      if (held) return held;

      // Relative, so the same build works under the API at / and as static
      // files under a project path like /praman/.
      const body = await fetch(`api/campaign/${id}`).then((r) => r.json());
      const frozen = Object.freeze({
        id,
        summary: Object.freeze(body.summary),
        episodes: Object.freeze(body.episodes.map(Object.freeze)),
      });
      cache.set(id, frozen);
      return frozen;
    }

    /** Load a campaign whole, without the paced replay.
     *
     * Selecting a campaign should show it. The replay exists to *narrate* one
     * — blocked, blocked, then through, at a speed a room can follow — which
     * is a different job from reading it, and making the read wait on the
     * narration left three empty panes staring at anyone who just wanted to
     * look at the numbers.
     */
    async function open(campaign) {
      const token = ++generation;
      setLink("loading");
      try {
        const body = await fetchCampaign(campaign.id);
        if (token !== generation) return;
        loaded.value = body;
        visible.value = body.episodes.length;
        setLink("loaded");
      } catch {
        if (token === generation) setLink("could not load the campaign", "fault");
      }
    }

    async function load() {
      try {
        // Both at once. Asked in series, the arena waited out two round trips
        // before it could draw anything, and neither answer needs the other.
        const [health, list] = await Promise.all([
          fetch("api/health").then((r) => r.json()),
          fetch("api/campaigns").then((r) => r.json()),
        ]);
        mode.value = health.mode;
        campaigns.value = Object.freeze(list);
        selected.value = list.find((c) => c.adaptive) ?? list[0] ?? null;
        if (selected.value) await open(selected.value);
      } catch {
        setLink("could not reach the campaign data", "fault");
      }
    }

    function select(campaign) {
      if (campaign.id === selected.value?.id) return;
      // Bumping the token here is load-bearing: it abandons an in-flight load
      // and stops a running replay, so neither can advance a campaign the new
      // selection has just replaced.
      generation++;
      running.value = false;
      picked.value = null;
      roundFilter.value = null;
      loaded.value = null;
      visible.value = 0;
      selected.value = campaign;
      open(campaign);
    }

    /** Re-play a loaded campaign, one episode at a time.
     *
     * Paced here rather than by the server. The episodes are a committed file
     * that has already been read; spacing them out is a presentation choice,
     * and doing it over a socket bought a connection to drop, four handlers to
     * keep consistent, and a lifecycle bug — for delays a `setTimeout` gives
     * for free. It also makes the whole arena deployable as static files.
     *
     * Each tick moves one integer. Nothing is copied, nothing is re-proxied,
     * and the panes recompute from a slice of data that never changes.
     */
    async function replay() {
      if (!selected.value) return;
      const token = ++generation;

      let body;
      try {
        body = await fetchCampaign(selected.value.id);
      } catch {
        if (token === generation) setLink("could not load the campaign", "fault");
        return;
      }
      if (token !== generation) return;

      loaded.value = body;
      visible.value = 0;
      picked.value = null;
      roundFilter.value = null;
      running.value = true;
      setLink("replaying", "live");

      const all = body.episodes;
      for (let i = 0; i < all.length; i++) {
        if (token !== generation) return;
        if (i > 0 && all[i].round !== all[i - 1].round) await pause(ROUND_DELAY);
        visible.value = i + 1;
        await pause(EPISODE_DELAY);
      }

      if (token !== generation) return;
      running.value = false;
      setLink("complete", "live");
    }

    // A selection that the filter excludes would leave the chain and verdict
    // panes describing an episode the feed is not showing.
    watch(roundFilter, (round) => {
      if (round !== null && picked.value && picked.value.round !== round) picked.value = null;
    });

    onMounted(load);
    // Nothing to tear down: no socket, no timer that outlives the component.
    onBeforeUnmount(() => generation++);

    return {
      campaigns,
      selected,
      mode,
      link,
      shown,
      summary: computed(() => loaded.value?.summary ?? null),
      running,
      picked,
      current,
      curve,
      rounds,
      arrived,
      roundFilter,
      replay,
      select,
      pick: (episode) => (picked.value = episode),
    };
  },

  template: `
    <div class="shell">
      <header class="mast">
        <div class="brand">
          <span class="mark">प्रमाण</span>
          <span class="divider"></span>
          <span class="name">Praman Arena</span>
          <span class="tag">breach &amp; attack simulation · payment mandate controls</span>
        </div>

        <span class="spacer"></span>

        <div class="status">
          <span class="readout">
            <span class="label">mode</span><span class="value">{{ mode }}</span>
          </span>
          <span class="link-state" :class="link.state">
            <span class="dot"></span><span class="text">{{ link.text }}</span>
          </span>
          <button class="replay" @click="replay" :disabled="running || !selected">
            <span class="glyph">▶</span>{{ running ? 'Replaying' : 'Replay' }}
          </button>
        </div>
      </header>

      <CampaignRail :campaigns="campaigns" :selected-id="selected?.id" @select="select"/>

      <main class="main">
        <CampaignHead :campaign="selected"/>
        <MetricBand :summary="summary" :campaign="selected"/>

        <div class="work">
          <AttackFeed :episodes="shown" :selected-id="picked?.episode_id"
                      :rounds="rounds" :arrived="arrived" :round="roundFilter"
                      @select="pick" @update:round="roundFilter = $event"/>
          <MandateChain :episode="current"/>
          <VerdictPanel :episode="current"/>
          <AsrCurve :series="curve"/>
        </div>
      </main>
    </div>
  `,
};

createApp(App).mount("#app");
