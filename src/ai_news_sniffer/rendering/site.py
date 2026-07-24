from pathlib import Path
from shutil import copytree

from jinja2 import FileSystemLoader, StrictUndefined, select_autoescape
from jinja2.sandbox import SandboxedEnvironment

from ai_news_sniffer.models import DailyReport


class SiteRenderer:
    def __init__(self, templates_root: Path) -> None:
        self.templates_root = templates_root

    def _environment(self, template_name: str) -> SandboxedEnvironment:
        root = self.templates_root.resolve()
        directory = (root / template_name).resolve()
        if root not in directory.parents:
            raise ValueError("template name must stay inside templates root")
        if not directory.is_dir():
            raise ValueError(f"template does not exist: {template_name}")
        environment = SandboxedEnvironment(
            loader=FileSystemLoader(directory),
            autoescape=select_autoescape(["html", "xml"]),
            undefined=StrictUndefined,
        )
        environment.filters["date_path"] = lambda value: value.strftime("%Y/%m/%d")
        return environment

    def render(
        self,
        reports: list[DailyReport],
        template_name: str,
        output_dir: Path,
    ) -> list[Path]:
        if not reports:
            raise ValueError("cannot render a site without reports")
        environment = self._environment(template_name)
        output_dir.mkdir(parents=True, exist_ok=True)
        created: list[Path] = []
        ordered = sorted(reports, key=lambda item: item.date, reverse=True)
        report_template = environment.get_template("report.html.j2")
        for index, report in enumerate(ordered):
            destination = (
                output_dir
                / f"{report.date:%Y}"
                / f"{report.date:%m}"
                / f"{report.date:%d}"
                / "index.html"
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                report_template.render(
                    report=report,
                    previous=ordered[index + 1] if index + 1 < len(ordered) else None,
                    next=ordered[index - 1] if index > 0 else None,
                ),
                encoding="utf-8",
            )
            created.append(destination)
        latest = output_dir / "index.html"
        latest.write_text(
            environment.get_template("index.html.j2").render(report=ordered[0]),
            encoding="utf-8",
        )
        created.append(latest)
        archive = output_dir / "archive" / "index.html"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_text(
            environment.get_template("archive.html.j2").render(reports=ordered),
            encoding="utf-8",
        )
        created.append(archive)
        static_source = self.templates_root / template_name / "static"
        if static_source.exists():
            copytree(static_source, output_dir / "static", dirs_exist_ok=True)
        return created

    def render_notification(
        self,
        report: DailyReport,
        template_name: str,
    ) -> str:
        return self._environment(template_name).get_template(
            "notification.md.j2"
        ).render(report=report, top_items=report.events[:3])
