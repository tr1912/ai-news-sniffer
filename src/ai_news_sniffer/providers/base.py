from typing import Protocol


class StructuredProvider(Protocol):
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict: ...


class ProviderChain:
    def __init__(self, providers: list[StructuredProvider]) -> None:
        if not providers:
            raise ValueError("provider chain cannot be empty")
        self.providers = providers

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        errors: list[str] = []
        for provider in self.providers:
            try:
                return provider.generate_json(system_prompt, user_prompt)
            except Exception as error:  # noqa: BLE001
                errors.append(f"{type(error).__name__}: {error}")
        raise RuntimeError("all providers failed: " + " | ".join(errors))
