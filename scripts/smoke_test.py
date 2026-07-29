"""Pre-demo smoke test — run against your public (ngrok) URL before the showcase.

    uv run python -m scripts.smoke_test https://<your-id>.ngrok-free.app

Checks the critical path an audience will see: health, catalogue, login, and the
orders page. Exits non-zero if any check fails, so you find out now, not mid-demo.
Network CLI — excluded from unit coverage.
"""

from __future__ import annotations

import sys

import httpx


def run(base_url: str) -> int:  # pragma: no cover - network CLI
    base = base_url.rstrip("/")
    checks: list[tuple[str, bool]] = []

    with httpx.Client(base_url=base, follow_redirects=True, timeout=15.0) as client:
        try:
            checks.append(("health", client.get("/health").json().get("status") == "ok"))
        except Exception as exc:  # noqa: BLE001
            checks.append((f"health ({exc})", False))

        home = client.get("/")
        checks.append(("home loads", home.status_code == 200))
        checks.append(("catalogue has products", "card" in home.text))

        client.post("/login", data={"user_id": "u001", "password": "demo1234"})
        orders = client.get("/orders")
        checks.append(("logged in + orders page", orders.status_code == 200))
        checks.append(("assistant page", client.get("/chat").status_code == 200))

    ok = True
    for name, passed in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    print("\nAll good — you're ready to demo." if ok else "\nFix the FAILs above first.")
    return 0 if ok else 1


def main() -> None:  # pragma: no cover - CLI
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m scripts.smoke_test <base-url>")
    raise SystemExit(run(sys.argv[1]))


if __name__ == "__main__":  # pragma: no cover
    main()
