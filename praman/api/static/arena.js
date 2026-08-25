/* The arena's root component: campaign selection, the replay socket, state.
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

const { createApp, computed, onMounted, onBeforeUnmount, ref, watch } = Vue;

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
    const campaigns = ref([]);
    const selected = ref(null);

    const mode = ref("—");
    const link = ref({ text: "idle", state: "" });
    const episodes = ref([]);
    const summary = ref(null);
    const running = ref(false);
    const roundFilter = ref(null);

    // Null until the viewer clicks. While it stays null the panes follow the
    // stream; once they choose an episode, the view stops moving under them.
    const picked = ref(null);

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
     *  yet would empty the feed and read as a broken button. */
    const arrived = computed(() => new Set(episodes.value.map((e) => e.round)));

    const shown = computed(() =>
      roundFilter.value === null
        ? episodes.value
        : episodes.value.filter((e) => e.round === roundFilter.value)
    );

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

    function reset() {
      episodes.value = [];
      summary.value = null;
      picked.value = null;
      roundFilter.value = null;
      running.value = false;
    }

    const setLink = (text, state = "") => (link.value = { text, state });

    // One token guards both loading and replaying. A viewer clicking through
    // the rail faster than the network answers, or switching campaigns
    // mid-replay, must not have the previous campaign's episodes land on top
    // of the new selection — which is exactly the bug the WebSocket version
    // had when its socket outlived the switch.
    let generation = 0;

    const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    async function fetchCampaign(id) {
      // Relative, so the same build works under the API at / and as static
      // files under a project path like /praman/.
      return fetch(`api/campaign/${id}`).then((r) => r.json());
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
        episodes.value = body.episodes;
        summary.value = body.summary;
        setLink("loaded");
      } catch {
        if (token === generation) setLink("could not load the campaign", "fault");
      }
    }

    async function load() {
      try {
        const health = await fetch("api/health").then((r) => r.json());
        mode.value = health.mode;
        campaigns.value = await fetch("api/campaigns").then((r) => r.json());
        selected.value = campaigns.value.find((c) => c.adaptive) ?? campaigns.value[0] ?? null;
        if (selected.value) await open(selected.value);
      } catch {
        setLink("could not reach the campaign data", "fault");
      }
    }

    function select(campaign) {
      if (campaign.id === selected.value?.id) return;
      // Bumping the token here is load-bearing: it abandons an in-flight load
      // and stops a running replay, so neither can append to the list the new
      // selection has just cleared.
      generation++;
      reset();
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
     */
    async function replay() {
      if (!selected.value) return;
      const token = ++generation;

      setLink("loading");
      let body;
      try {
        body = await fetchCampaign(selected.value.id);
      } catch {
        if (token === generation) setLink("could not load the campaign", "fault");
        return;
      }
      if (token !== generation) return;

      reset();
      running.value = true;
      summary.value = body.summary;
      setLink("replaying", "live");

      let previous = null;
      for (const episode of body.episodes) {
        if (token !== generation) return;
        if (previous !== null && episode.round !== previous) await pause(ROUND_DELAY);
        previous = episode.round;
        episodes.value = [...episodes.value, episode];
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
      episodes,
      shown,
      summary,
      running,
      picked,
      current,
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
          <AsrCurve :episodes="episodes"/>
        </div>
      </main>
    </div>
  `,
};

createApp(App).mount("#app");
