"""Domain errors: things that go wrong in *business terms*.

These know nothing about HTTP. The service raises them; the router (1.5)
translates each one into a status code. That keeps the service reusable
- later the LLM agent will call the same service with no HTTP involved.
"""


class DomainError(Exception):
    """Base class, so a caller can catch every business error at once."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    """The thing you referred to does not exist  -> HTTP 404."""


class ConflictError(DomainError):
    """It exists, but its current state forbids this action -> HTTP 409."""
