import asyncio

import pytest

from app.scenarios.rehearsal import run_rehearsal


def test_rehearsal_runs_three_scripted_calls(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = asyncio.run(run_rehearsal())

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "[1/3] successful booking: PASS" in output
    assert "[2/3] unavailable slot with alternative: PASS" in output
    assert "[3/3] ambiguous time and hangup: PASS" in output
