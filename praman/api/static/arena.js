/* The arena's root component: facets, the replay socket, and state.
 *
 * Vue 3 Composition API against the vendored global build. No build step, no
 * node_modules, no committed bundle — `git clone` then run the server, and the
 * arena is there.
 *
 * Rail and control are *facets over the committed campaign set*, not live
 * switches: the arena replays results rather than computing them, so choosing
 * "uap" and "Tier 1+2+3" means loading the campaign that was actually run that
 * way. `python -m praman matrix` generates the grid those facets index.
 */

import {
  AsrCurve,
  AttackFeed,
  Controls,
  MandateChain,
  Scoreboard,
  VerdictPanel,
} from "./components.js";

const { createApp, computed, onMounted, onBeforeUnmount, ref, watch } = Vue;

const App = {
  components: { Scoreboard, Controls, AttackFeed, MandateChain, VerdictPanel, AsrCurve },

  setup() {
    const campaigns = ref([]);
    const rail = ref("autopay");
    const tiersKey = ref("1");
    const roundFilter = ref(null);

    const mode = ref("—");
    const link = ref({ text: "idle", on: false });
    const episodes = ref([]);
    const summary = ref(null);
    const running = ref(false);

    // Null until the viewer clicks. While it stays null the panes follow the
    // stream; once they choose an episode, the view stops moving under them.
    const picked = ref(null);

    let socket = null;
    const setLink = (text, on = false) => (link.value = { text, on });

    /** The campaign behind the current facets, preferring the adaptive one. */
    const chosen = computed(() => {
      const matches = campaigns.value.filter(
        (c) => c.rail === rail.value && (c.tiers ?? []).join(",") === tiersKey.value
      );
      return matches.find((c) => c.adaptive) ?? matches[0] ?? null;
    });

    const shown = computed(() =>
      roundFilter.value === null
        ? episodes.value
        : episodes.value.filter((e) => e.round === roundFilter.value)
    );

    const rounds = computed(() =>
      [...new Set(episodes.value.map((e) => e.round))].sort((a, b) => a - b)
    );

    const current = computed(() => picked.value ?? shown.value.at(-1) ?? null);

    async function load() {
      try {
        mode.value = `mode ${(await fetch("/api/health").then((r) => r.json())).mode}`;
        campaigns.value = await fetch("/api/campaigns").then((r) => r.json());
        const first = campaigns.value.find((c) => c.adaptive) ?? campaigns.value[0];
        if (first) {
          rail.value = first.rail;
          tiersKey.value = (first.tiers ?? []).join(",");
        }
      } catch {
        setLink("could not reach the API");
      }
    }

    function replay() {
      if (!chosen.value) return;
      socket?.close();
      episodes.value = [];
      summary.value = null;
      picked.value = null;
      roundFilter.value = null;
      running.value = true;
      setLink("connecting");

      const scheme = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${location.host}/ws/replay/${chosen.value.id}`);

      socket.onopen = () => setLink("streaming", true);
      socket.onmessage = ({ data }) => {
        const message = JSON.parse(data);
        if (message.type === "summary") {
          summary.value = message.summary;
        } else if (message.type === "episode") {
          episodes.value = [...episodes.value, message.episode];
        } else if (message.type === "done") {
          setLink("complete", true);
          running.value = false;
        } else if (message.type === "error") {
          setLink(message.detail);
          running.value = false;
        }
      };
      socket.onerror = () => setLink("connection failed");
      socket.onclose = () => {
        running.value = false;
        if (link.value.text === "streaming") setLink("disconnected");
      };
    }

    // Changing a facet invalidates what is on screen: it belongs to a campaign
    // the viewer is no longer looking at.
    watch([rail, tiersKey], () => {
      episodes.value = [];
      summary.value = null;
      picked.value = null;
      roundFilter.value = null;
      setLink("idle");
    });

    onMounted(load);
    onBeforeUnmount(() => socket?.close());

    return {
      campaigns,
      rail,
      tiersKey,
      roundFilter,
      rounds,
      chosen,
      mode,
      link,
      episodes,
      shown,
      summary,
      running,
      picked,
      current,
      replay,
      select: (episode) => (picked.value = episode),
    };
  },

  template: `
    <header class="mast">
      <div class="brand">
        <span class="mark">प्रमाण</span>
        <span class="name">Praman Arena</span>
        <span class="tag">breach &amp; attack simulation · payment mandate controls</span>
      </div>
      <div class="controls">
        <button class="run" @click="replay" :disabled="running || !chosen">Replay</button>
        <span class="badge">{{ chosen ? chosen.id : 'no campaign' }}</span>
        <span class="badge">{{ mode }}</span>
        <span class="badge" :class="link.on ? 'on' : 'dim'">{{ link.text }}</span>
      </div>
    </header>

    <Controls
      :campaigns="campaigns"
      :rail="rail" @update:rail="rail = $event"
      :tiers-key="tiersKey" @update:tiersKey="tiersKey = $event"
      :round="roundFilter" @update:round="roundFilter = $event"
      :rounds="rounds"/>

    <Scoreboard :summary="summary"/>

    <main class="grid">
      <AttackFeed :episodes="shown" :selected-id="picked?.episode_id" @select="select"/>
      <MandateChain :episode="current"/>
      <VerdictPanel :episode="current"/>
      <AsrCurve :episodes="episodes"/>
    </main>
  `,
};

createApp(App).mount("#app");
