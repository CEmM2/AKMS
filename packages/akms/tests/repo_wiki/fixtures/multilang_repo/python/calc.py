"""Tiny Python sample for the multilang fixture."""


class Foo:
    """A small class with one method."""

    def run(self, x):
        return x + 1


def helper(x):
    """Free function that calls Foo.run — resolves CONFIDENT to Foo.run."""
    return Foo().run(x)
