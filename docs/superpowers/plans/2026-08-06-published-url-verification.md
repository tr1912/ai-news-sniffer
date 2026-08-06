# 发布 URL 校验增强实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将发布 URL 校验扩展为最多 8 分钟的斐波那契退避流程，记录每次请求的状态码与最终 URL，并对暂时性故障和永久性配置错误采取不同处理。

**架构：** 保留 `verify_report_url()` 作为 CLI 与发布状态之间的单一校验入口，在同一模块内增加 URL 预检、状态分类和统一日志辅助函数。重试循环使用可注入的单调时钟与 sleep 函数计算真实墙钟预算，并为最后一次 HTTP 请求保留最多 30 秒；测试通过假时钟验证退避与预算，不产生真实等待。

**技术栈：** Python 3.12、httpx、pytest、respx、ruff

---

## 文件结构

- 修改：`src/ai_news_sniffer/cli.py`——负责 URL 预检、响应分类、斐波那契退避、8 分钟预算和 Actions 诊断日志。
- 修改：`tests/test_cli.py`——使用 respx 与假时钟覆盖成功、重定向、暂时性错误、永久性错误及预算耗尽。
- 已有规格：`docs/superpowers/specs/2026-08-06-published-url-verification-design.md`——本计划的需求来源，不改变运行时代码。
- 创建：`docs/superpowers/plans/2026-08-06-published-url-verification.md`——记录 TDD 实施和验证步骤。

## 行为约定

- 校验总预算常量为 `480.0` 秒，单次请求超时上限为 `30.0` 秒。
- 首次请求立即执行；重试等待为 `1, 1, 2, 3, 5, 8, ...` 秒。
- 当完整的下一个斐波那契间隔会侵占最后 30 秒请求窗口时，将该等待截断；不会为了凑满 8 分钟而在截止时间后再发请求。
- 暂时性：404、408、425、429、500–599、网络传输/超时、2xx 但缺少页面标记。
- 永久性：非法或非 HTTP(S) URL、其他 HTTP 状态、无效/不支持请求 URL、重定向循环。
- 每次真实请求输出一条 `[verify-url]` stderr 日志；URL 预检失败输出 `attempt=0` 的永久性日志。

### 任务 1：锁定成功路径和永久性错误行为

**文件：**
- 修改：`tests/test_cli.py:1-30`
- 修改：`src/ai_news_sniffer/cli.py:1-75`

- [x] **步骤 1：先为成功日志、非法 URL 和永久性 403 编写失败测试**

在 `tests/test_cli.py` 中增加 `pytest` 导入，将现有成功测试替换为重定向日志测试，并添加永久性错误测试：

```python
import pytest


def test_verify_report_url_logs_status_and_final_url(
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_url = "https://example.com/report/"
    final_url = "https://cdn.example.com/report/"
    with respx.mock:
        respx.get(request_url).mock(
            return_value=httpx.Response(302, headers={"Location": final_url})
        )
        respx.get(final_url).mock(
            return_value=httpx.Response(200, text="<h1>AI 每日情报</h1>")
        )
        with httpx.Client() as client:
            verify_report_url(request_url, client)

    log = capsys.readouterr().err
    assert "attempt=1" in log
    assert "classification=success" in log
    assert "status=200" in log
    assert f"request_url={request_url}" in log
    assert f"final_url={final_url}" in log


@pytest.mark.parametrize("url", ["ftp://example.com/report/", "/relative/report/"])
def test_verify_report_url_rejects_invalid_configuration(
    url: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ai_news_sniffer.cli.time.sleep", lambda _: None)
    with httpx.Client() as client:
        with pytest.raises(RuntimeError, match="invalid published report URL"):
            verify_report_url(url, client)

    log = capsys.readouterr().err
    assert "attempt=0" in log
    assert "classification=permanent" in log
    assert f"request_url={url}" in log
    assert "final_url=unavailable" in log


def test_verify_report_url_fails_fast_for_permanent_http_status(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_url = "https://example.com/report/"
    monkeypatch.setattr("ai_news_sniffer.cli.time.sleep", lambda _: None)
    with respx.mock:
        route = respx.get(request_url).mock(return_value=httpx.Response(403))
        with httpx.Client() as client:
            with pytest.raises(RuntimeError, match="permanent configuration error"):
                verify_report_url(request_url, client)

    assert route.call_count == 1
    log = capsys.readouterr().err
    assert "classification=permanent" in log
    assert "status=403" in log
    assert f"request_url={request_url}" in log
    assert f"final_url={request_url}" in log
```

- [x] **步骤 2：运行三个测试并确认红灯原因正确**

运行：

```bash
python -m pytest \
  tests/test_cli.py::test_verify_report_url_logs_status_and_final_url \
  tests/test_cli.py::test_verify_report_url_rejects_invalid_configuration \
  tests/test_cli.py::test_verify_report_url_fails_fast_for_permanent_http_status \
  -q
```

预期：FAIL。成功路径缺少 stderr 日志；非法 URL 没有明确的配置错误；403 被旧循环重试而不是立即失败。

- [x] **步骤 3：增加 URL 预检、统一日志和单次响应分类的最少实现**

在 `src/ai_news_sniffer/cli.py` 中保留现有 `time` 导入，并在 `_extract_path()` 后、`verify_report_url()` 前增加：

```python
_REPORT_MARKER = "AI 每日情报"
_VERIFY_BUDGET_SECONDS = 480.0
_REQUEST_TIMEOUT_SECONDS = 30.0
_TRANSIENT_STATUS_CODES = {404, 408, 425, 429}


def _validated_report_url(url: str) -> httpx.URL:
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, ValueError) as error:
        raise ValueError(str(error)) from error
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise ValueError("URL must use http or https and include a host")
    return parsed


def _is_transient_status(status_code: int) -> bool:
    return status_code in _TRANSIENT_STATUS_CODES or 500 <= status_code <= 599


def _log_url_verification(
    *,
    attempt: int,
    classification: str,
    request_url: str,
    final_url: str | None,
    status_code: int | None,
    error: str | None = None,
    next_delay_seconds: float | None = None,
    remaining_seconds: float | None = None,
) -> None:
    fields = [
        "[verify-url]",
        f"attempt={attempt}",
        f"classification={classification}",
        f"status={status_code if status_code is not None else 'unavailable'}",
        f"request_url={request_url}",
        f"final_url={final_url or 'unavailable'}",
    ]
    if error is not None:
        fields.append(f"error={error}")
    if next_delay_seconds is not None:
        fields.append(f"next_delay_seconds={next_delay_seconds:.1f}")
    if remaining_seconds is not None:
        fields.append(f"remaining_seconds={remaining_seconds:.1f}")
    print(" ".join(fields), file=sys.stderr)
```

将旧的 `verify_report_url()` 暂时替换为以下单次请求实现，先让本任务的测试变绿：

```python
def verify_report_url(url: str, client: httpx.Client) -> None:
    try:
        request_url = str(_validated_report_url(url))
    except ValueError as error:
        _log_url_verification(
            attempt=0,
            classification="permanent",
            request_url=url,
            final_url=None,
            status_code=None,
            error="invalid-url",
        )
        raise RuntimeError(f"invalid published report URL: {error}") from error

    response = client.get(
        request_url,
        follow_redirects=True,
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )
    status_code = response.status_code
    final_url = str(response.url)
    if 200 <= status_code <= 299 and _REPORT_MARKER in response.text:
        _log_url_verification(
            attempt=1,
            classification="success",
            request_url=request_url,
            final_url=final_url,
            status_code=status_code,
        )
        return

    if _is_transient_status(status_code) or 200 <= status_code <= 299:
        _log_url_verification(
            attempt=1,
            classification="transient",
            request_url=request_url,
            final_url=final_url,
            status_code=status_code,
            error="missing-marker" if 200 <= status_code <= 299 else f"http-{status_code}",
        )
        raise RuntimeError(
            "published report was not reachable: "
            f"status={status_code} final_url={final_url}"
        )

    _log_url_verification(
        attempt=1,
        classification="permanent",
        request_url=request_url,
        final_url=final_url,
        status_code=status_code,
        error=f"http-{status_code}",
    )
    raise RuntimeError(
        "published report URL has a permanent configuration error: "
        f"status={status_code} request_url={request_url} final_url={final_url}"
    )
```

- [x] **步骤 4：运行任务 1 测试并确认变绿**

运行：

```bash
python -m pytest \
  tests/test_cli.py::test_verify_report_url_logs_status_and_final_url \
  tests/test_cli.py::test_verify_report_url_rejects_invalid_configuration \
  tests/test_cli.py::test_verify_report_url_fails_fast_for_permanent_http_status \
  -q
```

预期：4 passed（参数化非法 URL 产生两个测试用例），无真实 sleep。

- [x] **步骤 5：提交成功路径和永久错误分类**

```bash
git add \
  docs/superpowers/specs/2026-08-06-published-url-verification-design.md \
  docs/superpowers/plans/2026-08-06-published-url-verification.md \
  src/ai_news_sniffer/cli.py \
  tests/test_cli.py
git commit -m "feat: classify published URL verification errors"
```

### 任务 2：实现斐波那契退避和 8 分钟墙钟预算

**文件：**
- 修改：`tests/test_cli.py:1-110`
- 修改：`src/ai_news_sniffer/cli.py:1-150`

- [x] **步骤 1：增加假时钟测试工具**

在 `tests/test_cli.py` 顶部增加以下导入：

```python
from dataclasses import dataclass, field
```

在 URL 校验测试之前增加：

```python
@dataclass
class FakeClock:
    now: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
```

- [x] **步骤 2：先为 404、持续 5xx、旧页面和网络错误编写失败测试**

在 `tests/test_cli.py` 中增加：

```python
def test_verify_report_url_retries_404_with_fibonacci_delays() -> None:
    request_url = "https://example.com/report/"
    clock = FakeClock()
    with respx.mock:
        route = respx.get(request_url).mock(
            side_effect=[
                httpx.Response(404),
                httpx.Response(404),
                httpx.Response(200, text="<h1>AI 每日情报</h1>"),
            ]
        )
        with httpx.Client() as client:
            verify_report_url(
                request_url,
                client,
                monotonic=clock.monotonic,
                sleep=clock.sleep,
            )

    assert route.call_count == 3
    assert clock.sleeps == [1.0, 1.0]


@pytest.mark.parametrize("status_code", [408, 425, 429, 500, 599])
def test_verify_report_url_retries_other_transient_http_statuses(
    status_code: int,
) -> None:
    request_url = "https://example.com/report/"
    clock = FakeClock()
    with respx.mock:
        route = respx.get(request_url).mock(
            side_effect=[
                httpx.Response(status_code),
                httpx.Response(200, text="<h1>AI 每日情报</h1>"),
            ]
        )
        with httpx.Client() as client:
            verify_report_url(
                request_url,
                client,
                monotonic=clock.monotonic,
                sleep=clock.sleep,
            )

    assert route.call_count == 2
    assert clock.sleeps == [1.0]


def test_verify_report_url_caps_retries_at_eight_minute_budget(
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_url = "https://example.com/report/"
    clock = FakeClock()
    with respx.mock:
        route = respx.get(request_url).mock(return_value=httpx.Response(503))
        with httpx.Client() as client:
            with pytest.raises(
                RuntimeError,
                match=r"within 480s: status=503 .*final_url=https://example.com/report/",
            ):
                verify_report_url(
                    request_url,
                    client,
                    monotonic=clock.monotonic,
                    sleep=clock.sleep,
                )

    assert clock.sleeps == [
        1.0,
        1.0,
        2.0,
        3.0,
        5.0,
        8.0,
        13.0,
        21.0,
        34.0,
        55.0,
        89.0,
        144.0,
        74.0,
    ]
    assert sum(clock.sleeps) == 450.0
    assert route.call_count == len(clock.sleeps) + 1
    log = capsys.readouterr().err
    assert "classification=transient" in log
    assert "status=503" in log
    assert "next_delay_seconds=74.0" in log
    assert "remaining_seconds=104.0" in log


def test_verify_report_url_retries_page_without_expected_marker() -> None:
    request_url = "https://example.com/report/"
    clock = FakeClock()
    with respx.mock:
        respx.get(request_url).mock(
            side_effect=[
                httpx.Response(200, text="<h1>Old page</h1>"),
                httpx.Response(200, text="<h1>AI 每日情报</h1>"),
            ]
        )
        with httpx.Client() as client:
            verify_report_url(
                request_url,
                client,
                monotonic=clock.monotonic,
                sleep=clock.sleep,
            )

    assert clock.sleeps == [1.0]


def test_verify_report_url_retries_transport_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_url = "https://example.com/report/"
    clock = FakeClock()
    with respx.mock:
        respx.get(request_url).mock(
            side_effect=[
                httpx.ConnectError("temporary DNS failure"),
                httpx.Response(200, text="<h1>AI 每日情报</h1>"),
            ]
        )
        with httpx.Client() as client:
            verify_report_url(
                request_url,
                client,
                monotonic=clock.monotonic,
                sleep=clock.sleep,
            )

    assert clock.sleeps == [1.0]
    log = capsys.readouterr().err
    assert "classification=transient" in log
    assert "status=unavailable" in log
    assert "final_url=unavailable" in log
    assert "error=ConnectError" in log
```

同时修改任务 1 的永久性 403 测试，在请求前创建 `clock = FakeClock()`，调用时传入 `monotonic=clock.monotonic, sleep=clock.sleep`，并增加：

```python
assert clock.sleeps == []
```

- [x] **步骤 3：运行新增测试并确认红灯原因正确**

运行：

```bash
python -m pytest \
  tests/test_cli.py::test_verify_report_url_retries_404_with_fibonacci_delays \
  tests/test_cli.py::test_verify_report_url_retries_other_transient_http_statuses \
  tests/test_cli.py::test_verify_report_url_caps_retries_at_eight_minute_budget \
  tests/test_cli.py::test_verify_report_url_retries_page_without_expected_marker \
  tests/test_cli.py::test_verify_report_url_retries_transport_error \
  tests/test_cli.py::test_verify_report_url_fails_fast_for_permanent_http_status \
  -q
```

预期：FAIL，`verify_report_url()` 尚不接受时钟/sleep 注入，也没有重试循环。

- [x] **步骤 4：为生产代码增加 Callable 类型**

在 `src/ai_news_sniffer/cli.py` 的导入区增加：

```python
from collections.abc import Callable
```

- [x] **步骤 5：用预算受控的重试循环替换单次请求实现**

保留任务 1 新增的常量与辅助函数，将 `verify_report_url()` 完整替换为：

```python
def verify_report_url(
    url: str,
    client: httpx.Client,
    *,
    max_wait_seconds: float = _VERIFY_BUDGET_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    if max_wait_seconds <= 0:
        raise ValueError("max_wait_seconds must be positive")
    try:
        request_url = str(_validated_report_url(url))
    except ValueError as error:
        _log_url_verification(
            attempt=0,
            classification="permanent",
            request_url=url,
            final_url=None,
            status_code=None,
            error="invalid-url",
        )
        raise RuntimeError(f"invalid published report URL: {error}") from error

    deadline = monotonic() + max_wait_seconds
    previous_delay = 0.0
    next_delay = 1.0
    attempt = 0
    last_detail = "no response"

    while True:
        attempt += 1
        remaining_before_request = max(0.0, deadline - monotonic())
        request_timeout = min(
            _REQUEST_TIMEOUT_SECONDS,
            max(0.001, remaining_before_request),
        )
        try:
            response = client.get(
                request_url,
                follow_redirects=True,
                timeout=request_timeout,
            )
        except (httpx.InvalidURL, httpx.UnsupportedProtocol, httpx.TooManyRedirects) as error:
            error_name = type(error).__name__
            _log_url_verification(
                attempt=attempt,
                classification="permanent",
                request_url=request_url,
                final_url=None,
                status_code=None,
                error=error_name,
            )
            raise RuntimeError(
                "published report URL has a permanent configuration error: "
                f"error={error_name} request_url={request_url}"
            ) from error
        except httpx.TransportError as error:
            error_name = type(error).__name__
            final_url = None
            status_code = None
            transient_error = error_name
            last_detail = f"error={error_name} request_url={request_url}"
        else:
            final_url = str(response.url)
            status_code = response.status_code
            if 200 <= status_code <= 299 and _REPORT_MARKER in response.text:
                _log_url_verification(
                    attempt=attempt,
                    classification="success",
                    request_url=request_url,
                    final_url=final_url,
                    status_code=status_code,
                )
                return
            if _is_transient_status(status_code) or 200 <= status_code <= 299:
                transient_error = (
                    "missing-marker"
                    if 200 <= status_code <= 299
                    else f"http-{status_code}"
                )
                last_detail = f"status={status_code} final_url={final_url}"
            else:
                _log_url_verification(
                    attempt=attempt,
                    classification="permanent",
                    request_url=request_url,
                    final_url=final_url,
                    status_code=status_code,
                    error=f"http-{status_code}",
                )
                raise RuntimeError(
                    "published report URL has a permanent configuration error: "
                    f"status={status_code} request_url={request_url} "
                    f"final_url={final_url}"
                )

        remaining_seconds = max(0.0, deadline - monotonic())
        retry_wait_budget = max(
            0.0,
            remaining_seconds - min(_REQUEST_TIMEOUT_SECONDS, remaining_seconds),
        )
        delay_seconds = min(next_delay, retry_wait_budget)
        _log_url_verification(
            attempt=attempt,
            classification="transient",
            request_url=request_url,
            final_url=final_url,
            status_code=status_code,
            error=transient_error,
            next_delay_seconds=delay_seconds,
            remaining_seconds=remaining_seconds,
        )
        if delay_seconds <= 0:
            break

        sleep(delay_seconds)
        previous_delay, next_delay = next_delay, previous_delay + next_delay

    raise RuntimeError(
        f"published report was not reachable within {max_wait_seconds:g}s: "
        f"{last_detail}"
    )
```

实现注意：`retry_wait_budget` 始终为下一次请求保留最多 30 秒；默认假时钟下的最后一次等待因此从 233 秒截断为 74 秒，累计 sleep 450 秒，最后一次请求最多使用剩余 30 秒。

- [x] **步骤 6：运行 URL 校验测试并确认变绿**

运行：

```bash
python -m pytest tests/test_cli.py -q
```

预期：所有 `tests/test_cli.py` 测试通过；假时钟测试立即完成，没有真实等待。

- [ ] **步骤 7：提交重试实现和回归测试**

```bash
git add src/ai_news_sniffer/cli.py tests/test_cli.py
git commit -m "fix: retry transient published URL failures"
```

### 任务 3：验证 CLI、代码质量和完整回归

**文件：**
- 验证：`src/ai_news_sniffer/cli.py`
- 验证：`tests/test_cli.py`
- 验证：整个测试套件

- [ ] **步骤 1：运行 Ruff 检查**

运行：

```bash
python -m ruff check src tests
python -m ruff format --check src tests
```

预期：两个命令均以 exit code 0 结束；若仅有格式问题，运行 `python -m ruff format src tests` 后重新执行两个检查命令。

- [ ] **步骤 2：运行 URL 校验定向测试并显示详细用例名**

运行：

```bash
python -m pytest tests/test_cli.py -v
```

预期：全部通过，输出包含成功日志、非法 URL、永久性 403、404 斐波那契重试、8 分钟预算、缺失标记和网络错误用例。

- [ ] **步骤 3：运行完整测试套件**

运行：

```bash
python -m pytest -q
```

预期：exit code 0，0 failed。

- [ ] **步骤 4：检查补丁完整性与范围**

运行：

```bash
git diff --check
git status --short
git diff -- src/ai_news_sniffer/cli.py tests/test_cli.py
```

预期：`git diff --check` 无输出；变更只包含批准的规格、计划、`cli.py` 和 `test_cli.py`，不包含 workflow、部署或通知逻辑修改。

- [ ] **步骤 5：仅在验证导致文件变化时提交验证修正**

如果 Ruff 格式化产生文件变化，运行：

```bash
git add src/ai_news_sniffer/cli.py tests/test_cli.py
git commit -m "style: format URL verification changes"
```

如果没有文件变化，不创建空提交。

## 完成标准

- 404、408、425、429、5xx、网络错误和缺失页面标记使用斐波那契退避。
- 墙钟预算不超过 480 秒，并为最后一次请求预留最多 30 秒。
- 永久性 URL/HTTP 配置错误只请求一次或在请求前失败。
- 每次请求日志包含状态码或异常类型、请求 URL、最终 URL和分类；暂时性日志还包含下次等待与剩余预算。
- `tests/test_cli.py`、完整 pytest、Ruff 检查和 `git diff --check` 全部通过。
