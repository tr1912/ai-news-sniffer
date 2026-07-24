from datetime import datetime
from urllib.parse import urlencode

from ai_news_sniffer.models import RawArticle, SourceConfig
from ai_news_sniffer.sources.rss import RssAdapter


class ArxivAdapter(RssAdapter):
    def fetch(
        self,
        source: SourceConfig,
        since: datetime,
        until: datetime,
    ) -> list[RawArticle]:
        query = str(source.options["query"])
        max_results = int(source.options.get("max_results", 30))
        url = f"{source.url}?{urlencode({
            'search_query': query,
            'sortBy': 'submittedDate',
            'sortOrder': 'descending',
            'max_results': max_results,
        })}"
        arxiv_source = source.model_copy(update={"url": url})
        return super().fetch(arxiv_source, since, until)
