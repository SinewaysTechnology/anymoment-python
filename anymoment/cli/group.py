"""Click command classes that carry the global agent flags."""

import click

from anymoment.cli.state import activate, global_options


class AnyMomentCommand(click.Command):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.params.extend(global_options())

    def invoke(self, ctx):
        activate(ctx)
        return super().invoke(ctx)


_ALIASES = {"a": "agenda"}


class AnyMomentGroup(click.Group):
    command_class = AnyMomentCommand
    group_class = type

    def get_command(self, ctx, cmd_name):
        if ctx.parent is None and cmd_name == "ls":
            calendars = super().get_command(ctx, "calendars")
            if calendars is not None:
                return calendars.get_command(ctx, "list")
        if ctx.parent is None and cmd_name == "rm":
            events = super().get_command(ctx, "events")
            if events is not None:
                return events.get_command(ctx, "delete")
        return super().get_command(ctx, _ALIASES.get(cmd_name, cmd_name))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.params.extend(global_options())

    def invoke(self, ctx):
        activate(ctx)
        return super().invoke(ctx)


class AgendaGroup(AnyMomentGroup):
    """`agenda <window>` is the same command as `agenda show <window>`."""

    def parse_args(self, ctx, args):
        if args and not str(args[0]).startswith("-") and args[0] not in self.commands:
            args = ["show", *args]
        return super().parse_args(ctx, args)
