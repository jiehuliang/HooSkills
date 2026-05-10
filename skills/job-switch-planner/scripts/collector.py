"""
Job Switch Planner — 岗位/讨论信息采集器

基于 OpenCLI (https://github.com/jackwener/OpenCLI) 采集各平台数据。

用法：
    python collector.py --keyword "Go 后端" --output result.json
    python collector.py --keyword "Go 后端" --platforms zhihu,boss,reddit

依赖：
    npm install -g @jackwener/opencli

首次使用 OpenCLI 需要登录认证：
    opencli zhihu search "test"   # 首次会自动打开浏览器引导登录
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class CollectResult:
    platform: str
    keyword: str
    items: list = field(default_factory=list)
    error: Optional[str] = None


def run_opencli(cmd: list, timeout: int = 30) -> dict:
    """执行 OpenCLI 命令并解析 JSON 输出。"""
    full_cmd = ["opencli"] + cmd + ["-f", "json"]
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()[:200]
            return {"error": f"退出码 {result.returncode}: {stderr}"}
        output = result.stdout.strip()
        if not output:
            return {"error": "无输出"}
        return json.loads(output)
    except subprocess.TimeoutExpired:
        return {"error": f"超时 ({timeout}s)"}
    except json.JSONDecodeError as e:
        return {"error": f"JSON 解析失败: {e}"}
    except FileNotFoundError:
        return {"error": "OpenCLI 未安装，请执行: npm install -g @jackwener/opencli"}
    except Exception as e:
        return {"error": str(e)[:200]}


def collect_zhihu(keyword: str, limit: int = 5) -> CollectResult:
    result = CollectResult(platform="知乎", keyword=keyword)
    data = run_opencli(["zhihu", "search", keyword, "--limit", str(limit)])
    if "error" in data:
        result.error = data["error"]
        return result
    items = data if isinstance(data, list) else data.get("data", data.get("results", []))
    for item in items[:limit]:
        result.items.append({
            "title": item.get("title", ""),
            "type": item.get("type", ""),
            "url": item.get("url", ""),
        })
    return result


def collect_boss(keyword: str, city: str = "北京", limit: int = 20) -> CollectResult:
    result = CollectResult(platform="Boss直聘", keyword=keyword)
    cmd = ["boss", "search", keyword, "--city", city, "--limit", str(limit)]
    data = run_opencli(cmd)
    if "error" in data:
        result.error = data["error"]
        return result
    items = data if isinstance(data, list) else data.get("data", data.get("results", []))
    for item in items[:limit]:
        result.items.append({
            "title": item.get("title", "") or item.get("jobName", "") or item.get("name", ""),
            "salary": item.get("salary", "") or item.get("salaryDesc", ""),
            "company": item.get("company", "") or item.get("brandName", ""),
        })
    return result


def collect_v2ex(keyword: str, limit: int = 20) -> CollectResult:
    result = CollectResult(platform="V2EX", keyword=keyword)
    # V2EX hot/latest 没有关键词参数，获取全量后过滤
    data = run_opencli(["v2ex", "hot", "--limit", str(limit)])
    if "error" in data:
        data = run_opencli(["v2ex", "latest", "--limit", str(limit)])
    if "error" in data:
        result.error = data["error"]
        return result
    items = data if isinstance(data, list) else data.get("data", data.get("results", []))
    for item in items[:limit]:
        title = item.get("title", "")
        keywords = [keyword.lower()] if keyword else []
        if any(kw in title.lower() for kw in keywords) or \
           any(kw in title for kw in ["招聘", "工作", "求职", "内推", "招人", "offer"]):
            result.items.append({"title": title, "url": item.get("url", "")})
    return result


def collect_reddit(keyword: str, subreddit: str = "", limit: int = 10) -> CollectResult:
    result = CollectResult(platform="Reddit", keyword=keyword)
    cmd = ["reddit", "search", keyword, "--limit", str(limit)]
    if subreddit:
        cmd += ["--subreddit", subreddit]
    data = run_opencli(cmd)
    if "error" in data:
        result.error = data["error"]
        return result
    items = data if isinstance(data, list) else data.get("data", data.get("results", []))
    for item in items[:limit]:
        result.items.append({
            "title": item.get("title", ""),
            "subreddit": item.get("subreddit", ""),
            "url": item.get("url", ""),
        })
    return result


def collect_hackernews(keyword: str, limit: int = 10) -> CollectResult:
    result = CollectResult(platform="HackerNews", keyword=keyword)
    data = run_opencli(["hackernews", "search", keyword])
    if "error" in data:
        result.error = data["error"]
        return result
    items = data if isinstance(data, list) else data.get("data", data.get("results", []))
    for item in items[:limit]:
        result.items.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
        })
    return result


def collect_51job(keyword: str, limit: int = 15) -> CollectResult:
    result = CollectResult(platform="前程无忧", keyword=keyword)
    data = run_opencli(["51job", "search", keyword, "--limit", str(limit)])
    if "error" in data:
        result.error = data["error"]
        return result
    items = data if isinstance(data, list) else data.get("data", data.get("results", []))
    for item in items[:limit]:
        result.items.append({
            "title": item.get("title", "") or item.get("jobName", ""),
            "company": item.get("company", "") or item.get("companyName", ""),
            "salary": item.get("salary", "") or item.get("salaryDesc", ""),
        })
    return result


PLATFORMS = {
    "zhihu": collect_zhihu,
    "boss": collect_boss,
    "v2ex": collect_v2ex,
    "reddit": collect_reddit,
    "hackernews": collect_hackernews,
    "51job": collect_51job,
}

PLATFORM_NOTES = {
    "zhihu": "✅ 知乎搜索（需登录）",
    "boss": "✅ Boss直聘搜索（需登录）",
    "v2ex": "✅ V2EX 热帖（公开）",
    "reddit": "✅ Reddit 搜索（需登录）",
    "hackernews": "✅ HackerNews 搜索（公开）",
    "51job": "✅ 前程无忧搜索（需登录）",
}


def main():
    parser = argparse.ArgumentParser(description="岗位/讨论信息采集器（基于 OpenCLI）")
    parser.add_argument("--keyword", required=True, help="搜索关键词")
    parser.add_argument("--output", help="输出文件路径（默认 stdout）")
    parser.add_argument("--platforms", default="zhihu,boss,51job",
                        help="平台列表，逗号分隔")
    args = parser.parse_args()

    selected = [p.strip() for p in args.platforms.split(",") if p.strip() in PLATFORMS]
    if not selected:
        print(json.dumps({"error": "无有效平台"}, ensure_ascii=False))
        sys.exit(1)

    for name in selected:
        note = PLATFORM_NOTES.get(name, "")
        print(f"[{name}] {note}", file=sys.stderr)

    results = {}
    for name in selected:
        collector = PLATFORMS[name]
        try:
            result = collector(args.keyword)
        except Exception as e:
            result = CollectResult(platform=name, keyword=args.keyword, error=str(e)[:200])

        results[name] = asdict(result)
        status = "✅" if len(result.items) > 0 and not result.error else "❌"
        detail = result.error or f"{len(result.items)} 条"
        print(f"[{name}] {status} {detail}", file=sys.stderr)

    output = json.dumps(results, ensure_ascii=False, indent=2, default=str)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
