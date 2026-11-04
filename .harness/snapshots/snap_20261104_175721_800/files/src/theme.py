"""Auto-generated Design Tokens (Tier S) — AI Harness Architect."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Spacing:
    SPACE_0: int = 0
    SPACE_1: int = 4
    SPACE_2: int = 8
    SPACE_3: int = 12
    SPACE_4: int = 16
    SPACE_5: int = 24
    SPACE_6: int = 32
    SPACE_7: int = 48
    SPACE_8: int = 64

@dataclass(frozen=True)
class Radius:
    RADIUS_NONE: int = 0
    RADIUS_SM: int = 4
    RADIUS_MD: int = 8
    RADIUS_PILL: int = 9999

@dataclass(frozen=True)
class ThemeColors:
    SURFACE: str = '#0d1117'
    SURFACE_CARD: str = '#161b22'
    SURFACE_ELEVATED: str = '#21262d'
    BORDER: str = '#30363d'
    BORDER_SUBTLE: str = '#21262d'
    TEXT_PRIMARY: str = '#ffffff'
    TEXT_SECONDARY: str = '#c9d1d9'
    TEXT_MUTED: str = '#8b949e'
    ACTION_PRIMARY: str = '#238636'
    ACTION_PRIMARY_HOVER: str = '#2ea043'
    ACTION_SECONDARY_BG: str = '#21262d'
    ACTION_SECONDARY_TEXT: str = '#c9d1d9'
    ACTION_DANGER: str = '#da3633'
    ACTION_DANGER_HOVER: str = '#f85149'
    STATUS_SUCCESS: str = '#3fb950'
    STATUS_WARNING: str = '#d29922'
    STATUS_ERROR: str = '#f85149'
    STATUS_INFO: str = '#58a6ff'

# High contrast dark theme preset
DARK_THEME = ThemeColors()
SPACING = Spacing()
RADIUS = Radius()