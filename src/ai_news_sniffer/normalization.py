import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ai_news_sniffer.models import Article, RawArticle

TRACKING_PREFIXES = ("utm_",)
TRACKING_KEYS = {"fbclid", "gclid", "ref", "source"}


def canonicalize_url(url: str) -> str:
    split = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(split.query, keep_blank_values=True)
        if key.casefold() not in TRACKING_KEYS
        and not key.casefold().startswith(TRACKING_PREFIXES)
    ]
    return urlunsplit(
        (
            split.scheme.casefold(),
            split.netloc.casefold(),
            split.path.rstrip("/") or "/",
            urlencode(query),
            "",
        )
    )


def normalize_title(title: str) -> str:
    return " ".join(re.findall(r"[\w\u4e00-\u9fff]+", title.casefold()))


def normalize_article(raw: RawArticle) -> Article:
    canonical_url = canonicalize_url(str(raw.url))
    normalized_title = normalize_title(raw.title)
    fingerprint = hashlib.sha256(
        f"{canonical_url}|{normalized_title}".encode()
    ).hexdigest()
    raw_values = {field: getattr(raw, field) for field in RawArticle.model_fields}
    return Article(
        **raw_values,
        id=fingerprint[:16],
        canonical_url=canonical_url,
        normalized_title=normalized_title,
        fingerprint=fingerprint,
    )
