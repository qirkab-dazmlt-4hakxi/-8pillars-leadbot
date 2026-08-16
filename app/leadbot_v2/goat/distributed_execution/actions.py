from __future__ import annotations

from collections.abc import Callable

from .models import (
    ActionContext,
    ActionResult,
)


ActionHandler = Callable[
    [ActionContext],
    ActionResult,
]


class UnknownActionError(RuntimeError):
    pass


class ActionRegistry:
    def __init__(
        self,
    ) -> None:
        self._handlers: dict[
            str,
            ActionHandler,
        ] = {}

    def register(
        self,
        action: str,
        handler: ActionHandler,
        *,
        replace: bool = False,
    ) -> None:
        if not action.strip():
            raise ValueError(
                "action cannot be blank"
            )

        if (
            action in self._handlers
            and not replace
        ):
            raise ValueError(
                f"action already registered: {action}"
            )

        self._handlers[action] = handler

    def contains(
        self,
        action: str,
    ) -> bool:
        return action in self._handlers

    def execute(
        self,
        context: ActionContext,
    ) -> ActionResult:
        try:
            handler = self._handlers[
                context.action
            ]

        except KeyError as exc:
            raise UnknownActionError(
                context.action
            ) from exc

        result = handler(context)

        if not isinstance(
            result,
            ActionResult,
        ):
            raise TypeError(
                "action handler must return ActionResult"
            )

        return result
