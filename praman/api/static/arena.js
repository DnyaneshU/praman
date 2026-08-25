/* The arena's root component: campaign selection, the replay socket, and state.
 *
 * Vue 3 Composition API against the vendored global build. No build step, no
 * node_modules, no committed bundle — `git clone` then run the server, and the
 * arena is there.
 */

import { AsrCurve, AttackFeed, MandateChain, Scoreboard, VerdictPanel } from "./components.js";

const { createApp, computed, onMounted, onBeforeUnmount, ref } = Vue;

const App = {
  components: { Scoreboard, AttackFeed, MandateChain, VerdictPanel, AsrCurve },

  setup() {
    const campaigns = ref([]);
    const chosen = ref("");
    const mode = ref("—");
    const link = ref({ text: "idle", on: false });
    const episodes = ref([]);
    const summary = ref(null);
    const running = ref(false);

    // Null until the viewer clicks. While it stays null the panes follow the
    // stream; once they choose an episode, the view stops moving under them.
    const picked = ref(null);
    const current = computed(() => picked.value ?? episodes.value.at(-1) ?? null);

    let socket = null;

    const setLink = (text, on = false) => (link.value = { text, on });

    async function load() {
      try {
        const health = await fetch("/api/health").then((r) => r.json());
        mode.value = `mode ${health.mode}`;

        campaigns.value = await fetch("/api/campaigns").then((r) => r.json());
        // The adaptive campaign is the one that tells the story; open on it.
        const adaptive = campaigns.value.find((c) => c.adaptive);
        chosen.value = (adaptive ?? campaigns.value[0])?.id ?? "";
      } catch {
        setLink("could not reach the API");
      }
    }

    function replay() {
      socket?.close();
      episodes.value = [];
      summary.value = null;
      picked.value = null;
      running.value = true;
      setLink("connecting");

      const scheme = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${location.host}/ws/replay/${chosen.value}`);

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

    onMounted(load);
    onBeforeUnmount(() => socket?.close());

    return {
      campaigns,
      chosen,
      mode,
      link,
      episodes,
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
        <label class="field">
          <span>campaign</span>
          <select v-model="chosen" :disabled="running">
            <option v-for="c in campaigns" :key="c.id" :value="c.id">
              {{ c.id }} · {{ c.episodes }} episodes · {{ c.rounds }} round{{ c.rounds > 1 ? 's' : '' }}
            </option>
          </select>
        </label>
        <button class="run" @click="replay" :disabled="running || !chosen">Replay</button>
        <span class="badge">{{ mode }}</span>
        <span class="badge" :class="link.on ? 'on' : 'dim'">{{ link.text }}</span>
      </div>
    </header>

    <Scoreboard :summary="summary"/>

    <main class="grid">
      <AttackFeed :episodes="episodes" :selected-id="picked?.episode_id" @select="select"/>
      <MandateChain :episode="current"/>
      <VerdictPanel :episode="current"/>
      <AsrCurve :episodes="episodes"/>
    </main>
  `,
};

createApp(App).mount("#app");
