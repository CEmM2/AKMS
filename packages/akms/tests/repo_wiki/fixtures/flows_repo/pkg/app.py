"""Entry points: a console script, a __main__ block, CLI commands."""

import argparse

from pkg.core import leaf, middle, wide


def main(argv=None):
    parser = build()
    return middle(len(argv or []))


def build():
    parser = argparse.ArgumentParser()
    parser.set_defaults(func=cmd_go)
    return parser


def cmd_go(args):
    return wide()


@app.command()
def hello():
    return leaf(1)


if __name__ == "__main__":
    main()
