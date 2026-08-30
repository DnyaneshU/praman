"""The corpus is a public claim about what we built. It has to be true."""

from praman.red.attacks import ATTACKS
from praman.red.corpus import load_corpus


def test_corpus_matches_registry():
    """Marked implemented <=> an attack class exists. Drift here is dishonesty."""
    claimed = {s.id for s in load_corpus() if s.implemented}
    built = set(ATTACKS)
    assert claimed == built, (
        f"claimed but not built: {sorted(claimed - built)}; "
        f"built but not in corpus: {sorted(built - claimed)}"
    )


def test_the_map_covers_every_surface():
    """Breadth is the claim; this is the claim asserted.

    An attack map that only covers the protocol layer is a map of the protocol
    layer. Each surface must carry at least two entries, so no category is
    represented by a single token vector.
    """
    from collections import Counter

    from praman.red.corpus import SURFACES

    counts = Counter(s.surface for s in load_corpus())
    assert set(counts) <= set(SURFACES), f"undeclared surface: {set(counts) - set(SURFACES)}"
    thin = {s: n for s, n in counts.items() if n < 2}
    assert not thin, f"surfaces with a single entry: {thin}"
    assert set(counts) == set(SURFACES), f"unmapped surfaces: {set(SURFACES) - set(counts)}"


def test_no_seed_points_at_a_rule_that_does_not_exist():
    """Including the unimplemented ones, which is where this went wrong.

    `test_every_attack_is_caught_by_its_documented_invariant` only reaches
    seeds that are built, so S-05 went on naming `inv-08` for a while after
    inv-08 was deleted for being declared and never run. Same failure, one
    layer up: a document asserting something no code backs.
    """
    from praman.blue.invariants import INVARIANTS

    known = {i.id for i in INVARIANTS} | {"tier-2", "tier-3", "none"}
    unknown = {s.id: s.caught_by for s in load_corpus() if s.caught_by not in known}
    assert not unknown, f"caught_by names nothing that exists: {unknown}"


def test_a_seed_that_names_no_rule_says_why():
    """`caught_by: none` is a claim about the limits of the approach.

    Left unexplained it reads as an omission, which is the opposite of the
    point — these are the two places the corpus admits a boundary.
    """
    for seed in load_corpus():
        if seed.caught_by == "none":
            assert seed.note, f"{seed.id} names no rule and does not say why"


def test_metadata_agrees_with_the_code():
    seeds = {s.id: s for s in load_corpus()}
    for attack_id, cls in ATTACKS.items():
        assert seeds[attack_id].attack_class == cls.attack_class
        assert seeds[attack_id].root_cause == cls.root_cause


def test_unimplemented_seeds_have_no_attack_behind_them():
    """The inverse of the check above: nothing built is quietly undocumented."""
    for seed in load_corpus():
        if not seed.implemented:
            assert seed.id not in ATTACKS


def test_the_coerced_principal_is_documented_as_the_honest_limit():
    """I-31 is deliberately unbuildable at the mandate layer, and says so.

    Every signature verifies and the money is gone anyway, because the fraud is
    upstream of the mandate. Presenting that boundary is the point.
    """
    coerced = next(s for s in load_corpus() if s.id == "I-31")
    assert coerced.implemented is False
    assert coerced.caught_by == "none"
    assert coerced.note
