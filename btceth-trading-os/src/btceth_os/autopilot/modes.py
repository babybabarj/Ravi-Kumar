from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OperatingMode(StrEnum):
    OFF = "OFF"
    SHADOW_AUTO = "SHADOW_AUTO"
    PAPER_AUTO = "PAPER_AUTO"
    TESTNET_AUTO = "TESTNET_AUTO"
    LIVE_APPROVAL = "LIVE_APPROVAL"


DEFAULT_OPERATING_MODE = OperatingMode.PAPER_AUTO


@dataclass
class SystemControlState:
    mode: OperatingMode = DEFAULT_OPERATING_MODE
    paused: bool = False
    halted: bool = False
    halt_reason: str | None = None
    pause_reason: str | None = None

    def can_evaluate_signals(self) -> bool:
        return self.mode != OperatingMode.OFF and not self.halted

    def can_enter_new_trades(self) -> bool:
        return (
            self.mode in (OperatingMode.SHADOW_AUTO, OperatingMode.PAPER_AUTO, OperatingMode.TESTNET_AUTO, OperatingMode.LIVE_APPROVAL)
            and not self.paused
            and not self.halted
        )

    def pause(self, reason: str = "MANUAL_PAUSE") -> None:
        self.paused = True
        self.pause_reason = reason

    def resume(self) -> None:
        self.paused = False
        self.pause_reason = None

    def emergency_halt(self, reason: str) -> None:
        self.halted = True
        self.halt_reason = reason

    def clear_halt(self) -> None:
        self.halted = False
        self.halt_reason = None

    def set_mode(self, mode: OperatingMode | str) -> None:
        parsed = OperatingMode(mode)
        self.mode = parsed
