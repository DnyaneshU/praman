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

    let socket = null;
    const setLink = (text, state = "") => (link.value = { text, state });

    /** Rounds this campaign has, from the campaign itself.
     *
     * Not from the episodes on screen: derived that way the buttons appear one
     * at a time as the stream reaches each round, and the control jitters
     * under the cursor mid-replay.
     */
    const rounds = computed(() =>
      selected.value ? [...Array(selected.value.rounds).keys()] : []
    );

    /** Rounds actually streamed so far. Filtering to one that has not arrived
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
     * stream — watching each episode land as it arrives is the whole point of
     * the replay. A campaign that is merely loaded opens on the last episode
     * that took money instead, because "here is the one that got through" is a
     * more useful first view than whichever episode happened to be last.
     */
    const current = computed(() => {
      if (picked.value) return picked.value;
      if (running.value) return shown.value.at(-1) ?? null;
      const through = shown.value.filter((e) => Number(e.rupees_moved) > 0);
      return through.at(-1) ?? shown.value.at(-1) ?? null;
    });

    function close() {
      // Detach the handlers before closing: onclose fires asynchronously and
      // would otherwise report "disconnected" over the state we just moved to.
      if (!socket) return;
      socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null;
      socket.close();
      socket = null;
    }

    function reset() {
      episodes.value = [];
      summary.value = null;
      picked.value = null;
      roundFilter.value = null;
      running.value = false;
    }

    // Every campaign fetch carries a token. A viewer clicking through the rail
    // faster than the network answers would otherwise have an earlier
    // campaign's episodes land on top of a later selection.
    let generation = 0;

    /** Load a campaign whole, without the paced replay.
     *
     * Selecting a campaign should show it. The replay exists to *narrate* a
     * campaign — blocked, blocked, then through, at a speed a room can follow
     * — which is a different job from reading one, and making the read wait on
     * the narration left three empty panes staring at anyone who just wanted
     * to look at the numbers.
     */
    async function open(campaign) {
      const token = ++generation;
      setLink("loading");
      try {
        const body = await fetch(`/api/campaign/${campaign.id}`).then((r) => r.json());
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
        const health = await fetch("/api/health").then((r) => r.json());
        mode.value = health.mode;
        campaigns.value = await fetch("/api/campaigns").then((r) => r.json());
        selected.value = campaigns.value.find((c) => c.adaptive) ?? campaigns.value[0] ?? null;
        if (selected.value) await open(selected.value);
      } catch {
        setLink("could not reach the API", "fault");
      }
    }

    function select(campaign) {
      if (campaign.id === selected.value?.id) return;
      // Closing first is load-bearing: a socket left open would keep pushing
      // the previous campaign's episodes into the list we just cleared.
      close();
      reset();
      selected.value = campaign;
      open(campaign);
    }

    function replay() {
      if (!selected.value) return;
      close();
      reset();
      // Abandon any in-flight load, so its episodes cannot arrive mid-replay.
      generation++;
      running.value = true;
      setLink("connecting");

      const scheme = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${location.host}/ws/replay/${selected.value.id}`);

      socket.onopen = () => setLink("streaming", "live");
      socket.onmessage = ({ data }) => {
        const message = JSON.parse(data);
        if (message.type === "summary") {
          summary.value = message.summary;
        } else if (message.type === "episode") {
          episodes.value = [...episodes.value, message.episode];
        } else if (message.type === "done") {
          setLink("complete", "live");
          running.value = false;
        } else if (message.type === "error") {
          setLink(message.detail, "fault");
          running.value = false;
        }
      };
      socket.onerror = () => setLink("connection failed", "fault");
      socket.onclose = () => {
        running.value = false;
        if (link.value.text === "streaming") setLink("disconnected", "fault");
      };
    }

    // A selection that the filter excludes would leave the chain and verdict
    // panes describing an episode the feed is not showing.
    watch(roundFilter, (round) => {
      if (round !== null && picked.value && picked.value.round !== round) picked.value = null;
    });

    onMounted(load);
    onBeforeUnmount(close);

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
