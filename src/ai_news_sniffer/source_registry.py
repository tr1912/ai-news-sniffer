from ai_news_sniffer.models import ProfileName, SourceConfig, SourcesConfig


def resolve_sources(
    config: SourcesConfig,
    profile_override: ProfileName | None = None,
    include_sources: set[str] | None = None,
    exclude_sources: set[str] | None = None,
    auto_paused: set[str] | None = None,
) -> list[SourceConfig]:
    profile = profile_override or config.active_profile
    included = include_sources or set()
    excluded = exclude_sources or set()
    paused = auto_paused or set()
    selected: list[SourceConfig] = []

    for source in config.sources:
        if not source.enabled:
            continue
        if not config.source_groups[source.group].enabled:
            continue
        if profile not in source.profiles:
            continue
        if included and source.id not in included:
            continue
        if source.id in excluded or source.id in paused:
            continue
        selected.append(source)
    return selected
