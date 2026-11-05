"""渲染自包含执行结果页面，数据与所有本地链接均需安全转义。"""
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from .loader import load_execution_data


LABELS = {
    "passed": "通过", "failed": "失败", "skipped": "跳过", "pending": "未完成",
    "running": "运行中", "completed": "完成", "interrupted": "已中断", "partial": "部分失败",
    "disabled": "未启用", "not_run": "未执行", "unknown": "未知", "error": "异常",
}


def h(value):
    return escape(str(value if value is not None else "—"), quote=True)


def badge(value):
    status = str(value or "unknown")
    css = status if status in LABELS else "unknown"
    return f'<span class="badge {css}">{h(LABELS.get(status, status))}</span>'


def fmt_time(value):
    try:
        return datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M:%S") if value is not None else "—"
    except (ValueError, OSError, OverflowError, TypeError):
        return "—"


def fmt_duration(value):
    if not isinstance(value, (float, int)) or value < 0:
        return "—"
    if value < 60:
        return f"{value:.1f} 秒"
    return f"{int(value // 60)} 分 {int(value % 60)} 秒"


def local_link(root, path, label):
    """只链接本次任务内真实存在的文件，使用可移动的相对 URL。"""
    if path is None:
        return ""
    path = Path(path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return ""
    url = quote(path.relative_to(root).as_posix(), safe="/")
    return f'<a class="file" href="{h(url)}">{h(label)}</a>'


def child_path(base, relative):
    if base is None or not isinstance(relative, str) or not relative:
        return None
    path = Path(relative.replace("\\", "/"))
    if path.is_absolute() or path.drive or ".." in path.parts:
        return None
    return base / path


def phase_status(dynamic, phase):
    value = dynamic.get(phase)
    return value.get("status", "unknown") if isinstance(value, dict) else "unknown"


def detail(root, device, case, dynamic):
    entries = []
    if case.get("longrepr"):
        entries.append(f'<section class="detail-section"><h4>失败详情</h4><pre>{h(case["longrepr"])}</pre></section>')
    steps = case.get("steps") if isinstance(case.get("steps"), list) else []
    artifacts = case.get("artifacts") if isinstance(case.get("artifacts"), dict) else {}
    case_dir = child_path(device.directory, artifacts.get("case_dir"))
    if steps:
        step_html = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            image = local_link(root, child_path(case_dir, step.get("screenshot_path")), "查看截图")
            step_html.append(f'<li><span class="step-index">{h(step.get("index"))}</span><span>{h(step.get("description", ""))}</span>{image}</li>')
        if step_html:
            entries.append('<section class="detail-section"><h4>执行步骤</h4><ol class="steps">' + ''.join(step_html) + '</ol></section>')
    errors = []
    for phase, title in (("capture", "采集"), ("analysis", "解析"), ("upload", "上传")):
        data = dynamic.get(phase)
        if isinstance(data, dict) and data.get("error"):
            errors.append(f'<li>{h(title)}：{h(data["error"])}</li>')
    if errors:
        entries.append('<section class="detail-section"><h4>处理信息</h4><ul class="errors">' + ''.join(errors) + '</ul></section>')
    files = []
    for trace in dynamic.get("traces", []) if isinstance(dynamic.get("traces"), list) else []:
        if isinstance(trace, dict):
            link = local_link(root, child_path(device.directory, trace.get("path")), trace.get("name") or "Trace")
            if link:
                files.append(link)
    for log in dynamic.get("logs", []) if isinstance(dynamic.get("logs"), list) else []:
        if isinstance(log, dict):
            link = local_link(root, child_path(device.directory, log.get("path")), log.get("name") or "日志")
            if link:
                files.append(link)
    if files:
        entries.append('<section class="detail-section"><h4>采集文件</h4><div class="file-list">' + ''.join(files) + '</div></section>')
    path_text = ""
    if case_dir is not None and case_dir.resolve().is_relative_to(root):
        path_text = case_dir.resolve().relative_to(root).as_posix()
    entries.insert(0, f'<div class="detail-meta"><div><span>完整用例</span><code>{h(case.get("nodeid") or case.get("case_name"))}</code></div><div><span>开始</span>{h(fmt_time(case.get("started_at")))}</div><div><span>结束</span>{h(fmt_time(case.get("stopped_at")))}</div><div><span>产物目录</span><code>{h(path_text or "—")}</code></div></div>')
    return ''.join(entries)


def generate_execution_html(task_dir):
    data = load_execution_data(task_dir)
    counts = Counter(str(case.get("outcome") or "pending") for device in data.devices for case in device.cases)
    all_cases = [(device, case) for device in data.devices for case in device.cases]
    rank = {"failed": 0, "error": 1, "pending": 2, "skipped": 3, "passed": 4}
    all_cases.sort(key=lambda pair: (rank.get(pair[1].get("outcome"), 2), pair[0].serial, pair[1].get("round") or 0, str(pair[1].get("nodeid") or "")))
    device_rows = []
    for device in data.devices:
        c = Counter(str(case.get("outcome") or "pending") for case in device.cases)
        info = "" if device.session is not None else '<span class="muted">结果尚不可用</span>'
        links = ''.join(local_link(data.root, device.directory / name if device.directory else None, title) for name, title in (("execution.log", "运行日志"), ("pytest-output.log", "pytest 输出")))
        device_rows.append(f'<tr><td><strong>{h(device.serial)}</strong><br><span class="muted">{h(device.testbed)}</span></td><td>{badge(device.status)} {info}</td><td>{c["passed"]}</td><td class="red-number">{c["failed"]}</td><td>{c["skipped"]}</td><td>{h(fmt_duration(device.task.get("duration_seconds")))}</td><td><div class="file-list">{links or "—"}</div></td></tr>')
    case_rows = []
    for device, case in all_cases:
        ext = case.get("extensions") if isinstance(case.get("extensions"), dict) else {}
        dynamic = ext.get("dynamic_model") if isinstance(ext.get("dynamic_model"), dict) else {}
        outcome = str(case.get("outcome") or "pending")
        round_no = case.get("round")
        nodeid = case.get("nodeid") or case.get("case_name") or "未知用例"
        title = case.get("case_name") or str(nodeid).split("::")[-1]
        details = detail(data.root, device, case, dynamic)
        case_rows.append(f'<tr class="case-row" data-device="{h(device.serial)}" data-round="{h(round_no)}" data-outcome="{h(outcome)}" data-search="{h(str(nodeid).lower())}"><td>{h(device.serial)}</td><td>{h(round_no)}</td><td class="case-name"><details><summary><strong>{h(title)}</strong><span class="expand">查看详情</span></summary><div class="detail">{details}</div></details></td><td>{badge(outcome)}</td><td>{h(fmt_duration(case.get("duration")))}</td><td>{badge(phase_status(dynamic, "capture"))}</td><td>{badge(phase_status(dynamic, "analysis"))}</td><td>{badge(phase_status(dynamic, "upload"))}</td></tr>')
    options = ''.join(f'<option value="{h(d.serial)}">{h(d.serial)}</option>' for d in data.devices)
    rounds = sorted({case.get("round") for _, case in all_cases if isinstance(case.get("round"), int)})
    round_options = ''.join(f'<option value="{n}">第 {n} 轮</option>' for n in rounds)
    task = data.task
    status = str(task.get("status") or "unknown")
    body = f'''<main class="shell"><header class="hero"><div><div class="eyebrow">EXFW / DYNAMIC MODEL</div><h1>测试执行结果</h1><p>查看设备执行情况、失败用例与产物位置</p></div><div class="hero-status"><span>任务状态</span>{badge(status)}</div></header>
<section class="metadata"><div><span>开始时间</span><strong>{h(fmt_time(task.get('started_at')))}</strong></div><div><span>结束时间</span><strong>{h(fmt_time(task.get('stopped_at')))}</strong></div><div><span>执行耗时</span><strong>{h(fmt_duration(task.get('duration_seconds')))}</strong></div><div><span>测试设备</span><strong>{len(data.devices)} 台</strong></div><div><span>配置轮数</span><strong>{h(task.get('rounds') if task.get('rounds') is not None else '普通执行')}</strong></div></section>
<section class="metrics"><div class="metric"><span>已记录用例</span><strong>{len(all_cases)}</strong><small>按设备与轮次统计执行次数</small></div><div class="metric"><span>通过</span><strong class="green-text">{counts['passed']}</strong><small>执行成功</small></div><div class="metric"><span>失败</span><strong class="red-text">{counts['failed']}</strong><small>查看下方失败详情</small></div><div class="metric"><span>跳过 / 未完成</span><strong>{counts['skipped']} <i>/</i> {counts['pending']}</strong><small>仅统计已记录的用例</small></div></section>
<section class="panel"><div class="section-heading"><div><div class="eyebrow muted-eyebrow">DEVICES</div><h2>设备概览</h2></div><span class="section-note">每台设备对应一个 pytest 任务</span></div><div class="table-wrap"><table><thead><tr><th>设备 / 测试床</th><th>任务状态</th><th>通过</th><th>失败</th><th>跳过</th><th>耗时</th><th>日志</th></tr></thead><tbody>{''.join(device_rows) or '<tr><td colspan="7" class="empty">没有设备记录</td></tr>'}</tbody></table></div></section>
<section class="panel"><div class="section-heading"><div><div class="eyebrow muted-eyebrow">TEST CASES</div><h2>用例执行</h2></div><span class="section-note" id="case-count">{len(all_cases)} 条记录</span></div><div class="filters"><input id="search" type="search" placeholder="搜索用例名称或路径" aria-label="搜索用例"><select id="device" aria-label="筛选设备"><option value="">全部设备</option>{options}</select><select id="round" aria-label="筛选轮次"><option value="">全部轮次</option>{round_options}</select><select id="outcome" aria-label="筛选结果"><option value="">全部结果</option><option value="failed">失败</option><option value="passed">通过</option><option value="skipped">跳过</option><option value="pending">未完成</option></select></div><div class="table-wrap"><table><thead><tr><th>设备</th><th>轮次</th><th>用例 / 详情</th><th>执行结果</th><th>耗时</th><th>采集</th><th>解析</th><th>上传</th></tr></thead><tbody>{''.join(case_rows) or '<tr><td colspan="8" class="empty">暂无用例结果</td></tr>'}</tbody></table><p id="no-match" class="empty" hidden>没有符合筛选条件的用例</p></div></section><footer>执行结果快照 · 结果生成后不会自动刷新；重新运行生成命令可更新页面。</footer></main>'''
    page = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>测试执行结果</title><style>' + CSS + '</style></head><body>' + body + '<script>' + SCRIPT + '</script></body></html>'
    output = data.root / "execution_report.html"
    temporary = output.with_name(f".{output.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(page, encoding="utf-8")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


CSS = r'''
:root{font-family:Inter,"Segoe UI","Microsoft YaHei",sans-serif;color:#182235;background:#f4f6fa;font-size:14px}*{box-sizing:border-box}body{margin:0}.shell{max-width:1480px;margin:auto;padding:44px 48px 28px}.hero{display:flex;justify-content:space-between;align-items:center;gap:24px;margin-bottom:30px}.eyebrow{font-size:11px;font-weight:800;letter-spacing:.16em;color:#526ee8}.hero h1{font-size:34px;letter-spacing:-.04em;margin:9px 0 8px}.hero p{margin:0;color:#748095;font-size:14px}.hero-status{display:flex;align-items:center;gap:12px;color:#788397}.hero-status .badge{font-size:13px;padding:7px 12px}.metadata{display:flex;gap:44px;flex-wrap:wrap;border-top:1px solid #e0e6ef;padding:22px 0 27px}.metadata div{display:grid;gap:7px}.metadata span,.metric>span{color:#7a879a;font-size:12px}.metadata strong{font-size:13px;font-weight:600}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:26px}.metric,.panel{background:white;border:1px solid #e5eaf2;box-shadow:0 3px 14px rgba(26,45,87,.035);border-radius:12px}.metric{padding:20px 22px;display:grid;gap:8px}.metric strong{font-size:30px;letter-spacing:-.035em;line-height:1}.metric i{font-size:20px;font-style:normal;color:#c1c9d6}.metric small{font-size:11px;color:#a0aaba}.green-text{color:#188b6d}.red-text,.red-number{color:#d25155}.panel{margin:0 0 20px;padding:23px 24px}.section-heading{display:flex;justify-content:space-between;align-items:end;gap:10px;margin-bottom:19px}.muted-eyebrow{color:#99a5b7;letter-spacing:.13em;font-size:10px}h2{font-size:19px;letter-spacing:-.02em;margin:6px 0 0}.section-note{color:#9ba6b6;font-size:12px}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;text-align:left}th{background:#f7f9fc;color:#8490a2;font-size:11px;font-weight:600;white-space:nowrap;padding:11px 12px}td{border-bottom:1px solid #eef1f5;padding:13px 12px;vertical-align:top;font-size:12px}tbody tr:last-child td{border-bottom:0}.muted{color:#9ba6b6;font-size:11px}.badge{display:inline-block;padding:4px 8px;border-radius:6px;background:#f0f2f6;color:#718096;font-size:11px;white-space:nowrap}.passed,.completed{color:#168668;background:#e7f6f0}.failed,.error,.interrupted{color:#bd4249;background:#fceced}.partial{color:#a56718;background:#fff2dd}.running{color:#4d67cb;background:#eaf0ff}.filters{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px}.filters input,.filters select{height:36px;border:1px solid #e1e7ef;border-radius:7px;background:#fff;color:#526074;padding:0 11px;font:inherit;font-size:12px}.filters input{min-width:220px;flex:1}.filters input:focus,.filters select:focus{outline:2px solid #cad5ff}.file-list{display:flex;flex-wrap:wrap;gap:6px}.file{color:#526ee8;text-decoration:none;font-size:11px;overflow-wrap:anywhere}.file:hover{text-decoration:underline}.case-name{min-width:250px;max-width:560px}details summary{cursor:pointer;list-style:none;display:flex;justify-content:space-between;gap:12px;align-items:baseline}details summary::-webkit-details-marker{display:none}details summary strong{overflow-wrap:anywhere}.expand{font-size:11px;white-space:nowrap;color:#788de8}.detail{padding:17px 0 4px}.detail-meta{display:grid;gap:9px;color:#4e5d71}.detail-meta div{display:flex;gap:12px}.detail-meta span{color:#9ba6b6;min-width:48px}.detail-meta code{overflow-wrap:anywhere}.detail-section{margin-top:17px}.detail-section h4{font-size:12px;color:#718096;margin:0 0 9px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f8f9fc;border:1px solid #e9edf4;border-radius:7px;padding:12px;color:#4a5568;font:11px/1.6 Consolas,monospace;max-height:320px;overflow:auto}.steps{list-style:none;margin:0;padding:0;display:grid;gap:9px}.steps li{display:flex;gap:9px;align-items:baseline}.step-index{font-size:10px;color:#fff;background:#a6b3d2;border-radius:50%;width:19px;height:19px;display:inline-grid;place-items:center;flex:none}.errors{padding-left:18px;color:#a44d51}.empty{color:#9ba6b6;text-align:center;padding:24px}footer{font-size:11px;color:#a2adbc;text-align:center;padding:12px}tr[hidden],p[hidden]{display:none}@media(max-width:760px){.shell{padding:25px 16px}.hero h1{font-size:27px}.hero-status{align-self:flex-start}.metadata{gap:22px}.metrics{grid-template-columns:repeat(2,1fr)}.panel{padding:18px 14px}.section-note{display:none}th,td{padding:10px}}
'''

SCRIPT = r'''
const search=document.getElementById('search'),device=document.getElementById('device'),round=document.getElementById('round'),outcome=document.getElementById('outcome'),rows=[...document.querySelectorAll('.case-row')];function filter(){let visible=0;for(const row of rows){const match=(!device.value||row.dataset.device===device.value)&&(!round.value||row.dataset.round===round.value)&&(!outcome.value||row.dataset.outcome===outcome.value)&&row.dataset.search.includes(search.value.trim().toLowerCase());row.hidden=!match;if(match)visible++}document.getElementById('case-count').textContent=visible+' 条记录';document.getElementById('no-match').hidden=visible!==0||rows.length===0}for(const element of [search,device,round,outcome])element.addEventListener('input',filter);
'''
