"""Legacy Python mirror identity and nested-symbol fixture."""


class LegacyVector:
    """A vector whose method must retain its parent relationship."""

    def scale(self, factor: float) -> float:
        """Scale one unit vector component."""
        return factor
