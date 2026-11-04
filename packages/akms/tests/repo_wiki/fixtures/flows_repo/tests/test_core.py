from pkg.core import leaf, middle, only_tested


def test_leaf():
    assert leaf(2) == 2


def test_only():
    assert only_tested() == 0


class TestMiddle:
    def test_middle(self):
        assert middle(1) == 2

    def helper(self):
        return 1
