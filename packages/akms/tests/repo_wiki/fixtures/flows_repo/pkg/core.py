"""Call shapes: a chain, a wide fan-out, a cycle and a name-only link."""


def leaf(value):
    return value


def middle(value):
    return leaf(value) + 1


def chain_a():
    return chain_b()


def chain_b():
    return chain_c()


def chain_c():
    return chain_d()


def chain_d():
    return leaf(4)


def wide():
    one()
    two()
    three()
    four()
    return five()


def one():
    return middle(1)


def two():
    return 2


def three():
    return 3


def four():
    return 4


def five():
    return 5


def spin():
    return loop_a()


def loop_a():
    return loop_b()


def loop_b():
    return loop_a()


def only_tested():
    return leaf(0)


def _private_root():
    return leaf(9)
