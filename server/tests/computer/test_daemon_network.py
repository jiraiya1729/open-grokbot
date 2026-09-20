from __future__ import annotations

import subprocess

from computer_daemon import main


def test_sandbox_gets_a_separate_egress_network(monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_docker(*args: str, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(
            args,
            1 if args[:2] == ("network", "inspect") else 0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(main, "docker", fake_docker)
    main.attach_egress_network("grokbot-workspace")

    assert calls == [
        ("network", "inspect", main.COMPUTER_EGRESS_NETWORK),
        ("network", "create", "--driver", "bridge", main.COMPUTER_EGRESS_NETWORK),
        ("network", "connect", main.COMPUTER_EGRESS_NETWORK, "grokbot-workspace"),
    ]


def test_viewer_uses_private_control_network_address(monkeypatch) -> None:
    captured: list[tuple[str, ...]] = []

    def fake_docker(*args: str, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="172.30.0.8\n", stderr="")

    monkeypatch.setattr(main, "docker", fake_docker)

    assert main.container_ip("grokbot-workspace") == "172.30.0.8"
    assert main.COMPUTER_NETWORK in captured[0][2]
    assert "range .NetworkSettings.Networks" not in captured[0][2]
