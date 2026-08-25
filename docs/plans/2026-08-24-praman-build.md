# Praman Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan session-by-session. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a breach-and-attack-simulation harness for agentic payment mandate controls — an adaptive attacker, a three-tier defense, a ledger that is the sole authority on harm, and a live arena — submitted to the Mastercard Innovation Challenge by 31 Aug 2026.

**Architecture:** One FastAPI process, three packages (`range` / `red` / `blue`) plus an `api` surface and a `arena` React app. The invariant gate runs **out-of-band** as a reference monitor between the agent and the ledger. The mutator is pluggable so the LLM path is optional, never required.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, stdlib `sqlite3`, `cryptography` (ECDSA P-256), LightGBM, sentence-transformers, Vite + React + TypeScript + Tailwind + Recharts, Docker, GitHub Actions.

**Spec:** `Praman Handbook` (part zero) and `Praman Build Stack` (part three) — published artifacts; sections referenced by number below.

---

## Global Constraints

- **Python 3.12.7** exactly (not 3.13 — ML wheels). Node 20+.
- **Nothing touches a real payment rail.** Local test keys, SQLite ledger, YAML merchant fixtures.
- **The app must import and serve with no `ANTHROPIC_API_KEY` present.** Any Anthropic client is constructed lazily, inside the function that calls it — never at module import.
- **Money is `Decimal`, stored as integer paise.** Never float. Never `==` on floats.
- **Every verdict names its reason.** A block that cannot say which invariant failed is a bug.
- **Harm is ledger-verified.** No model, scorer or heuristic decides whether harm occurred — only an account balance delta.
- **Seeded RNG everywhere** (`--seed`, default 1729). Same seed reproduces every result field; `timestamp` and `latency_ms` are measurements of the run, not results from it, and are excluded by name.
- **`refusal` is a first-class episode verdict**, distinct from `block`. An LLM refusal must never be counted as a defended attack.
- Ruff clean, pytest green before every commit. Commit at the end of every task.

---

## File Structure

```
praman/
├─ pyproject.toml            uv deps, ruff + pytest config
├─ Makefile                  dev · demo · campaign · test · build
├─ Dockerfile                multi-stage: node build → python runtime
├─ .env.example              ANTHROPIC_API_KEY placeholder (real .env gitignored)
├─ .github/workflows/ci.yml
├─ praman/
│  ├─ money.py               Decimal/paise helpers — single source of truth
│  ├─ range/
│  │  ├─ mandates.py         Pydantic models + canonical bytes
│  │  ├─ signing.py          ECDSA P-256 sign/verify, keyring
│  │  ├─ ledger.py           SQLite, BEGIN IMMEDIATE, atomic settle
│  │  ├─ catalog.py          merchant + product fixtures loader
│  │  ├─ context.py          RangeContext — keys, catalog, ledger, profile
│  │  ├─ agent.py            victim agent: scripted + llm backends
│  │  └─ profiles/
│  │     ├─ base.py          RailProfile ABC
│  │     ├─ autopay.py       UPI Autopay
│  │     ├─ uap.py           NPCI UAP delegate
│  │     └─ ap2.py           AP2 cart chain
│  ├─ red/
│  │  ├─ corpus.yaml         all 14 seeds, `implemented:` flag
│  │  ├─ episode.py          Episode record
│  │  ├─ attacks/
│  │  │  ├─ base.py          Attack ABC + registry
│  │  │  ├─ structural.py    S-01 … S-04
│  │  │  └─ semantic.py      M-08, M-09
│  │  ├─ mutator/
│  │  │  ├─ base.py          Mutator protocol
│  │  │  ├─ search.py        deterministic strategy search (default)
│  │  │  └─ llm.py           Anthropic-backed mutator (optional)
│  │  ├─ selector.py         fitness + survivor selection
│  │  └─ campaign.py         multi-round runner → JSONL
│  ├─ blue/
│  │  ├─ verdict.py          Verdict model
│  │  ├─ invariants.py       named invariant checks (Tier 1)
│  │  ├─ monitor.py          out-of-band reference monitor
│  │  ├─ features.py         episode → feature vector
│  │  ├─ anomaly.py          LightGBM (Tier 2)
│  │  ├─ divergence.py       embeddings (Tier 3)
│  │  └─ defense.py          tier orchestration
│  ├─ metrics.py             ASR, adaptive delta, ₹, latency, benign rate
│  └─ api/
│     ├─ main.py             FastAPI app, static mount, WS
│     └─ replay.py           committed-campaign replay
├─ arena/                    Vite + React + TS
├─ fixtures/                 merchants.yaml, products.yaml, benign_tasks.yaml
├─ results/                  committed campaign_*.jsonl
└─ tests/
```

---

## Session 1 — The Range

**Goal:** A signed mandate chain settles against an atomic ledger. No LLM, no attacks, no defense.

**Files:**
- Create: `pyproject.toml`, `Makefile`, `.gitignore`, `.env.example`
- Create: `praman/money.py`, `praman/range/{mandates,signing,ledger,catalog,context}.py`, `praman/range/profiles/{base,autopay}.py`
- Create: `fixtures/merchants.yaml`, `fixtures/products.yaml`
- Test: `tests/test_money.py`, `tests/test_mandates.py`, `tests/test_signing.py`, `tests/test_ledger.py`

**Interfaces produced:**
```python
# money.py
def rupees(x: str | int) -> Decimal        # "3940.50" -> Decimal paise 394050
def fmt(paise: Decimal) -> str             # "₹3,940.50"

# mandates.py
class LineItem(BaseModel):
    sku: str; name: str; price: Decimal; qty: int; visible: bool = True
class IntentMandate(BaseModel):
    mandate_id: str; principal: str; description: str; max_amount: Decimal
    allowed_categories: list[str]; expires_at: datetime; nonce: str
    signature: str | None = None
class CartMandate(BaseModel):
    mandate_id: str; intent_id: str; merchant_id: str; items: list[LineItem]
    total: Decimal; display_summary: str; expires_at: datetime; nonce: str
    signature: str | None = None
class PaymentMandate(BaseModel):
    mandate_id: str; cart_id: str; beneficiary: str; amount: Decimal
    expires_at: datetime; nonce: str; signature: str | None = None
class MandateChain(BaseModel):
    intent: IntentMandate; cart: CartMandate; payment: PaymentMandate

# signing.py
def canonical_bytes(m: BaseModel) -> bytes          # sorted keys, signature excluded
class Keyring:
    def generate(self, holder: str) -> None
    def sign(self, m: BaseModel, holder: str) -> str
    def verify(self, m: BaseModel, holder: str) -> bool

# ledger.py
class SettlementResult(BaseModel):
    settled: bool; amount: Decimal; beneficiary: str; reason: str | None = None
class Ledger:
    def __init__(self, path: str | Path)
    def open_account(self, account_id: str, balance: Decimal) -> None
    def balance(self, account_id: str) -> Decimal
    def redeem_nonce(self, nonce: str) -> bool       # atomic; False if consumed
    def settle(self, payment: PaymentMandate, source: str) -> SettlementResult
    def total_moved_to(self, beneficiary: str) -> Decimal
    def snapshot(self) -> dict[str, Decimal]

# profiles/base.py
class RailProfile(ABC):
    name: str
    def build_intent(self, task: dict, ctx) -> IntentMandate
    def invariant_ids(self) -> list[str]
```

**Tasks:**
- [ ] **T1.1** `git init`; `pyproject.toml` with deps and ruff/pytest config; `.gitignore` including `.env`, `*.db`, `arena/node_modules`; `.env.example`. Commit.
- [ ] **T1.2** `money.py` — test first: `rupees("3940.50") == Decimal(394050)`, `fmt` output, and that no float ever appears. Commit.
- [ ] **T1.3** `mandates.py` models. Test: construction, `Decimal` coercion, rejection of negative amounts. Commit.
- [ ] **T1.4** `signing.py`. Tests: sign→verify roundtrip passes; **mutating any field after signing makes verify fail**; `canonical_bytes` is stable across dict ordering. Commit.
- [ ] **T1.5** `ledger.py` schema + `settle`. Tests: balance conservation (sum of all accounts constant); settle debits source and credits beneficiary; insufficient funds returns `settled=False` with a reason. Commit.
- [ ] **T1.6** `redeem_nonce` atomicity. Test: two threads redeeming the same nonce — exactly one gets `True`. This is the S-03 substrate; it must be a real race test, not a mocked one. Commit.
- [ ] **T1.7** `fixtures/*.yaml` + `catalog.py` + `context.py` + `profiles/autopay.py`. Commit.
- [ ] **T1.8** `Makefile` with `dev`, `demo`, `test`, `campaign`; `make demo` runs a scripted honest purchase end to end. Commit.

**Gate:**
```
make test      → all green
make demo      → prints the three signed mandates, "SETTLED ₹3,940.00",
                 and a ledger snapshot whose totals are unchanged
```

---

## Session 2 — Victim agent, structural attacks, baseline

**Goal:** Four structural attacks succeed against an undefended range, and we have a baseline number to beat.

**Files:**
- Create: `praman/range/agent.py`, `praman/red/{episode,selector}.py`, `praman/red/attacks/{base,structural}.py`, `praman/red/corpus.yaml`, `praman/metrics.py`
- Create: `fixtures/benign_tasks.yaml`
- Test: `tests/test_attacks_structural.py`, `tests/test_metrics.py`

**Interfaces produced:**
```python
# agent.py
class VictimAgent(Protocol):
    model_name: str
    def shop(self, task: dict, ctx: RangeContext) -> MandateChain
class ScriptedAgent(VictimAgent): ...      # no LLM — default
class LLMAgent(VictimAgent): ...           # lazy Anthropic client, Session 5

# attacks/base.py
class Attack(ABC):
    id: str; name: str; attack_class: Literal["structural","semantic","india"]
    def apply(self, chain: MandateChain, ctx: RangeContext) -> MandateChain
    def beneficiary(self, ctx) -> str
ATTACKS: dict[str, type[Attack]]           # registry, keyed "S-01" …

# episode.py
class Episode(BaseModel):
    episode_id: str; round: int; attack_id: str
    lineage: list[str] = []; strategy: str | None = None
    rail_profile: str; victim_model: str | None = None
    verdict: Literal["allow","block","refusal","error"]
    blocked_by_tier: int | None = None; violated_invariant: str | None = None
    rupees_moved: Decimal; beneficiary: str | None = None
    latency_ms: dict[str, float] = {}; seed: int; timestamp: datetime
def write_jsonl(episodes: list[Episode], path: Path) -> None
def read_jsonl(path: Path) -> list[Episode]

# metrics.py
def asr(eps: list[Episode]) -> float                  # excludes verdict=="refusal"
def asr_by_round(eps) -> list[float]
def rupees_moved(eps) -> Decimal
def benign_pass_rate(eps) -> float
def refusal_rate(eps) -> float
```

**Tasks:**
- [ ] **T2.1** `attacks/base.py` registry + `episode.py` with `refusal` in the verdict enum from the start. Test round-trip JSONL with `Decimal` preserved. Commit.
- [ ] **T2.2** `ScriptedAgent` — builds an honest chain from a task fixture. Test: produces a chain that settles and passes signature verification. Commit.
- [ ] **T2.3** S-01 cart substitution. Test-first: apply to an honest chain, assert money reaches the attacker beneficiary and `rupees_moved > 0`. Commit.
- [ ] **T2.4** S-02 beneficiary rebinding. Same test shape. Commit.
- [ ] **T2.5** S-03 token-redemption race — must exercise the real concurrent path from T1.6. Test: one mandate, two settlements, both succeed while undefended. Commit.
- [ ] **T2.6** S-04 mandate replay across merchants. Commit.
- [ ] **T2.7** `metrics.py` + `benign_tasks.yaml`. Test: `asr` ignores refusals; `benign_pass_rate` is 1.0 undefended. Commit.
- [ ] **T2.8** `red/runner.py` baseline campaign → `results/baseline.jsonl`. Commit results.

**Gate:**
```
make campaign --baseline
→ "Undefended ASR: 100.0% (4/4 attacks)   ₹ moved: ₹XX,XXX   benign pass: 100%"
→ results/baseline.jsonl exists and re-runs identically under the same seed
```

---

## Session 3 — Tier 1, evidence, semantic attacks

**Goal:** Structural ASR collapses to ~0, every block names its invariant, and benign traffic still passes.

**Files:**
- Create: `praman/blue/{verdict,invariants,monitor,defense}.py`, `praman/red/attacks/semantic.py`
- Modify: `praman/range/ledger.py` — route settlement through the monitor
- Test: `tests/test_invariants.py`, `tests/test_monitor.py`, `tests/test_attacks_semantic.py`

**Interfaces produced:**
```python
# verdict.py
class Verdict(BaseModel):
    allowed: bool; tier: int | None = None; invariant: str | None = None
    observed: str | None = None; expected: str | None = None
    score: float | None = None; latency_ms: float = 0.0
    def reason(self) -> str          # "inv-02: payment.beneficiary must equal cart.issuer"

# invariants.py
class Invariant(ABC):
    id: str; name: str
    def check(self, chain: MandateChain, ctx) -> Verdict
INVARIANTS: dict[str, Invariant]
# inv-01 cart_within_intent   inv-02 beneficiary_binds_cart_issuer
# inv-03 total_under_ceiling  inv-04 nonce_fresh_and_unconsumed
# inv-05 chain_signatures_valid inv-06 no_hidden_line_items
# inv-07 ttl_live             inv-08 spend_within_delegated_cap

# defense.py
class Defense:
    def __init__(self, tiers: list[int], ctx)
    def evaluate(self, chain: MandateChain) -> Verdict
```

**Tasks:**
- [ ] **T3.1** `verdict.py` + `invariants.py` skeleton with `inv-01`. Test-first: S-01 blocked, honest chain allowed, `verdict.invariant == "inv-01"`. Commit.
- [ ] **T3.2** `inv-02` → blocks S-02. `inv-04` → blocks S-03. `inv-05`+`inv-07` → block S-04. One test per invariant asserting **both** the block and the specific invariant id. Commit after each.
- [ ] **T3.3** `monitor.py` — out-of-band interception. Test: settlement is impossible without passing the monitor (call the ledger directly in a test and assert it raises). Commit.
- [ ] **T3.4** M-08 branded whisper + `inv-06`; M-09 hidden line item. `ScriptedAgent` gains a `susceptible: bool` flag so semantic attacks land with no LLM. Commit.
- [ ] **T3.5** Latency instrumentation into `Verdict.latency_ms`; benign regression run. Commit.

**Gate:**
```
make campaign --tier1
→ "Structural ASR: 0.0%   Semantic ASR: 0.0%   benign pass: 100%   Tier-1 latency p50: <1ms"
→ every blocked episode has a non-null violated_invariant
```

---

## Session 4 — The adaptive loop  ⚠ PROTECTED

**Goal:** Adaptive ASR measurably exceeds static ASR. **If this session fails, the submission loses its thesis.**

**Files:**
- Create: `praman/red/mutator/{base,search,llm}.py`, `praman/red/campaign.py`
- Modify: `praman/red/selector.py`, `praman/metrics.py`
- Test: `tests/test_mutator_search.py`, `tests/test_campaign.py`

**Interfaces produced:**
```python
# mutator/base.py
class Mutator(Protocol):
    name: str
    def mutate(self, chain: MandateChain, attack: Attack,
               verdict: Verdict, ctx) -> list[MandateChain]

# mutator/search.py
class Strategy(BaseModel):
    id: str; targets: list[str]        # invariant ids it tries to evade
    def apply(self, chain, ctx) -> MandateChain
class SearchMutator(Mutator):
    name = "search"
    STRATEGIES: dict[str, list[Strategy]]   # keyed by violated invariant id

# campaign.py
def run_campaign(*, rounds: int, episodes_per_round: int, profile: str,
                 mutator: Mutator, defense: Defense, seed: int,
                 out: Path) -> Path

# metrics.py additions
def static_asr(eps) -> float          # round 0 only
def adaptive_asr(eps) -> float        # final round
def adaptive_delta(eps) -> float
def rounds_to_rebreak(eps) -> int | None
```

**Tasks:**
- [ ] **T4.1** `Mutator` protocol + `Strategy` registry. Commit.
- [ ] **T4.2** **Prove the mechanism narrowly first.** Strategies for `inv-02` only (beneficiary binding): 4–6 variants — alias VPA, homoglyph merchant id, sub-merchant indirection, late rebind after monitor read. Test: S-02 blocked at round 0, at least one strategy gets through by round 3. Commit.
- [ ] **T4.3** Only once T4.2 is green, widen: strategies targeting `inv-01`, `inv-04`, `inv-06`. Commit each.
- [ ] **T4.4** `selector.py` — fitness = ₹ moved, then proximity to a pass. Keep top-k, retire the rest, record `lineage`. Commit.
- [ ] **T4.5** `campaign.py` multi-round runner, seeded, writing JSONL per round. Commit.
- [ ] **T4.6** `metrics.py` adaptive delta + `rounds_to_rebreak`. Commit.
- [ ] **T4.7** `mutator/llm.py` — **lazy** Anthropic client, `claude-opus-5`, `thinking={"type":"adaptive"}`, `output_config={"effort":"high"}`, structured output for the mutated chain, `stop_reason == "refusal"` recorded as `verdict="refusal"`. Skipped by test when no credential. Commit.

**Gate:**
```
make campaign --rounds 5
→ "Static ASR: 0.0%   Adaptive ASR: NN.N%   adaptive delta: +NN.N pts"
→ adaptive delta strictly > 0
→ results/campaign_adaptive.jsonl reproduces under the same seed
```
**If the gate fails by end of session:** fall back to the documented cut — templated mutation over a fixed strategy list — and reduce the claim to "adaptive in structure." Do not spend Session 5 here.

---

## Session 5 — Tiers 2 and 3, second rail

**Goal:** A control that learned from Red beats one that did not; the rail flag switches worlds.

**Files:**
- Create: `praman/blue/{features,anomaly,divergence}.py`, `praman/range/profiles/{uap,ap2}.py`
- Modify: `praman/blue/defense.py`, `praman/range/agent.py` (LLM backend)
- Test: `tests/test_features.py`, `tests/test_anomaly.py`, `tests/test_profiles.py`

**Interfaces produced:**
```python
# features.py
FEATURE_NAMES: list[str]
def extract(chain: MandateChain, ctx) -> dict[str, float]
# category_drift, price_to_ceiling_ratio, beneficiary_age_days,
# beneficiary_novelty, interstage_ms, catalog_source_score,
# cumulative_spend_ratio, item_count, hidden_item_count

# anomaly.py
class AnomalyTier:
    def train(self, eps: list[Episode], ctx) -> None
    def score(self, chain, ctx) -> Verdict          # tier=2
    def save(self, path) / def load(self, path)
    def explain(self, chain, ctx) -> dict[str, float]   # SHAP

# divergence.py
class DivergenceTier:
    def __init__(self, threshold: float = 0.42)
    def score(self, chain, ctx) -> Verdict          # tier=3, escalates not blocks
```

**Tasks:**
- [ ] **T5.1** `features.py` + tests asserting each feature separates an attack episode from a benign one. Commit.
- [ ] **T5.2** `anomaly.py` LightGBM train/score/save/load on Session-4 survivors. Test: trained model catches ≥1 attack Tier 1 missed; benign pass rate stays ≥95%. Commit.
- [ ] **T5.3** SHAP attribution surfaced in the verdict. Commit.
- [ ] **T5.4** `divergence.py` with sentence-transformers, **downloaded and cached in this session** (torch is a large install — do not discover it on Sunday). Escalate above threshold; never auto-block. Commit.
- [ ] **T5.5** `profiles/uap.py` — delegate scope, spend ceiling, agent identity, `inv-08`. Test: the same S-05-shaped attack behaves differently per profile. Commit.
- [ ] **T5.6** `profiles/ap2.py` (thin — cart chain shape only). Commit.
- [ ] **T5.7** `LLMAgent` behind `--victim-model`; record `victim_model` per episode. Commit.

**Gate:**
```
make campaign --tiers 1,2,3 --profile autopay
make campaign --tiers 1,2,3 --profile uap
→ Tier-2-trained ASR < Tier-1-only ASR on round ≥2 survivors
→ benign pass ≥95%, latency reported per tier
```

---

## Session 6 — The arena and the API

**Goal:** A stranger watches the loop run and understands it without narration.

**Files:**
- Create: `praman/api/{main,replay}.py`
- Create: `arena/` — `index.html`, `src/{main.tsx,App.tsx}`, `src/components/{AttackFeed,MandateChain,VerdictPanel,ASRCurve,Controls}.tsx`, `src/types.ts`, `tailwind.config.js`, `vite.config.ts`
- Create: `Dockerfile`
- Test: `tests/test_api.py`

**Interfaces produced:**
```
GET  /api/health                    -> {"status":"ok","mode":"replay|live"}
GET  /api/campaigns                 -> [{id, rounds, episodes, created}]
GET  /api/campaign/{id}/summary     -> full metrics block
WS   /ws/replay/{id}                -> streams Episode JSON at demo speed
WS   /ws/live                       -> live campaign stream; 403 when mode=replay
POST /api/campaign/start            -> 403 when mode=replay
```
`arena/src/types.ts` mirrors `Episode` and `Verdict` exactly.

**Tasks:**
- [ ] **T6.1** `api/main.py` + `/api/health`; assert the app imports with `ANTHROPIC_API_KEY` unset. Commit.
- [ ] **T6.2** `replay.py` + `/ws/replay/{id}`. Test with a WS test client. Commit.
- [ ] **T6.3** Vite + React + TS + Tailwind scaffold; `types.ts` mirroring the Python models. Commit.
- [ ] **T6.4** `AttackFeed` — scrolling episode list, mutation lineage shown as `↳ mutated ×3`. Commit.
- [ ] **T6.5** `MandateChain` — hand-rolled SVG, Intent → Cart → Payment, tampered link struck in crimson, hidden line item revealed. **This is the centerpiece; give it the most time.** Commit.
- [ ] **T6.6** `VerdictPanel` — invariant id, observed vs expected, tier, latency. Commit.
- [ ] **T6.7** `ASRCurve` — Recharts, ASR by round, annotated retrain points. Commit.
- [ ] **T6.8** `Controls` — round stepper, rail-profile switch, tier toggles. Commit.
- [ ] **T6.9** `Dockerfile` multi-stage; `npm run build` → static served by FastAPI; non-root user; `EXPOSE 8000`. Verify `docker build` and `docker run` locally. Commit.

**Gate:**
```
make dev            → arena at localhost:8000, campaign streams live
docker build -t praman . && docker run -p 8000:8000 -e PRAMAN_MODE=replay praman
                    → replay works in the container with no credential present
```

---

## Session 7 — Results, deploy, demo

**Goal:** Submitted, with a URL that works and a video that carries the pitch.

**Files:**
- Create: `.github/workflows/ci.yml`, `README.md`, `docs/DEMO.md`, `docs/deck-outline.md`
- Create: `results/campaign_final.jsonl`, `results/summary.json`

**Tasks:**
- [ ] **T7.1** Final campaign at full scale, `--seed 1729`, all tiers, both profiles. Commit `results/`.
- [ ] **T7.2** CI workflow — ruff + pytest on push; README badge. Commit.
- [ ] **T7.3** README: video at top, one-command repro, the honesty section (§12 ground rules), architecture diagram, metrics table. Commit.
- [ ] **T7.4** Deploy (conditions below). Verify the public URL cold.
- [ ] **T7.5** `docs/DEMO.md` — the 90-second script, beat by beat, with exact commands and expected on-screen output.
- [ ] **T7.6** Record the video. Upload. Embed in README.
- [ ] **T7.7** Deck outline built on the curves, not on prose.
- [ ] **T7.8** Fresh-clone rehearsal: clone into a clean directory, follow the README exactly, confirm it runs. Fix whatever breaks.

**Gate:** a stranger clones, runs `make demo`, and sees the loop — with no credential and no instructions from us.

---

## Exact deploy conditions

**Mode.** The deployed app runs `PRAMAN_MODE=replay`. In this mode `/ws/live` and `POST /api/campaign/start` return 403, and no Anthropic client is ever constructed. This is enforced in code, not by convention.

**Import safety.** `ANTHROPIC_API_KEY` is absent in production. Any `Anthropic()` construction lives inside the calling function. `tests/test_api.py` asserts the app imports with the variable unset — this test is what stops a 3am regression.

**Container.**
```dockerfile
FROM node:20-alpine AS web
WORKDIR /w
COPY arena/package*.json ./
RUN npm ci
COPY arena/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PRAMAN_MODE=replay
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY praman/ ./praman/
COPY fixtures/ ./fixtures/
COPY results/ ./results/
COPY --from=web /w/dist ./praman/api/static
RUN useradd -m app && chown -R app /app
USER app
EXPOSE 8000
CMD ["sh","-c","uvicorn praman.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

**Host binding.** Must bind `0.0.0.0` and honour `$PORT` — both Railway and Fly inject it. Binding `127.0.0.1` is the single most common cause of a deploy that builds and then health-checks dead.

**Platform.** Railway: connect the repo, it detects the Dockerfile, set `PRAMAN_MODE=replay`, deploy. Fly: `fly launch --no-deploy`, set `internal_port = 8000` in `fly.toml`, `fly secrets set PRAMAN_MODE=replay`, `fly deploy`. Railway is the shorter path; Fly gives a more predictable free allowance. **Verify current free-tier terms before committing to either — they change, and I can't confirm today's from here.**

**Healthcheck.** `GET /api/health` returning 200. Configure it explicitly; without it a hung worker looks healthy.

**Image size.** `sentence-transformers` pulls torch (~2GB) and will blow past small image limits. Tier 3 in the deployed container runs from **precomputed divergence scores stored in the campaign JSONL**, so torch is a dev dependency only and not installed in the runtime image. Decide this at T5.4, not at deploy time.

**What is NOT deployed.** No live campaigns, no API credential, no database beyond the committed SQLite snapshot, no auth, no user accounts.

---

## Testing strategy

Testing is **per-session, not a phase.** Every task is test-first, and each session's gate is a command with expected output rather than a judgement call.

| Layer | What is tested | Where |
|---|---|---|
| Money | No float ever; paise conversion exact | `test_money.py` |
| Mandates | Sign→verify roundtrip; any tamper fails verification | `test_signing.py` |
| Ledger | Balance conservation; real concurrent nonce race | `test_ledger.py` |
| Attacks | Each attack succeeds undefended (else the defense proves nothing) | `test_attacks_*.py` |
| Invariants | Each blocks its attack **and names the right invariant id** | `test_invariants.py` |
| Monitor | Ledger cannot be reached bypassing the monitor | `test_monitor.py` |
| Mutator | Blocked attack yields ≥1 variant that gets through | `test_mutator_search.py` |
| Campaign | Same seed → identical results (timestamp/latency excluded) | `test_reproducibility.py` |
| API | Imports with no credential; replay streams; live is 403 in replay mode | `test_api.py` |

Two properties are worth more than the rest combined: **every attack must succeed undefended**, and **every block must name its invariant.** Without the first, the defense is measuring nothing. Without the second, the explainability claim is false.

---

## The demo, prepared

`make demo` runs this deterministically, and `docs/DEMO.md` scripts the narration.

| Beat | On screen | Said |
|---|---|---|
| 1 · 0:00 | Honest purchase settles. Chain green. | "An agent buys shoes. ₹3,940. Every signature valid." |
| 2 · 0:15 | S-02 runs. Tier 1 blocks. Panel reads `inv-02: payment.beneficiary must equal cart.issuer`. | "A documented attack. Blocked, and the control says exactly why." |
| 3 · 0:30 | Mutator on. Feed shows `↳ mutated ×1 … ×2 … ×3`. | "Now the attacker reads that rejection and rewrites itself." |
| 4 · 0:45 | Round 3: a variant passes. Ledger ticks. ₹ to `mule-vpa@axl`. | "Same attack class. Same control. It knew — and it still fell." |
| 5 · 1:00 | Retrain. Curve bends 41% → 12% → 4%. | "Tier 2 trains on what got through. The curve bends." |
| 6 · 1:15 | Rail switch Autopay → UAP. | "That was UPI Autopay — live in Indian banks today. This is UAP, which NPCI is about to approve. Nothing is watching it yet." |

**Fallbacks, in order:** live arena → deployed URL → recorded video → static curve PNGs in the deck. Assume the live demo fails; the video is what gets scored.

---

## Self-review

**Spec coverage.** Range ✓ S1. Victim agent ✓ S2/S5. 6 attacks ✓ S2/S3. Tier 1 ✓ S3. Tier 2/3 ✓ S5. Mutator ✓ S4. Rail profiles ✓ S1/S5. Arena ✓ S6. Metrics ✓ S2/S4. Deploy ✓ S6/S7. Demo ✓ S7.

**Known gaps, accepted:** S-05→S-07, M-10→M-12, I-13, I-14 stay documented and unimplemented — recorded in `corpus.yaml` with `implemented: false`. AP2 profile is thin. This matches the agreed scope; widen only if more hands arrive.

**Type consistency.** `Verdict` is produced by `invariants.py`, `anomaly.py`, `divergence.py` and consumed by `defense.py` and `arena/src/types.ts` — one shape throughout. `Episode.verdict` includes `refusal` from Session 2 so no later migration is needed. `Decimal` paise crosses every boundary including JSONL.
