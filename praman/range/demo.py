"""`make demo` — an honest purchase, settled end to end.

The simplest thing that has to work. No model, no attack, no defense: a signed chain
that settles and a ledger that balances. Everything built later is a deviation
from this path, so it has to be right first.
"""

from __future__ import annotations

import argparse
import tempfile
from decimal import Decimal
from pathlib import Path

from praman.console import banner, field, rule
from praman.console import setup as console_setup
from praman.money import fmt
from praman.range.agent import ScriptedAgent
from praman.range.context import RangeContext
from praman.range.mandates import MandateChain
from praman.range.purchase import settle_chain
from praman.range.signing import Keyring

RULE = rule()


def _line(label: str, value: str) -> None:
    field(label, value, width=23)


def _show_chain(chain: MandateChain, keyring: Keyring, principal: str) -> None:
    intent, cart, payment = chain.intent, chain.cart, chain.payment

    print("\nINTENT   what the human authorised")
    _line("id", intent.mandate_id)
    _line("asked for", intent.description)
    _line("ceiling", fmt(intent.max_amount))
    _line("signature", _verdict(keyring.verify(intent, principal)))

    print("\nCART     what the agent chose")
    _line("id", cart.mandate_id)
    _line("merchant", cart.merchant_id)
    _line("items", ", ".join(f"{i.name} x{i.qty}" for i in cart.items))
    _line("total", fmt(cart.total))
    _line("shown to user", cart.display_summary)
    _line("signature", _verdict(keyring.verify(cart, cart.merchant_id)))

    print("\nPAYMENT  where the money goes")
    _line("id", payment.mandate_id)
    _line("beneficiary", payment.beneficiary)
    _line("amount", fmt(payment.amount))
    _line("signature", _verdict(keyring.verify(payment, principal)))


def _verdict(ok: bool) -> str:
    return "valid" if ok else "INVALID"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Praman range — honest purchase demo")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--profile", default="autopay")
    parser.add_argument("--task", default="task-shoes")
    args = parser.parse_args(argv)
    console_setup()

    with tempfile.TemporaryDirectory() as tmp:
        ctx = RangeContext.build(Path(tmp) / "range.db", profile=args.profile, seed=args.seed)
        try:
            return _run(ctx, args)
        finally:
            ctx.ledger.close()


def _run(ctx: RangeContext, args) -> int:
    banner(
        "RANGE",
        f"profile: {ctx.profile.name}",
        f"seed: {ctx.seed}",
        note=ctx.profile.description,
    )

    task = ctx.catalog.task(args.task)
    # Through the agent, not by assembling the chain here. This demo used to
    # reimplement `shop()` and had drifted out of step with it — it passed the
    # task where an intent is required, so the honest path, the first command
    # in the README, raised AttributeError. Whatever the campaigns run is what
    # this shows, because it is the same call.
    chain = ScriptedAgent().shop(task, ctx)
    item = chain.cart.items[0]

    print(f'\nTASK     "{task.description}"')
    _line("agent picked", f"{item.name} ({item.sku}) at {fmt(item.price)}")

    _show_chain(chain, ctx.keyring, ctx.principal)

    before = ctx.ledger.snapshot()
    total_before = sum(before.values(), Decimal(0))

    print(f"\n{RULE}")
    result = settle_chain(chain, ctx)
    if result.settled:
        print(f"SETTLED  {fmt(result.amount)} to {result.beneficiary}")
    else:
        print(f"REFUSED  {result.reason}")
    print(RULE)

    after = ctx.ledger.snapshot()
    total_after = sum(after.values(), Decimal(0))

    print("\nLEDGER")
    for account in sorted(after):
        delta = after[account] - before.get(account, Decimal(0))
        if delta:
            _line(
                account,
                f"{fmt(after[account])}   ({fmt(abs(delta))} {'in' if delta > 0 else 'out'})",
            )
    _line("total in system", f"{fmt(total_after)}")

    conserved = total_before == total_after
    print(f"\n  money conserved:    {'yes' if conserved else 'NO — LEDGER BUG'}")
    print(f"  harm to attacker:   {fmt(ctx.harm())}")
    print()

    return 0 if (result.settled and conserved) else 1


if __name__ == "__main__":
    raise SystemExit(main())
