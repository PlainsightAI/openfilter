import sys

from .common import SCRIPT
from .cmd_emit_schema import cmd_emit_schema
from .cmd_info import cmd_info
from .cmd_run import cmd_run


def main():
    args = sys.argv[2:]
    cmd  = sys.argv[1] if len(sys.argv) > 1 else ''

    cmd_attr = f'cmd_{cmd.replace("-", "_")}'
    if cmd_func := getattr(sys.modules[__name__], cmd_attr, None):
        cmd_func(args)

    else:
        print(f"""
usage: {SCRIPT} COMMAND ...

Commands:
  run           Directly run one or more filter(s)
  logs          Show filter(s) logs
  info          Get help on a specific filter
  emit-schema   Emit a filter's JSON Schema (declarative config, FC-1)

Run '{SCRIPT} COMMAND --help' for more information on a command.
""".strip())


if __name__ == '__main__':
    main()
