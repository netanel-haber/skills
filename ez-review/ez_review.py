#!/usr/bin/env python3
"""E-Z-Review: make one HTML review page for GitHub PRs, with a note next to each diff hunk.

This file makes the page. The HTML, CSS and JavaScript of the page are in this file.
SKILL.md next to this file is the Claude Code skill. It tells Claude Code how to do a full review.
Its section "Brief for note writers" tells the agents how to write notes.

Commands:
    python3 -I ez_review.py init --repo OWNER/NAME --prs 101 102 [--clone PATH] [--dir DIR]
        Get the PRs. Write the diffs, the chunk files, the order files and the config.
    python3 -I ez_review.py brief [--mode review|explain]
        Show the instructions for note writers.
    python3 -I ez_review.py check DIR/ez-review.json
        Find hunks that have no note, and files that are not valid JSON.
    python3 -I ez_review.py render-multi DIR/ez-review.json DIR/review.html
        Make the page.
    python3 -I ez_review.py posted OWNER/NAME PR USER OUT.json
        Get the review threads that USER started on the PR.
    python3 -I ez_review.py split DIFF OUT_DIR
        Write one chunk file for each changed file.
    python3 -I ez_review.py render DIFF NOTES_DIR OUT.html --title "..."
        Make a page for one PR, without a config.
    python3 -I ez_review.py carry OLD_DIFF OLD_NOTES NEW_DIFF OUT_DIR
        Move the notes to a new version of the same PR.

Notes files:
    A PR has a notes folder. The tool reads all *.json files in it, in sorted path order.
    A later file replaces the same fields of an earlier file.

    {"files": {"path/to/file.py": {"summary": "...", "note": "..."}},
     "hunks": {"path/to/file.py#3": {"severity": "important|question|nit|pre-existing|info",
                                     "trivial": false, "summary": "...", "note": "...",
                                     "ask": {"priority": "should|question|nit", "title": "...",
                                             "text": "draft comment", "line": 123,
                                             "posted_url": "set this when you post the draft"}}},
     "threads": {"<discussion id>": {"state": "open|addressed|answered", "why": "..."}}}

    A hunk id is "<new path>#<index>". The index starts at 0 in each file.
    In a note, "#N" links to hunk N of the same file. "other.py hunk #N" links to hunk N of a
    different file. Notes can use Markdown: `code`, **bold**, *italic*, "- " lists, "1. " lists,
    ``` code blocks and "---" lines.

Config (ez-review.json). The init command writes it. Relative paths start at its folder.
    {"title": "...", "prs": [{"prefix": "101", "label": "#101 short name", "title": "...",
      "url": "https://github.com/OWNER/NAME/pull/101", "diff": "diffs/101.diff",
      "notes_dir": "notes-101", "order": "order-101.txt", "overview_file": "overview-101.md",
      "pages_dir": "pages-101", "git": {"repo": "PATH", "base": "SHA", "head": "REF"},
      "default_tab": "overview|todo", "posted": "posted-101.json", "collapsed": false}]}

Order file:
    Write one file path on each line, in reading order.
    A line "# 1. Section title" starts a section.
    An indented line "hunks: 3 0 1" after a path sets the order of the hunks in that file.
"""

import argparse
import hashlib
import html
import json
import os
import pathlib
import re
import subprocess
import sys

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")


def parse_diff(text):
    files = []
    cur = None
    hunk = None
    for line in text.splitlines():
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.*) b/(.*)$", line)
            cur = {"old": m.group(1), "path": m.group(2), "hunks": [], "add": 0, "del": 0}
            files.append(cur)
            hunk = None
            continue
        if cur is None:
            continue
        m = HUNK_RE.match(line)
        if m:
            o, n = int(m.group(1)), int(m.group(3))
            hunk = {"header": line, "ctx": m.group(5), "lines": [], "o": o, "n": n}
            cur["hunks"].append(hunk)
            continue
        if hunk is None:
            continue  # file metadata lines (index, ---, +++)
        if line.startswith("\\"):
            continue
        tag = line[:1] or " "
        body = line[1:]
        if tag == "+":
            hunk["lines"].append(["+", None, hunk["n"], body])
            hunk["n"] += 1
            cur["add"] += 1
        elif tag == "-":
            hunk["lines"].append(["-", hunk["o"], None, body])
            hunk["o"] += 1
            cur["del"] += 1
        else:
            hunk["lines"].append([" ", hunk["o"], hunk["n"], body])
            hunk["o"] += 1
            hunk["n"] += 1
    for f in files:
        for i, h in enumerate(f["hunks"]):
            h["id"] = f"{f['path']}#{i}"
            raw = h["header"] + "\n" + "\n".join(t + b for t, _, _, b in h["lines"])
            h["hash"] = hashlib.sha1(raw.encode()).hexdigest()[:12]
            del h["o"], h["n"]
    return files


def cmd_split(args):
    files = parse_diff(pathlib.Path(args.diff).read_text())
    split_to(files, pathlib.Path(args.out_dir))
    for f in files:
        print(f["path"], len(f["hunks"]), f["add"] + f["del"], sep="\t")


def load_notes(notes_dir):
    """Merge every *.json under notes_dir; later files merge field by field."""
    notes = {"files": {}, "hunks": {}, "threads": {}}
    pr_asks = []
    for p in sorted(pathlib.Path(notes_dir).glob("**/*.json")):
        d = json.loads(p.read_text())
        for group in ("files", "hunks"):
            for key, entry in d.get(group, {}).items():
                target = notes[group].setdefault(key, {})
                for k, v in entry.items():  # nested dicts (e.g. "ask") merge too
                    if isinstance(v, dict) and isinstance(target.get(k), dict):
                        target[k].update(v)
                    else:
                        target[k] = v
        notes["threads"].update(d.get("threads", {}))  # {discussion id: {"state", "why"}}
        if "pr_asks_replace" in d:  # a later file can replace the whole PR-level list
            pr_asks = list(d["pr_asks_replace"])
        pr_asks.extend(d.get("pr_asks", []))
        for a in pr_asks:  # {"pr_ask_status": {title: status}}
            if a.get("title") in d.get("pr_ask_status", {}):
                a["status"] = d["pr_ask_status"][a["title"]]
    return notes, pr_asks


def _content(h):
    return [t + b for t, _, _, b in h["lines"]]


def _remap_refs(text, own_path, idmap):
    """Rewrite "#N" (own file) and "x.py hunk #N" (other file) to new hunk numbers."""
    if not text:
        return text
    saved = []

    def keep(s):
        saved.append(s)
        return f"\0{len(saved) - 1}\0"

    def cross2(m):
        name = m.group(1).rstrip("`")
        tick = "`" if m.group(1).endswith("`") else ""
        for (path, i), (_, j) in idmap.items():
            if (path == name or path.endswith("/" + name)) and i == int(m.group(3)):
                return keep(f"{name}{tick}{m.group(2)}#{j}")
        return m.group(0)
    text = re.sub(r"([\w./-]+\.py`?)(\s+hunks?\s+)#(\d{1,3})\b", cross2, text)

    def own(m):
        key = (own_path, int(m.group(2)))
        return f"{m.group(1)}#{idmap[key][1]}" if key in idmap else m.group(0)
    text = re.sub(r"(^|[^\w&/])#(\d{1,3})\b", own, text)
    return re.sub(r"\0(\d+)\0", lambda m: saved[int(m.group(1))], text)


def cmd_carry(args):
    """Carry notes from an old diff to a new diff of the same PR."""
    import difflib
    old = {f["path"]: f for f in parse_diff(pathlib.Path(args.old_diff).read_text())}
    new = parse_diff(pathlib.Path(args.new_diff).read_text())
    notes, pr_asks = load_notes(args.old_notes)
    out = {"files": {}, "hunks": {}, "pr_asks": pr_asks, "threads": notes["threads"]}
    idmap = {}      # (path, old index) -> (path, new index)
    counts = {}
    for f in new:
        if f["path"] in notes["files"]:
            out["files"][f["path"]] = dict(notes["files"][f["path"]])
        olds = old.get(f["path"], {"hunks": []})["hunks"]
        used = set()
        for j, h in enumerate(f["hunks"]):
            status, match = "new", None
            for i, o in enumerate(olds):
                if i not in used and o["hash"] == h["hash"]:
                    status, match = "unchanged", i
                    break
            if match is None:
                for i, o in enumerate(olds):
                    if i not in used and _content(o) == _content(h):
                        status, match = "moved", i
                        break
            if match is None:
                best, best_r = None, 0.0
                hc = [l for l in _content(h) if l[:1] in "+-"]
                for i, o in enumerate(olds):
                    if i in used:
                        continue
                    oc = [l for l in _content(o) if l[:1] in "+-"]
                    r = difflib.SequenceMatcher(None, oc, hc).ratio()
                    if r > best_r:
                        best, best_r = i, r
                if best is not None and best_r >= 0.4:
                    status, match = "changed", best
            entry = {}
            if match is not None:
                used.add(match)
                o = olds[match]
                idmap[(f["path"], match)] = (f["path"], j)
                entry = json.loads(json.dumps(notes["hunks"].get(o["id"], {})))
                entry["prev"] = {"id": o["id"], "hash": o["hash"]}
            entry["change"] = status
            out["hunks"][h["id"]] = entry
            counts[status] = counts.get(status, 0) + 1
    # renumber hunk references in carried text
    for hid, e in out["hunks"].items():
        path = hid.rsplit("#", 1)[0]
        for k in ("summary", "note"):
            e[k] = _remap_refs(e.get(k), path, idmap)
        if e.get("ask"):
            e["ask"]["text"] = _remap_refs(e["ask"].get("text"), path, idmap)
    for path, e in out["files"].items():
        e["note"] = _remap_refs(e.get("note"), path, idmap)
    outp = pathlib.Path(args.out_dir)
    outp.mkdir(parents=True, exist_ok=True)
    (outp / "carried.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(counts, file=sys.stderr)
    for f in new:
        for j, h in enumerate(f["hunks"]):
            st = out["hunks"][h["id"]]["change"]
            if st in ("changed", "new"):
                prev = out["hunks"][h["id"]].get("prev", {}).get("id", "-")
                print(f"{st:8} {h['id']}  (was {prev})")


def add_ws_views(files, repo, base, head):
    """Give each hunk "ws": its lines as `git diff -w` aligns them (whitespace-only changes
    become context), cut to the hunk's old and new line ranges. Without git, the page
    falls back to a per-hunk approximation."""
    import subprocess
    git = lambda *a: subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True).stdout
    for f in files:
        full = parse_diff(git("diff", "-w", "-U999999", base, head, "--", f["path"]))
        if not full:
            continue  # whitespace-only file (or no change): the page's fallback handles it
        lines = [l for h in full[0]["hunks"] for l in h["lines"]]
        new_text = git("show", f"{head}:{f['path']}").split("\n")
        for h in f["hunks"]:
            olds = [o for _, o, _, _ in h["lines"] if o is not None]
            news = [n for _, _, n, _ in h["lines"] if n is not None]
            o1, o2 = (min(olds), max(olds)) if olds else (0, -1)
            n1, n2 = (min(news), max(news)) if news else (0, -1)
            h["ws"] = [[t, o, n, new_text[n - 1] if t == " " and n and n <= len(new_text) else b]
                       for t, o, n, b in lines
                       if (o is not None and o1 <= o <= o2) or (n is not None and n1 <= n <= n2)]


def build_pr(cfg, out):
    """Page data for one PR. cfg: diff, notes_dir, title, prefix, and optional url, label,
    overview, subst, order, since, posted, seed_viewed, pages_dir, collapsed."""
    tag = cfg.get("label") or cfg["prefix"]
    files = parse_diff(pathlib.Path(cfg["diff"]).read_text())
    for f in files:  # GitHub "Files changed" anchor: #diff-<sha256(path)>R<line>
        f["anchor"] = hashlib.sha256(f["path"].encode()).hexdigest()
    if cfg.get("same_as"):  # {"prefix", "diff"}: a stacked PR's hunks that equal a hunk of the PR below
        below = {(f["path"], tuple(_content(h))): f"{h['id']}@{h['hash']}"
                 for f in parse_diff(pathlib.Path(cfg["same_as"]["diff"]).read_text()) for h in f["hunks"]}
        for f in files:
            for h in f["hunks"]:
                k = below.get((f["path"], tuple(_content(h))))
                if k:
                    h["same_as"] = [cfg["same_as"]["prefix"], k]
    if cfg.get("git"):  # {"repo", "base", "head"}: exact `git diff -w` view for "hide whitespace"
        add_ws_views(files, cfg["git"]["repo"], cfg["git"]["base"], cfg["git"]["head"])
    # Files load in sorted path order; a later file's entry is merged into an
    # earlier one field by field, so an overrides file only needs the changed fields.
    notes, pr_asks = load_notes(cfg["notes_dir"])
    if cfg.get("subst"):  # {regex: replacement}, applied to every summary/note
        subs = json.loads(pathlib.Path(cfg["subst"]).read_text())
        for group in (notes["files"], notes["hunks"]):
            for entry in group.values():
                for k in ("summary", "note"):
                    for pat, rep in subs.items():
                        if entry.get(k):
                            entry[k] = re.sub(pat, rep, entry[k])
                        if k == "note" and (entry.get("ask") or {}).get("text"):
                            entry["ask"]["text"] = re.sub(pat, rep, entry["ask"]["text"])
    anchors = {f["path"]: f["anchor"] for f in files}
    for hid, entry in notes["hunks"].items():  # an ask with "line" and no "link": link that line on GitHub
        a = entry.get("ask")
        if a and a.get("line") and not a.get("link") and cfg.get("url"):
            a["link"] = f'{cfg["url"]}/files#diff-{anchors.get(hid.rsplit("#", 1)[0], "")}R{a["line"]}'
    ids = {h["id"] for f in files for h in f["hunks"]}
    unknown = sorted(set(notes["hunks"]) - ids)
    missing = sorted(ids - set(notes["hunks"]))
    if unknown:
        print(f"{tag}: warning: {len(unknown)} note ids match no hunk: {unknown[:5]}", file=sys.stderr)
    print(f"{tag}: {len(ids)} hunks, {len(ids) - len(missing)} with notes, {len(missing)} without",
          file=sys.stderr)
    if cfg.get("order"):  # file paths in reading order; unlisted files keep diff order, at the end
        # An indented "hunks: 4 0 2" line after a path gives that file's hunk reading order
        # (numbers as in the hunk ids); unlisted hunks follow in line order.
        # A "# 1. Title" comment starts a section; the page shows it above that section's first file.
        order, hunk_order, section, sections = [], {}, None, {}
        for l in pathlib.Path(cfg["order"]).read_text().splitlines():
            t = l.strip()
            m = re.match(r"#\s*(\d+\.\s+.*)", t)
            if m:
                section = m.group(1)
                continue
            if not t or t.startswith("#"):
                continue
            if t.startswith("hunks:") and order:
                hunk_order[order[-1]] = [int(x) for x in t[len("hunks:"):].split()]
            else:
                order.append(t)
                if section:
                    sections[t], section = section, None
        for f in files:
            if f["path"] in sections:
                f["section"] = sections[f["path"]]
            if f["path"] in hunk_order:
                by_num = {int(h["id"].rsplit("#", 1)[1]): h for h in f["hunks"]}
                seq = [n for n in dict.fromkeys(hunk_order[f["path"]]) if n in by_num]
                if len(seq) != len(hunk_order[f["path"]]):
                    print(f"{tag}: warning: bad hunk order for {f['path']}", file=sys.stderr)
                f["hunks"] = [by_num[n] for n in seq] + [h for n, h in by_num.items() if n not in seq]
        rank = {p: i for i, p in enumerate(order)}
        for p in order:
            if not any(f["path"] == p for f in files):
                print(f"{tag}: warning: --order path not in diff: {p}", file=sys.stderr)
        files.sort(key=lambda f: rank.get(f["path"], len(order)))
    gmap, order = {}, []
    for f in files:
        for h in f["hunks"]:
            order.append((f, h))
            gmap[h["id"]] = len(order)
    pages_rel = (os.path.relpath(cfg["pages_dir"], pathlib.Path(out).parent)
                 if cfg.get("pages_dir") else "")
    posted = json.loads(pathlib.Path(cfg["posted"]).read_text()) if cfg.get("posted") else []
    seed = set(json.loads(pathlib.Path(cfg["seed_viewed"]).read_text())) if cfg.get("seed_viewed") else set()
    data = {"prefix": cfg["prefix"], "label": cfg.get("label", ""), "title": cfg["title"],
            "url": cfg.get("url", ""), "overview": cfg.get("overview", ""), "default_tab": cfg.get("default_tab", ""),
            "collapsed": bool(cfg.get("collapsed")), "gmap": gmap, "pages_rel": pages_rel,
            "files": files, "notes": notes, "pr_asks": pr_asks, "since": cfg.get("since", ""),
            "posted": [{**t, "status": notes["threads"].get(t["url"].rsplit("_r", 1)[-1])} for t in posted],
            "seed_viewed": [f"{h['id']}@{h['hash']}" for f in files for h in f["hunks"] if h["id"] in seed]}
    return data, order


def write_page(path, title, prs, built):
    payload = json.dumps({"built": built, "prs": prs}).replace("</", "<\\/")
    pathlib.Path(path).write_text(
        TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__DATA__", payload))


def render_all(cfgs, out, page_title):
    """One page with a collapsible section per PR, plus optional one-hunk pages per PR."""
    built = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prs = [build_pr(c, out) for c in cfgs]
    write_page(out, page_title, [d for d, _ in prs], built)
    for cfg, (data, order) in zip(cfgs, prs):
        if not cfg.get("pages_dir"):
            continue
        pages_dir = pathlib.Path(cfg["pages_dir"])
        pages_dir.mkdir(parents=True, exist_ok=True)
        full = os.path.relpath(pathlib.Path(out), pages_dir)
        notes = data["notes"]
        for g, (f, h) in enumerate(order, 1):
            one = {**data, "overview": "", "pr_asks": [], "posted": [], "collapsed": False,
                   "files": [{**f, "hunks": [h]}],
                   "notes": {"files": {k: v for k, v in notes["files"].items() if k == f["path"]},
                             "hunks": {h["id"]: notes["hunks"].get(h["id"], {})}, "threads": {}},
                   "single": {"g": g, "total": len(order), "full": full,
                              "prev": g - 1 if g > 1 else None,
                              "next": g + 1 if g < len(order) else None}}
            write_page(pages_dir / f"{g}.html", f"#{g} · {data['title']}", [one], built)
        print(f"{cfg['prefix']}: wrote {len(order)} hunk pages to {pages_dir}/", file=sys.stderr)
    print(f"wrote {out}", file=sys.stderr)


def cmd_render(args):
    cfg = {k: getattr(args, k) for k in ("diff", "notes_dir", "title", "url", "overview", "subst",
                                          "order", "since", "posted", "seed_viewed", "pages_dir")}
    cfg["prefix"] = args.prefix
    render_all([cfg], args.out, args.title)


def cmd_render_multi(args):
    """CONFIG: {"title": "...", "prs": [build_pr cfg, ...]}; "overview_file" reads the overview from a file."""
    out = pathlib.Path(args.out).resolve()
    conf_path = pathlib.Path(args.config).resolve()
    os.chdir(conf_path.parent)
    args.out = str(out)
    conf = json.loads(conf_path.read_text())
    for c in conf["prs"]:
        if c.get("overview_file"):
            c["overview"] = pathlib.Path(c["overview_file"]).read_text()
    render_all(conf["prs"], args.out, conf["title"])


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{color-scheme:dark;--bg:#0a0c10;--fg:#f0f3f6;--muted:#9ea7b3;--line:#525964;--panel:#272b33;
 --add:#09b43a26;--addn:#26cd4d4d;--del:#ff6a6926;--deln:#ff6a694d;--hunk:#409eff26;
 --imp:#ff6a69;--q:#f0b72f;--nit:#9ea7b3;--pre:#b780ff;--info:#71b7ff;--ok:#26cd4d}
/* GitHub Dark High Contrast (fixed, regardless of OS theme) */
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:13.5px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,"DejaVu Sans",sans-serif}
code,pre,.code{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono","DejaVu Sans Mono",monospace;font-size:12px}
header{position:sticky;top:0;z-index:5;background:var(--panel);border-bottom:1px solid var(--line);
 padding:3px 8px;display:flex;flex-wrap:wrap;gap:2px 10px;align-items:center}
header h1{font-size:14px;margin:0}
/* page-wide controls: scroll away with the page (the PR bars are the sticky ones) */
#topbar{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;padding:6px 12px;background:var(--panel);border-bottom:1px solid var(--line)}
#topbar .ttl{font-size:14px} #topbar .sp{flex:1} #topbar label{white-space:nowrap;font-size:12px} body.single #topbar{display:none}
.bar{flex:1 1 120px;min-width:80px;height:6px;background:var(--line);border-radius:4px;overflow:hidden}
.bar>div{height:100%;background:var(--info);width:0}
header label{white-space:nowrap;font-size:12px}
button{font:inherit;font-size:12px;padding:1px 6px;border:1px solid var(--line);border-radius:6px;
 background:var(--bg);color:var(--fg);cursor:pointer}
.layout{display:grid;grid-template-columns:210px minmax(0,1fr);gap:0}
nav{position:sticky;top:0;align-self:start;max-height:100vh;overflow:auto;
 border-right:1px solid var(--line);padding:8px 6px;font-size:12.5px}
nav a{display:flex;gap:6px;align-items:center;color:var(--fg);text-decoration:none;padding:1px 5px;border-radius:4px}
nav a:hover{background:var(--panel)} nav a.done{color:var(--muted);text-decoration:line-through}
nav .cnt{margin-left:auto;color:var(--muted);white-space:nowrap;flex:none} nav{overflow-x:hidden}
nav a>span:not(.cnt):not(.chip){overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0} nav .chip{flex:none}
main{padding:8px 12px;min-width:0}
.overview{line-height:1.45} .overview p{margin:4px 0}
.panel{border:1px solid var(--line);border-radius:5px;margin:0 0 8px;background:var(--panel)}
.panel .tabs{display:flex;gap:2px;align-items:center;padding:3px 6px 0;border-bottom:1px solid var(--line)}
.panel[data-tab=""] .tabs{border-bottom:0;padding-bottom:3px}
.panel .tab{border:1px solid transparent;border-bottom:0;border-radius:5px 5px 0 0;background:none;padding:3px 10px;font-size:12.5px;color:var(--muted)}
.panel .tab b{margin-left:3px;color:var(--fg)} .panel .tab.on{background:var(--bg);border-color:var(--line);color:var(--fg);margin-bottom:-1px}
.panel .tabhint{margin-left:auto;font-size:11px}
.panel .pane{padding:6px 12px;background:var(--bg);border-radius:0 0 5px 5px;line-height:1.45;overflow-wrap:anywhere}
.panel .pane ol{margin:2px 0 4px;padding-left:22px} .panel .pane li{margin:3px 0} .panel a{color:var(--info);text-decoration:none} .panel .loc{color:var(--muted);font-size:12px}
.todolist .praskitem{margin:4px 0 8px}
body.single .panel{display:none}
.file{border:1px solid var(--line);border-radius:5px;margin-bottom:6px}
.fhead{display:flex;gap:10px;align-items:center;padding:4px 10px;background:var(--panel);
 border-bottom:1px solid var(--line);position:sticky;top:var(--hh,0px);z-index:3;flex-wrap:wrap}
.fhead .path{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono","DejaVu Sans Mono",monospace;font-size:13px;font-weight:600;word-break:break-all}
.fview{margin-left:auto;display:inline-flex;gap:6px;align-items:center;color:var(--muted);font-size:12px} .stat .a{color:var(--ok)} .stat .d{color:var(--imp)}
.fnote{padding:5px 10px;border-bottom:1px solid var(--line);font-size:12.5px} .fnote p{margin:3px 0}
/* code column as wide as its longest line (it scrolls when the screen is narrower); the note takes the rest */
.hunk{display:grid;grid-template-columns:minmax(0,max-content) minmax(340px,1fr);column-gap:14px;border-bottom:1px solid var(--line)}
.hunk:last-child{border-bottom:0}
.hbar{grid-column:1/-1;display:flex;gap:9px;align-items:center;background:var(--hunk);padding:3px 10px;
 font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono","DejaVu Sans Mono",monospace;font-size:12px;color:var(--muted);cursor:pointer}
.hbar .hdr{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0} .hbar{min-width:0}
.diff{overflow-x:auto;min-width:0}
table{border-collapse:collapse;width:100%}
td{padding:0 6px;vertical-align:top;white-space:pre}
td.ln{width:1%;color:var(--muted);text-align:right;user-select:none;font-size:11px}
tr.p td,td.p{background:var(--add)} tr.p td.ln,td.ln.p{background:var(--addn)}
tr.m td,td.m{background:var(--del)} tr.m td.ln,td.ln.m{background:var(--deln)}
tr.p .x,td.p .x{background:#26cd4d5c;border-radius:2px} tr.m .x,td.m .x{background:#ff6a6966;border-radius:2px}
/* split view: old | new; a side with no line is hatched, as on GitHub */
table.split{table-layout:fixed} table.split col.ln{width:5.5ch} table.split td.ln.r{border-left:1px solid var(--line)}
table.split td.code{white-space:pre-wrap;overflow-wrap:anywhere}  /* fixed halves: a long old line must not squeeze the new side */
td.e{background:repeating-linear-gradient(-45deg,transparent 0 4px,#8881 4px 8px)} td .sg{color:var(--muted);user-select:none}
.tk-k{color:#ff9492} .tk-s{color:#addcff} .tk-c{color:#9ea7b3;font-style:italic} .tk-n{color:#91cbff} .tk-d,.tk-f{color:#dbb7ff} .tk-b{color:#ffb757}
.side{border-left:1px solid var(--line);padding:6px 14px;font-size:12.5px;line-height:1.45;background:var(--bg)}
.side .sum{font-weight:600;margin:1px 0 2px}
.side,.fnote,.overview,.asks,.prasks{overflow-wrap:anywhere;min-width:0} .side code,.fnote code,.overview code,.asks code{overflow-wrap:anywhere}
.overview hr,.side hr,.fnote hr{border:0;border-top:1px solid var(--line);margin:8px 0} .side p{margin:4px 0} .side ul,.fnote ul,.overview ul,.todotext ul,.side ol,.fnote ol,.overview ol,.todotext ol{margin:2px 0;padding-left:18px} .side code{background:var(--panel);padding:0 3px;border-radius:3px}
.chip{display:inline-block;font-size:11px;font-weight:600;padding:1px 8px;border-radius:10px;border:1px solid currentColor}
.important{color:var(--imp)} .question{color:var(--q)} .nit{color:var(--nit)} .pre-existing{color:var(--pre)}
.info{color:var(--info)} .trivial{color:var(--muted)}
.hunk.viewed .diff,.hunk.viewed .side{display:none}
.hunk.viewed .hbar>*{opacity:.6}
.file:not(.fopen) .fnote,.file:not(.fopen) .hunks{display:none}
.fhead{cursor:pointer} .fhead::before{content:'▸';color:var(--muted)} .file.fopen .fhead::before{content:'▾'}
.hbar{cursor:pointer} .hbar::before{content:'▾';color:var(--muted)} .hunk.folded:not(.viewed) .diff,.hunk.folded:not(.viewed) .side{display:none} .hunk.folded:not(.viewed) .hbar::before{content:'▸'}
.hunk.viewed .hbar::before{content:'▸'} .hunk.viewed.peek .hbar::before{content:'▾'} .hunk.viewed.peek .hbar>*{opacity:.85}
.pr.hideviewed .hunk.viewed,.pr.hideviewed .file.fviewed{display:none}
.pr.onlyflag .hunk:not(.flag){display:none}
.hunk.focus{outline:2px solid var(--info);outline-offset:-2px}
.hunk{scroll-margin-top:calc(var(--hh,0px) + var(--fh,0px))}
/* the hunk bar sticks under the PR and file headers; the layered background keeps the tint opaque */
.hbar{position:sticky;top:calc(var(--hh,0px) + var(--fh,0px));z-index:2;background:linear-gradient(var(--hunk),var(--hunk)),var(--bg)}
.hunk.viewed.peek .diff,.hunk.viewed.peek .side{display:block}
.flash{animation:flash 2.6s ease-out} @keyframes flash{0%,45%{box-shadow:0 0 0 3px var(--q)}100%{box-shadow:0 0 0 3px transparent}}
tr.askline td{background:#f0b72f2e} tr.askline td.ln{box-shadow:inset 3px 0 var(--q)}
a.hnum{color:var(--info);text-decoration:none}
a.ghh{flex:none;color:var(--info);text-decoration:none;font-weight:700;font-size:13px;border:1px solid var(--line);border-radius:4px;padding:0 6px;background:var(--bg)}
a.ghh:hover{border-color:var(--info)}
.pager{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:4px;font-size:13px}
.pager a{color:var(--info);text-decoration:none;font-weight:600}
body.single header label, body.single #trivbtn, body.single #resetbtn, body.single .bar,
body.single #progtxt, body.single #navbtn, body.single .asks{display:none}
.empty{color:var(--muted);font-style:italic}
.hnum{font-weight:700;color:var(--fg);min-width:2.2em}
.chip.st{color:var(--muted)} .chip.chg,.chip.newh{color:var(--pre);border-style:dashed} .chip.done{color:var(--info)}
.pr.onlychg .hunk:not(.chg){display:none} .pr.onlychg .file:not(.chg){display:none}
a.hlink{color:var(--info);text-decoration:none;font-weight:600}
.ask{margin:0 0 4px;border:1px solid var(--q);border-left-width:3px;border-radius:4px;padding:4px 10px;background:var(--panel)}
.ask .askhead{display:flex;flex-wrap:wrap;align-items:center;gap:6px;font-weight:600;margin-bottom:1px}
.ask .askhead button{margin-left:auto}
.ask.must{border-color:var(--imp)} .ask.should{border-color:var(--q)} .ask.nit{border-color:var(--nit)}
.chip.must{color:var(--imp)} .chip.should{color:var(--q)} .chip.ask-question{color:var(--info)}
.chip.todo{color:var(--bg);border-color:transparent;background:var(--q)} .chip.todo.must{background:var(--imp)} .chip.todo.nit{background:var(--nit)} .chip.todo.ask-question{background:var(--info)}
.pr.onlyask .hunk:not(.hasask){display:none} .pr.onlyask .file:not(.hasask){display:none}
.asks{border:1px solid var(--line);border-radius:5px;padding:5px 12px;margin-bottom:7px;line-height:1.45}
.asks h2{font-size:13px;margin:0 0 3px}
.asks ol{margin:0 0 4px;padding-left:22px} .asks li{margin:2px 0} .tlinks{margin-top:6px;font-size:12px;color:var(--muted)} .tlinks summary{font-size:12px} .tlinks div{padding:4px 0 0 14px}
.asks a{color:var(--info);text-decoration:none} .asks .loc{color:var(--muted);font-size:12px}
.asks summary{cursor:pointer;font-size:13px} .todotext{margin:2px 0 8px;font-size:13px}
.todotext p{margin:3px 0} .prasks{margin:0 0 7px} .prasks h2{font-size:13px;margin:3px 0 4px} .praskitem{scroll-margin-top:calc(var(--hh,0px) + 10px);margin-bottom:6px} pre.mdcode{white-space:pre;overflow-x:auto;background:var(--panel);padding:2px 6px;border-radius:3px;margin:2px 0;font-size:11.5px} a.gh{color:var(--info);font-weight:600;text-decoration:none;font-size:12px;white-space:nowrap}
.posted{margin:0 0 3px;font-size:12px;color:var(--muted)} .posted a{color:var(--info)}
body.nonav .layout{grid-template-columns:minmax(0,1fr)} body.nonav nav{display:none}
@media (max-width:900px){.layout{grid-template-columns:1fr}nav{display:none}.hunk{grid-template-columns:1fr}
 .side{border-left:0;border-top:1px dashed var(--line)}}
.pr{margin-bottom:6px}
.prhead{display:flex;align-items:center;gap:6px 12px;flex-wrap:wrap;padding:6px 10px;background:var(--panel);border:1px solid var(--line);border-radius:5px;margin-bottom:8px;cursor:pointer;position:sticky;top:0;z-index:5}
.prctl{display:flex;flex-wrap:nowrap;align-items:center;gap:4px 12px;margin-left:auto;flex:none} .pr.collapsed .prctl{display:none} .prhead label{white-space:nowrap;font-size:12px;cursor:pointer}
.prhead .goto{font:inherit;font-size:12px;width:4em} .prhead .navbtn{padding:0 5px}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:6px;overflow:hidden}
.seg label{padding:1px 9px;font-size:12px;cursor:pointer;border-left:1px solid var(--line)} .seg label:first-child{border-left:0}
.seg input{position:absolute;opacity:0;pointer-events:none} .seg label:has(input:checked){background:var(--info);color:var(--bg);font-weight:600}
.seg label:has(input:focus-visible){outline:2px solid var(--info);outline-offset:-2px}
details.more{position:relative} details.more>summary{list-style:none;cursor:pointer;padding:0 8px;border:1px solid var(--line);border-radius:6px;font-weight:700}
details.more>summary::-webkit-details-marker{display:none}
details.more .menu{position:absolute;right:0;top:calc(100% + 4px);z-index:8;display:flex;flex-direction:column;gap:4px;padding:6px;background:var(--panel);border:1px solid var(--line);border-radius:6px;box-shadow:0 6px 18px #0009;white-space:nowrap}
details.more .resetbtn{color:var(--imp);border-color:var(--imp)}
#xfer{background:var(--panel);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:12px;width:min(640px,92vw)}
#xfer::backdrop{background:#0008} #xfer textarea{width:100%;height:160px;box-sizing:border-box;font:12px ui-monospace,monospace;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:4px}
#xfer .row{display:flex;gap:8px;justify-content:flex-end;margin-top:8px}
.helpbtn{font-weight:700;padding:0 7px}
#help{position:fixed;z-index:9;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:8px 12px;box-shadow:0 6px 18px #0009;font-size:12.5px;max-width:420px}
#help td{white-space:normal;padding:1px 10px 1px 0} #help td:first-child{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono","DejaVu Sans Mono",monospace;color:var(--info);white-space:nowrap}
#help .loc{color:var(--muted);font-size:11.5px;margin-top:6px}
.todochip{border:0;padding:0;background:none}
#toast{position:fixed;left:50%;bottom:24px;transform:translate(-50%,8px);z-index:20;background:var(--info);color:#fff;font-weight:600;padding:7px 14px;border-radius:6px;box-shadow:0 4px 14px #0008;opacity:0;pointer-events:none;transition:opacity .15s,transform .15s}
#toast.on{opacity:1;transform:translate(-50%,0)}
#status{position:fixed;right:6px;bottom:3px;z-index:6;font-size:11px;color:var(--imp);background:var(--bg);padding:0 4px;border-radius:3px;display:none}
.prhead::before{content:'▾';color:var(--muted)} .pr.collapsed .prhead::before{content:'▸'}
.prhead h2{font-size:15px;margin:0;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap} .prhead>*{flex:none} .prhead>h2{flex:0 1 auto;min-width:14em} .prhead h2 a{color:inherit} .prhead .bar{flex:0 0 56px}
.prhead .loc{color:var(--muted);font-size:12px}
.pr.collapsed .prbody{display:none}
nav .dot{flex:none;font-size:9px;color:transparent} nav .dot.important{color:var(--imp)} nav .dot.question{color:var(--q)}
nav .legend{color:var(--muted);font-size:11px;padding:0 5px 4px;border-bottom:1px solid var(--line)} nav .legend .dot{font-size:9px}
.osec{margin:14px 2px 6px;color:var(--muted);font-size:12.5px;font-weight:600;border-bottom:1px solid var(--line);padding-bottom:3px}
nav .navsec{color:var(--muted);font-size:11px;margin:6px 5px 1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
nav .navgrp-h{font-weight:700;margin-top:8px} nav .navgrp.collapsed .navfiles{display:none}
nav .navgrp.collapsed .navgrp-h{color:var(--muted)}
body.single .prhead{display:none}
.dstat{display:inline-flex;gap:1px;vertical-align:middle;margin-left:2px} .dstat i{width:8px;height:8px;border-radius:1px;background:var(--line)}
.dstat i.a{background:var(--ok)} .dstat i.d{background:var(--imp)}
.hunk.wsonly .hbar .hdr::after{content:' · whitespace only';color:var(--muted)}
</style></head><body>
<div id="status"></div>
<div id="help" hidden><b>Keys</b><table><tr><td>j / k</td><td>next / previous unviewed hunk</td></tr><tr><td>v</td><td>mark the current hunk viewed, go to the next</td></tr><tr><td>Space</td><td>on a checkbox: check it, go to the next one</td></tr><tr><td>Tab</td><td>on a checkbox: next checkbox</td></tr><tr><td>?</td><td>show / hide this help</td></tr></table><div class="loc" id="built"></div></div>
<div id="topbar"><b class="ttl"></b>
  <button class="navbtn" title="show / hide the file list">☰ files</button>
  <label title="show old and new code side by side, in all PRs; a hunk that only adds lines stays inline"><input type="checkbox" id="splitchk"> split view</label>
  <span class="sp"></span>
  <button class="copystate" title="copy the viewed marks and settings of all PRs, to paste in another browser">Copy review state</button>
  <button class="pastestate" title="replace this browser's viewed marks and settings with ones copied from another browser">Paste review state…</button>
  <button class="helpbtn" title="keyboard shortcuts">?</button></div>
<div class="layout"><nav id="nav"></nav><main id="main"></main></div>
<script id="data" type="application/json">__DATA__</script>
<script>
const STATUS = document.getElementById('status');
// height of the sticky header above an element: its PR's header
const HH = el => {  // PR header + file header
  const h = el && el.closest('.pr') && el.closest('.pr').querySelector('.prhead'), f = el && el.closest('.file') && el.closest('.file').querySelector('.fhead');
  return (h ? h.offsetHeight : 0) + (f ? f.offsetHeight : 0);
};
const status = t => { STATUS.textContent += (STATUS.textContent ? ' · ' : '') + t; console.log('[review]', t); };
window.addEventListener('error', e => { STATUS.style.display = 'block'; status('ERROR: ' + e.message + ' (line ' + e.lineno + ')'); });
const ROOT = JSON.parse(document.getElementById('data').textContent);
document.getElementById('built').textContent = 'Page built ' + ROOT.built;
const SINGLE = ROOT.prs.length === 1 ? ROOT.prs[0].single || null : null;
const store = {  // localStorage, tolerant of private mode
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
};
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
// tiny markdown: paragraphs, `code`, **bold**, "- " lists, ``` fences
function md(s) {
  if (!s) return '';
  const inline = t => esc(t).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/(^|[\s(])\*([^*\s][^*]*?)\*(?=[\s.,;:)]|$)/g, '$1<i>$2</i>');
  let out = '', para = [], items = [], code = null, ol = false;
  const flushP = () => { if (para.length) out += '<p>' + para.map(inline).join('<br>') + '</p>'; para = []; };
  const flushL = () => { const t = ol ? 'ol' : 'ul'; if (items.length) out += `<${t}>` + items.map(i => '<li>' + inline(i) + '</li>').join('') + `</${t}>`; items = []; };
  for (const l of s.split('\n')) {
    if (/^\s*```/.test(l)) {  // fenced code keeps its indentation
      if (code) { out += '<pre class="mdcode">' + esc(code.join('\n')) + '</pre>'; code = null; }
      else { flushP(); flushL(); code = []; }
    }
    else if (code) code.push(l);
    else if (/^\s*[-*] /.test(l)) { flushP(); if (ol) flushL(); ol = false; items.push(l.replace(/^\s*[-*] /, '')); }
    else if (/^\s*\d+[.)] /.test(l)) { flushP(); if (!ol) flushL(); ol = true; items.push(l.replace(/^\s*\d+[.)] /, '')); }
    else if (/^\s*-{3,}\s*$/.test(l)) { flushP(); flushL(); out += '<hr>'; }
    else if (!l.trim()) { flushP(); flushL(); }
    else if (items.length && /^\s{2,}/.test(l)) { items[items.length - 1] += ' ' + l.trim(); }
    else { flushL(); para.push(l); }
  }
  flushP(); flushL();
  return out;
}
const SEV_ORDER = ['important', 'question', 'pre-existing', 'nit', 'info'];
const PRI = ['must', 'should', 'question', 'nit'];
const askCls = p => p === 'question' ? 'ask-question' : p;
const askWord = p => p === 'question' ? 'ask' : p;  // "question" is a note severity; a to-do of that kind reads "ask"
const todoChip = (p, label) => `<span class="chip todo ${askCls(p)}" title="to do: ${esc(askWord(p))}">${esc(label || 'to do: ' + askWord(p))}</span>`;
const firstLine = h => { const l = h.lines.find(x => x[2] != null); return l ? l[2] : ''; };
const isOpen = a => a && !a.posted_url && a.text;
// a draft's ↗ copies the draft and opens its line on GitHub, ready to paste
const ghLink = a => a.link ? `<a class="gh" href="${esc(a.link)}" target="gh"${a.text ? ` data-text="${esc(a.text)}" title="copy the draft and open the line on GitHub"` : ' title="open on GitHub"'}>↗</a>` : '';
const toast = (() => {
  let el, t;
  return msg => {
    if (!el) { el = document.createElement('div'); el.id = 'toast'; el.setAttribute('role', 'status'); document.body.appendChild(el); }
    el.textContent = msg; el.classList.add('on');
    clearTimeout(t); t = setTimeout(() => el.classList.remove('on'), 2500);
  };
})();
document.addEventListener('click', e => {
  const b = e.target.closest('button.copy'); if (!b) return;
  e.stopPropagation();
  const t = b.dataset.text;
  const done = () => { const o = b.textContent; b.textContent = 'copied'; setTimeout(() => b.textContent = o, 1200); toast('Copied to clipboard'); };
  if (navigator.clipboard) navigator.clipboard.writeText(t).then(done, () => { prompt('Copy:', t); });
  else prompt('Copy:', t);
});
// move viewed marks and settings between browsers (e.g. Chrome -> the VS Code browser): each keeps its own storage
const xfer = (() => {
  const dump = () => {
    const o = {};
    try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k.startsWith('review')) o[k] = localStorage.getItem(k); } } catch (e) {}
    return JSON.stringify(o);
  };
  const dialog = (text, pasting) => {
    let d = document.getElementById('xfer');
    if (!d) { d = document.createElement('dialog'); d.id = 'xfer'; document.body.appendChild(d); }
    d.innerHTML = `<b>${pasting ? 'Paste the review state copied in the other browser' : 'Copy this text, then paste it in the other browser'}</b>
      <textarea spellcheck="false"></textarea><div class="loc err"></div>
      <div class="row"><button class="cancel">${pasting ? 'Cancel' : 'Close'}</button>${pasting ? '<button class="ok">Replace and reload</button>' : ''}</div>`;
    const ta = d.querySelector('textarea'); ta.value = text;
    d.querySelector('.cancel').onclick = () => d.close();
    if (pasting) d.querySelector('.ok').onclick = () => {
      let o;
      try { o = JSON.parse(ta.value); if (!o || typeof o !== 'object' || !Object.keys(o).every(k => k.startsWith('review'))) throw 0; }
      catch (e) { d.querySelector('.err').textContent = 'This is not a copied review state.'; return; }
      try {
        for (let i = localStorage.length - 1; i >= 0; i--) { const k = localStorage.key(i); if (k.startsWith('review')) localStorage.removeItem(k); }
        for (const [k, v] of Object.entries(o)) localStorage.setItem(k, v);
      } catch (e) { d.querySelector('.err').textContent = 'This browser does not allow saving.'; return; }
      location.reload();
    };
    d.showModal(); ta.focus(); if (!pasting) ta.select();
  };
  return {
    copy() {
      const t = dump();
      if (navigator.clipboard) navigator.clipboard.writeText(t).then(() => toast('Review state copied. In the other browser: ⋯ → Paste review state.'), () => dialog(t, false));
      else dialog(t, false);
    },
    paste() { dialog('', true); },
  };
})();
document.addEventListener('click', e => {
  const b = e.target.closest('button.copystate, button.pastestate'); if (!b) return;
  const m = b.closest('details'); if (m) m.open = false;
  b.classList.contains('copystate') ? xfer.copy() : xfer.paste();
});
const main = document.getElementById('main'), nav = document.getElementById('nav');

// ---- whitespace view and line counts ----
// like `git diff -w`: inside each run of changed lines, a removed and an added line that
// differ only in whitespace become one context line (LCS on whitespace-free text)
function wsLines(lines) {
  const out = [], norm = l => l[3].replace(/\s+/g, '');
  let i = 0;
  while (i < lines.length) {
    if (lines[i][0] !== '-' && lines[i][0] !== '+') { out.push(lines[i++]); continue; }
    const run = [];
    while (i < lines.length && (lines[i][0] === '-' || lines[i][0] === '+')) run.push(lines[i++]);
    const olds = run.filter(l => l[0] === '-'), news = run.filter(l => l[0] === '+');
    const n = olds.length, m = news.length, no = olds.map(norm), nn = news.map(norm);
    const dp = Array.from({length: n + 1}, () => new Array(m + 1).fill(0));
    for (let a = n - 1; a >= 0; a--) for (let b = m - 1; b >= 0; b--)
      dp[a][b] = no[a] === nn[b] ? dp[a + 1][b + 1] + 1 : Math.max(dp[a + 1][b], dp[a][b + 1]);
    let a = 0, b = 0;
    while (a < n || b < m) {
      if (a < n && b < m && no[a] === nn[b]) { out.push([' ', olds[a][1], news[b][2], news[b][3]]); a++; b++; }
      else if (b >= m || (a < n && dp[a + 1][b] >= dp[a][b + 1])) out.push(olds[a++]);
      else out.push(news[b++]);
    }
  }
  return out;
}
// ---- diff colors: Python syntax, and the changed part of a line that was edited (like GitHub's word diff) ----
const PYKW = new Set(('False None True and as assert async await break class continue def del elif else except finally for from global if '
  + 'import in is lambda nonlocal not or pass raise return try while with yield').split(' '));
const PYB = new Set('self cls print len range int float str bool list dict tuple set isinstance super min max'.split(' '));
// one line -> [[class, text], ...]; st.q is the open triple quote carried from earlier lines of the same side
function pyTokens(line, st) {
  const out = [];
  let i = 0;
  if (st.q) {
    const e = line.indexOf(st.q);
    if (e < 0) return [['tk-s', line]];
    out.push(['tk-s', line.slice(0, e + 3)]); i = e + 3; st.q = null;
  }
  const re = /(#.*$)|([rbfuRBFU]{0,2}(?:"{3}|'{3}))|([rbfRBF]{0,2}"(?:\\.|[^"\\])*"?|[rbfRBF]{0,2}'(?:\\.|[^'\\])*'?)|(@[\w.]+)|(\b\d[\w.]*)|([A-Za-z_]\w*)|(\s+|.)/gy;
  re.lastIndex = i;
  let m, prev = '';
  while (i < line.length && (m = re.exec(line))) {
    const [t, com, tq, str, dec, num, id] = m;
    if (com) out.push(['tk-c', t]);
    else if (tq) {  // may carry a string prefix (r, b, f, u) opens the same docstring
      const q = tq.slice(-3), e = line.indexOf(q, re.lastIndex);
      if (e < 0) { out.push(['tk-s', line.slice(m.index)]); st.q = q; break; }
      out.push(['tk-s', line.slice(m.index, e + 3)]); re.lastIndex = e + 3;
    }
    else if (str) out.push(['tk-s', t]);
    else if (dec) out.push(['tk-d', t]);
    else if (num) out.push(['tk-n', t]);
    else if (id) out.push([PYKW.has(id) ? 'tk-k' : PYB.has(id) ? 'tk-b' : (prev === 'def' || prev === 'class') ? 'tk-f' : '', t]);
    else out.push(['', t]);
    if (id) prev = id; else if (t.trim()) prev = '';
    i = re.lastIndex;
  }
  return out;
}
// tokens -> html; chars in rng = [start, end) also get the "changed" mark
function lineHtml(toks, rng) {
  let out = '', pos = 0;
  for (const [cls, t] of toks) {
    let i = 0;
    while (i < t.length) {
      const abs = pos + i;
      let end = t.length;
      if (rng && abs < rng[0]) end = Math.min(end, rng[0] - pos);
      else if (rng && abs < rng[1]) end = Math.min(end, rng[1] - pos);
      let h = esc(t.slice(i, end));
      if (cls) h = `<span class="${cls}">${h}</span>`;
      if (rng && abs >= rng[0] && abs < rng[1]) h = `<span class="x">${h}</span>`;
      out += h; i = end;
    }
    pos += t.length;
  }
  return out;
}
// in each run of removed then added lines, pair them in order and mark what differs between the common start and end
function changedRanges(lines) {
  const r = new Map();
  let i = 0;
  while (i < lines.length) {
    if (lines[i][0] !== '-') { i++; continue; }
    const ms = []; while (i < lines.length && lines[i][0] === '-') ms.push(i++);
    const ps = []; while (i < lines.length && lines[i][0] === '+') ps.push(i++);
    for (let k = 0; k < Math.min(ms.length, ps.length); k++) {
      const a = lines[ms[k]][3], b = lines[ps[k]][3];
      let pre = 0; while (pre < a.length && pre < b.length && a[pre] === b[pre]) pre++;
      let suf = 0; while (suf < a.length - pre && suf < b.length - pre && a[a.length - 1 - suf] === b[b.length - 1 - suf]) suf++;
      if (pre + suf < 3 || (pre + suf) < 0.25 * Math.min(a.length, b.length)) continue;  // mostly rewritten: mark nothing
      r.set(ms[k], [pre, a.length - suf]); r.set(ps[k], [pre, b.length - suf]);
    }
  }
  return r;
}
// a hunk can start inside a docstring: try each start state on the new side and keep the one
// that leaves the fewest code-looking lines colored as string
const CODE_LINE = /^\s*(if|elif|else|for|while|return|raise|def|class|import|from|with|try|except|assert)\b|^\s*[\w.\[\]]+\s*[+\-*\/]?=[^=]/;
function pyStart(lines) {
  let best = null, bestBad = Infinity;
  for (const q of [null, '"'.repeat(3), "'".repeat(3)]) {
    const st = {q}; let bad = 0;
    for (const [t, , , b] of lines) {
      if (t === '-') continue;
      const inStr = !!st.q, toks = pyTokens(b, st);
      if ((inStr || (toks.find(x => x[1].trim()) || [])[0] === 'tk-s') && CODE_LINE.test(b)) bad++;
    }
    if (bad < bestBad) { best = q; bestBad = bad; }
  }
  return best;
}
function rowsHtml(lines, py, split) {
  const q0 = py ? pyStart(lines) : null;
  const ranges = changedRanges(lines), so = {q: q0}, sn = {q: q0};
  const code = lines.map(([t, o, nn, b], i) => {
    let toks = [['', b]];
    if (py) {
      if (t === '-') toks = pyTokens(b, so);
      else { toks = pyTokens(b, sn); if (t === ' ') so.q = sn.q; }
    }
    return `<span class="sg">${t === ' ' ? ' ' : t}</span>${lineHtml(toks, ranges.get(i))}`;
  });
  if (!split) return lines.map(([t, o, nn], i) =>
    `<tr class="${t === '+' ? 'p' : t === '-' ? 'm' : ''}" data-n="${nn ?? ''}"><td class="ln">${o ?? ''}</td><td class="ln">${nn ?? ''}</td><td class="code">${code[i]}</td></tr>`).join('');
  // split: a context line on both sides; a run of removed lines next to the run of added lines after it
  const side = (i, c, r) => i == null ? `<td class="ln e${r}"></td><td class="code e"></td>`
    : `<td class="ln ${c}${r}">${lines[i][c === 'p' ? 2 : 1] ?? ''}</td><td class="code ${c}">${code[i]}</td>`;
  const out = ['<colgroup><col class="ln"><col><col class="ln"><col></colgroup>'];
  for (let i = 0; i < lines.length;) {
    if (lines[i][0] === ' ') {
      out.push(`<tr data-n="${lines[i][2] ?? ''}">${side(i, '', '')}<td class="ln r">${lines[i][2] ?? ''}</td><td class="code">${code[i]}</td></tr>`);
      i++; continue;
    }
    const ms = []; while (i < lines.length && lines[i][0] === '-') ms.push(i++);
    const ps = []; while (i < lines.length && lines[i][0] === '+') ps.push(i++);
    for (let k = 0; k < Math.max(ms.length, ps.length); k++)
      out.push(`<tr data-n="${ps[k] != null ? lines[ps[k]][2] ?? '' : ''}">${side(ms[k], 'm', '')}${side(ps[k], 'p', ' r')}</tr>`);
  }
  return out.join('');
}
let SPLIT = !!store.get('review:split', true);
function paintDiff(el, hideWS) {
  el._hideWS = hideWS;
  const lines = hideWS ? (el._ws = el._ws || el._h.ws || wsLines(el._h.lines)) : el._h.lines;
  const tb = el.querySelector('table'), split = SPLIT && lines.some(l => l[0] === '-');  // a hunk that only adds stays inline
  tb.classList.toggle('split', split);
  tb.innerHTML = rowsHtml(lines, el._py, split);
  el._cnt = {a: lines.filter(l => l[0] === '+').length, d: lines.filter(l => l[0] === '-').length};
  el.classList.toggle('wsonly', hideWS && !el._cnt.a && !el._cnt.d);
}
// GitHub-style: "+a −d" and five squares
const dstat = ({a, d}) => {
  const tot = a + d, fill = Math.min(5, tot), g = tot ? Math.round(a / tot * fill) : 0;
  const sq = [...Array(g).fill('a'), ...Array(fill - g).fill('d'), ...Array(5 - fill).fill('')];
  return `<span class="a">+${a}</span> <span class="d">−${d}</span><span class="dstat">${sq.map(c => `<i class="${c}"></i>`).join('')}</span>`;
};
const sumCnt = els => els.reduce((s, el) => ({a: s.a + el._cnt.a, d: s.d + el._cnt.d}), {a: 0, d: 0});

const ALL = [];   // every hunk element, in page order
const PR = {};    // prefix -> controller
const PRLIST = [];

function mountPR(D) {
  const P = D.prefix, IDP = 'p' + P + '-';
  const KEY = 'review:' + D.title;
  let state = store.get(KEY, {});
  const save = () => store.set(KEY, state);
  { // hunks the reviewer already read for their comments: check each once, never re-check after an uncheck
    const seeded = store.get(KEY + ':seeded', {});
    (D.seed_viewed || []).forEach(k => { if (!seeded[k]) { state[k] = 1; seeded[k] = 1; } });
    save(); store.set(KEY + ':seeded', seeded);
  }
  // "#N" in a note -> hunk N of the same file; "foo.py hunk #N" -> hunk N of foo.py (this PR)
  const GNUM = D.gmap;
  const PATHS = [...new Set(Object.keys(GNUM).map(k => k.replace(/#\d+$/, '')))];
  const hunkAnchor = (path, k) => IDP + 'h-' + (path + '#' + k).replace(/[^A-Za-z0-9]/g, '_');
  const hunkHref = (path, k) => SINGLE ? `${GNUM[path + '#' + k]}.html` : '#' + hunkAnchor(path, k);
  function linkHunks(html, f) {
    const saved = [];
    const keep = s => { saved.push(s); return '\u0000' + (saved.length - 1) + '\u0000'; };
    html = html.replace(/(<code>)?([\w./-]+\.py)(<\/code>)?(\s+hunks?\s+)#(\d{1,3})\b/g, (m, c1, name, c2, mid, num) => {
      const gp = PATHS.find(x => x === name || x.endsWith('/' + name));
      if (!gp || !((gp + '#' + num) in GNUM)) return m;
      return keep(`${c1 || ''}${name}${c2 || ''}${mid}<a class="hlink" href="${hunkHref(gp, +num)}">#${GNUM[gp + '#' + num]}</a>`);
    });
    if (f) html = html.replace(/(^|[^\w&\/])#(\d{1,3})\b/g, (m, pre, num) =>
      (f.path + '#' + num) in GNUM ? `${pre}<a class="hlink" href="${hunkHref(f.path, +num)}">#${GNUM[f.path + '#' + num]}</a>` : m);
    return html.replace(/\u0000(\d+)\u0000/g, (m, i) => saved[+i]);
  }
  // the hunk's first line on GitHub (new side; old side for a deletion-only hunk)
  const ghHunk = (f, h) => {
    if (!D.url || !f.anchor || !h.lines.length) return '';
    const [, o, nn] = h.lines[0];
    const at = nn != null ? 'R' + nn : 'L' + o;
    return `<a class="ghh" href="${esc(D.url)}/files#diff-${f.anchor}${at}" target="gh" title="open this hunk on GitHub (line ${at.slice(1)})">↗</a>`;
  };
  function askBox(a, f, bare) {  // bare: under a To do row that already shows the chip and title
    if (a.posted_url)
      return `<div class="posted">✓ posted: ${esc(a.title || 'comment')} <a class="gh" href="${esc(a.posted_url)}" target="gh" title="open on GitHub">↗</a></div>`;
    return `<div class="ask ${askCls(a.priority)}"><div class="askhead">${bare ? '' : `${todoChip(a.priority)}
      <span>${esc(a.title || '')}</span>`}${ghLink(a)}<button class="copy" data-text="${esc(a.text)}">copy comment</button></div>${linkHunks(md(a.text), f)}</div>`;
  }

  // section + nav group, each collapsible; the open/closed choice is remembered
  const COLKEY = 'review:collapsed:' + P;
  const sec = document.createElement('section'); sec.className = 'pr'; sec.id = 'pr' + P;
  sec.innerHTML = `<div class="prhead"><h2>${D.url ? `<a href="${esc(D.url)}" target="gh">${esc(D.title)}</a>` : esc(D.title)}</h2>
    <span class="prstat"></span><div class="bar"><div class="prprog"></div></div><span class="prprogtxt loc"></span><span class="prtodo"></span>
    <span class="prctl"><span class="seg" title="which hunks to show">
        <label><input type="radio" name="f${P}" value="" checked>All</label>
        <label><input type="radio" name="f${P}" value="hideviewed">Unviewed</label>
        <label><input type="radio" name="f${P}" value="onlyask">To do</label>
        <label><input type="radio" name="f${P}" value="onlyflag">Flagged</label>
        <label class="chgctl" style="display:none"><input type="radio" name="f${P}" value="onlychg">Changed</label></span>
      <label title="like GitHub's 'Hide whitespace': a removed and an added line that differ only in whitespace show as one unchanged line, and the line counts skip them"><input type="checkbox" class="hidews"> hide whitespace</label>
      <label title="jump to hunk N of this PR">go to #<input class="goto" type="text"></label>
      <details class="more"><summary title="more actions">⋯</summary><div class="menu">
        <button class="trivbtn" title="mark every hunk tagged trivial as viewed">Mark trivial hunks viewed</button>
        <button class="resetbtn" title="clear this PR's viewed marks">Clear viewed marks…</button></div></details></span></div><div class="prbody"></div>`;
  const head = sec.querySelector('.prhead');
  { // the file headers stick right under this PR's header
    const setHH = () => sec.style.setProperty('--hh', head.offsetHeight + 'px');
    setHH(); if (window.ResizeObserver) new ResizeObserver(setHH).observe(head);
  }
  const FILTERS = ['hideviewed', 'onlyflag', 'onlyask', 'onlychg'];
  sec.querySelectorAll('.seg input').forEach(c => c.addEventListener('change', () => {
    FILTERS.forEach(f => sec.classList.remove(f)); if (c.value) sec.classList.add(c.value);
  }));
  let hideWS = !!store.get('review:hidews:' + P, store.get('review:hidews', false));
  sec.querySelector('.hidews').checked = hideWS;
  sec.querySelector('.hidews').addEventListener('change', e => {
    hideWS = e.target.checked; store.set('review:hidews:' + P, hideWS);
    hunkEls.forEach(el => paintDiff(el, hideWS)); refreshCounts();
  });
  sec.querySelector('.goto').addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const ok = gotoHunk(P + ':' + e.target.value);
    e.target.style.outline = ok ? '' : '2px solid var(--imp)'; if (ok) e.target.blur();
  });
  sec.querySelector('.trivbtn').addEventListener('click', () => api.markTrivial());
  sec.querySelector('.resetbtn').addEventListener('click', () => { if (confirm('Clear all viewed marks of ' + (D.label || D.title) + '?')) api.reset(); });
  const body = sec.querySelector('.prbody');
  main.appendChild(sec);
  const ng = document.createElement('div'); ng.className = 'navgrp';
  ng.innerHTML = `<a class="navgrp-h" href="#pr${P}" title="${esc(D.title)}"><span>${esc(D.label || D.title)}</span><span class="cnt"></span></a><div class="navfiles"></div>`;
  nav.appendChild(ng);
  const navfiles = ng.querySelector('.navfiles');
  const isCollapsed = () => sec.classList.contains('collapsed');
  const setCollapsed = (c, remember = true) => {
    sec.classList.toggle('collapsed', c); ng.classList.toggle('collapsed', c);
    if (remember) store.set(COLKEY, c);
    refreshTotals();
  };
  setCollapsed(!SINGLE && store.get(COLKEY, !!D.collapsed), false);
  head.addEventListener('click', e => { if (!e.target.closest('a, input, label, button, details')) setCollapsed(!isCollapsed()); });
  ng.querySelector('.navgrp-h').addEventListener('click', () => { if (isCollapsed()) setCollapsed(false); });

  const hunkEls = [], ASKS = [], CHG = [];
  // files are folded by default; the ones the reviewer opened are remembered
  const OPENKEY = KEY + ':open';
  const openFiles = store.get(OPENKEY, {});
  const setOpen = (fel, o) => {
    fel.classList.toggle('fopen', o);
    if (o) openFiles[fel.dataset.path] = 1; else delete openFiles[fel.dataset.path];
    if (!SINGLE) store.set(OPENKEY, openFiles);
  };
  const panel = document.createElement('div'); panel.className = 'panel'; body.appendChild(panel);  // filled after the files
  D.files.forEach((f, fi) => {
    const fn = D.notes.files[f.path] || {};
    const sevs = f.hunks.map(h => (D.notes.hunks[h.id] || {}).severity).filter(Boolean);
    const top = SEV_ORDER.find(s => sevs.includes(s) && (s === 'important' || s === 'question'));
    const fel = document.createElement('section');
    fel.className = 'file'; fel.id = IDP + 'f' + fi; fel.dataset.path = f.path;
    fel.innerHTML = `<div class="fhead"><span class="path">${esc(f.path)}</span><span class="stat"></span>
      ${top ? `<span class="chip ${top}">${top}</span>` : ''}<span class="fprog" style="color:var(--muted);font-size:12px"></span>
      <span class="fview"><span>Viewed</span><input type="checkbox" class="fchk" title="mark the whole file viewed"></span></div>
      ${fn.summary || fn.note ? `<div class="fnote"><b>${esc(fn.summary || '')}</b>${linkHunks(md(fn.note), f)}</div>` : ''}
      <div class="hunks"></div>`;
    const hc = fel.querySelector('.hunks');
    { // hunk bars stick right under this file's header
      const fh = fel.querySelector('.fhead'), setFH = () => fel.style.setProperty('--fh', fh.offsetHeight + 'px');
      setFH(); if (window.ResizeObserver) new ResizeObserver(setFH).observe(fh);
    }
    f.hunks.forEach((h, hi) => {
      const n = D.notes.hunks[h.id] || {};
      const sev = n.severity || '';
      const g = GNUM[h.id];
      const el = document.createElement('div');
      el.className = 'hunk' + (sev === 'important' || sev === 'question' ? ' flag' : '');
      el.id = hunkAnchor(f.path, +h.id.split('#').pop());  // the hunk's own number: hunks may be reordered
      el.dataset.g = g; el.dataset.pr = P; el._h = h; el._py = /\.pyi?$/.test(f.path);
      if (isOpen(n.ask)) { el.dataset.askline = n.ask.line || ''; el.classList.add('hasask'); fel.classList.add('hasask'); ASKS.push({n, h, f, el}); }
      if (n.change === 'changed' || n.change === 'new') { el.classList.add('chg'); fel.classList.add('chg'); CHG.push({n, h, f, el}); }
      if (n.prev && (n.change === 'unchanged' || n.change === 'moved')) el.dataset.prev = n.prev.id + '@' + n.prev.hash;
      el.dataset.id = h.id; el.dataset.hash = h.hash; el.dataset.trivial = n.trivial ? 1 : 0;
      const since = D.since ? ' since ' + esc(D.since) : '';
      el.innerHTML = `<div class="hbar"><input type="checkbox" class="hchk" title="viewed">${SINGLE || !D.pages_rel ? `<span class="hnum">#${g}</span>` : `<a class="hnum" href="${D.pages_rel}/${g}.html" title="open this hunk as its own page">#${g}</a>`}${n.change === 'changed' ? `<span class="chip chg" title="this hunk changed since the last review; the note was updated">changed${since}</span>` : n.change === 'new' ? `<span class="chip newh">new${since}</span>` : ''}
          ${isOpen(n.ask) ? todoChip(n.ask.priority) : n.ask && n.ask.posted_url ? '<span class="chip st">posted</span>' : ''}${sev ? `<span class="chip ${sev}">${sev}</span>` : ''}${n.trivial ? '<span class="chip trivial">trivial</span>' : ''}
          <span class="hdr">${esc(n.summary ? n.summary : h.header)}</span>${ghHunk(f, h)}</div>
        <div class="diff"><div style="color:var(--muted);font-size:11px;padding:2px 6px" class="code">${esc(h.header)}</div><table></table></div>
        <div class="side">${n.ask ? askBox(n.ask, f) : ''}${n.summary || n.note ? `<div class="sum">${esc(n.summary || '')}</div>${linkHunks(md(n.note), f)}` : '<span class="empty">no note</span>'}</div>`;
      paintDiff(el, hideWS);
      const chk = el.querySelector('.hchk');
      chk.addEventListener('click', e => e.stopPropagation());
      chk.addEventListener('change', () => setHunk(el, chk.checked));
      el.querySelector('.hbar').addEventListener('click', e => {
        if (e.target.closest('a, input')) return;
        // folding only hides or shows the hunk; the checkbox alone marks it viewed
        if (el.classList.contains('viewed')) el.classList.toggle('peek');
        else el.classList.toggle('folded');
      });
      hc.appendChild(el); hunkEls.push(el); ALL.push(el);
    });
    if (SINGLE || openFiles[f.path]) fel.classList.add('fopen');
    fel.querySelector('.fhead').addEventListener('click', e => {
      if (e.target.closest('label, a, input, button')) return;
      setOpen(fel, !fel.classList.contains('fopen'));
    });
    fel.querySelector('.fchk').addEventListener('change', e => {
      const hs = fel.querySelectorAll('.hunk'), snap = fsnap[f.path];
      if (e.target.checked) hs.forEach(el => setHunk(el, true, true));
      else if (snap) hs.forEach(el => setHunk(el, snap.includes(sk(el)), true));  // undo: back to the state before the file was completed
      else hs.forEach(el => setHunk(el, false, true));  // no recorded earlier state
      refresh();
    });
    if (f.section) {  // reading-order section from the order file
      const sh = document.createElement('div'); sh.className = 'osec'; sh.textContent = f.section; body.appendChild(sh);
      const nh = document.createElement('div'); nh.className = 'navsec'; nh.textContent = f.section.replace(/^\d+\.\s*/, '').split(/[:—(]/)[0]; nh.title = f.section; navfiles.appendChild(nh);
    }
    body.appendChild(fel);
    const a = document.createElement('a');
    a.href = '#' + fel.id; a.dataset.fi = fi;
    const base = f.path.split('/').pop(), short = base.length > 24 ? base.slice(0, 10) + '…' + base.slice(-13) : base;
    a.innerHTML = `<span class="dot ${top || ''}" title="${top ? 'has ' + top + ' notes' : ''}">●</span><span>${esc(short)}</span><span class="cnt" title="hunks viewed / hunks"></span>`;
    a.title = f.path; navfiles.appendChild(a);
  });

  // status panel: Overview / To do / Changed / Posted share one box with tabs, so the code starts high on the page
  let setTab = () => {};
  {
    const rows = [];
    const gh = u => u ? ` <a class="gh" href="${esc(u)}" target="gh" title="open on GitHub">↗</a>` : '';
    const base = path => path.split('/').pop();
    const todo = (a, href, where) => `${todoChip(a.priority, askWord(a.priority))} <a href="${href}" data-todo><b>${esc(a.title)}</b></a> <span class="loc">${where}</span> ${ghLink(a)}`;
    const POSTED = D.posted || [];
    const st = p => (p.status && p.status.state) || 'open';
    // threads that need you: a drafted reply to post, or an author reply nobody has triaged yet
    const replies = POSTED.filter(p => p.status && p.status.reply && !p.status.reply_posted)
      .map(p => ({priority: p.status.priority || 'question', title: 'Reply on ' + p.where, text: p.status.reply, link: p.url, why: p.status.why}));
    const untriaged = POSTED.filter(p => p.author_replied && !p.status);
    const addressed = POSTED.filter(p => st(p) === 'addressed' || st(p) === 'answered');
    const waiting = POSTED.filter(p => st(p) === 'open' && !(p.status && p.status.reply && !p.status.reply_posted) && !untriaged.includes(p));
    const prAsks = (D.pr_asks || []).filter(isOpen).concat(replies);
    // PR-level comments and thread replies have no hunk, so their text sits right under their row
    prAsks.forEach((a, i) => rows.push({p: a.priority, html: todo(a, '#' + IDP + 'prask' + i, a.title.startsWith('Reply on') ? 'thread reply' : 'PR conversation'),
      detail: `<div id="${IDP}prask${i}" class="praskitem">${askBox(a, null, true)}${a.why ? `<div class="loc">→ ${esc(a.why)}</div>` : ''}</div>`}));
    untriaged.forEach(p => rows.push({p: 'question', html: `${todoChip('question', 'read')} <b>Author replied on ${esc(p.where)}</b>${gh(p.url)} <span class="loc">${esc(p.text.slice(0, 60))}…</span>`}));
    ASKS.forEach(({n, h, f, el}) => rows.push({p: n.ask.priority, html: todo(n.ask,
      SINGLE ? GNUM[h.id] + '.html' : '#' + el.id, `${esc(base(f.path))}:${n.ask.line || firstLine(h)}`)}));
    rows.sort((a, b) => PRI.indexOf(a.p) - PRI.indexOf(b.p));
    const tl = list => list.map(p => `<span title="${esc(p.text)}">${esc(p.where)}</span>${gh(p.url)}`).join(', ');
    const tabs = [];
    if (D.overview) tabs.push(['overview', 'Overview', `<div class="overview">${linkHunks(md(D.overview), null)}</div>`]);
    if (rows.length || waiting.length || addressed.length) tabs.push(['todo', `To do <b>${rows.length}</b>`,
      (rows.length ? `<ol class="todolist">${rows.map(r => `<li>${r.html}${r.detail || ''}</li>`).join('')}</ol>` : '<p class="loc">Nothing to post.</p>')
      + (waiting.length ? `<details class="tlinks"><summary>Waiting on the author: ${waiting.length} threads</summary><div>${tl(waiting)}</div></details>` : '')
      + (addressed.length ? `<details class="tlinks"><summary>Addressed, for the author to resolve: ${addressed.length} threads</summary><div>${tl(addressed)}</div></details>` : '')]);
    if (CHG.length) {
      sec.querySelector('.chgctl').style.display = '';
      tabs.push(['chg', `Changed since ${D.since ? esc(D.since) : 'last review'} <b>${CHG.length}</b>`, `<ol>${CHG.map(({n, h, f, el}) =>
        `<li><span class="chip ${n.change === 'new' ? 'newh' : 'chg'}">${esc(n.change)}</span> <a href="#${el.id}"><b>${esc(n.summary || h.header)}</b></a> <span class="loc">${esc(base(f.path))}:${firstLine(h)}</span></li>`).join('')}</ol>`]);
    }
    if (POSTED.length && !SINGLE) {
      const nDone = POSTED.filter(p => st(p) === 'addressed').length;
      const stChip = s => !s ? '' : s.state === 'addressed' ? '<span class="chip done">addressed</span> '
        : s.state === 'answered' ? '<span class="chip done">answered</span> ' : '<span class="chip st">open</span> ';
      tabs.push(['posted', `Posted <b>${POSTED.length}</b>`, (nDone ? `<p class="loc">${nDone} addressed. Only the author or a maintainer can resolve them.</p>` : '') + `<ol>${POSTED.map(p =>
        `<li>${stChip(p.status)}${esc(p.where)}${gh(p.url)} — ${esc(p.text)}${p.replies ? ` <span class="loc">(+${p.replies} ${p.replies > 1 ? 'replies' : 'reply'})</span>` : ''}${p.author_replied ? ' <span class="chip important">author replied</span>' : ''}${p.status && p.status.why ? `<div class="loc">→ ${esc(p.status.why)}</div>` : ''}</li>`).join('')}</ol>`]);
    }
    if (rows.length) sec.querySelector('.prtodo').innerHTML = `<button class="todochip" title="show the To do list">${todoChip('should', rows.length + ' to do')}</button>`;
    if (!tabs.length) panel.remove();
    else {
      panel.innerHTML = `<div class="tabs">${tabs.map(([k, l]) => `<button class="tab" data-tab="${k}">${l}</button>`).join('')}<span class="tabhint loc">click the open tab to fold</span></div>`
        + tabs.map(([k, , h]) => `<div class="pane" data-pane="${k}" hidden>${h}</div>`).join('');
      const TABKEY = 'review:tab:' + P, keys = tabs.map(t => t[0]);
      setTab = (k, remember = true) => {
        if (k && !keys.includes(k)) k = keys[0];
        panel.dataset.tab = k || '';
        panel.querySelectorAll('.tab').forEach(b => b.classList.toggle('on', b.dataset.tab === k));
        panel.querySelectorAll('.pane').forEach(x => { x.hidden = x.dataset.pane !== k; });
        if (remember) store.set(TABKEY, k || '');
      };
      setTab(store.get(TABKEY, keys.includes(D.default_tab) ? D.default_tab : rows.length ? 'todo' : keys[0]), false);
      panel.querySelector('.tabs').addEventListener('click', e => {
        const b = e.target.closest('.tab'); if (b) setTab(panel.dataset.tab === b.dataset.tab ? '' : b.dataset.tab);
      });
      const tc = sec.querySelector('.todochip');
      if (tc) tc.addEventListener('click', () => {
        if (isCollapsed()) setCollapsed(false);
        setTab('todo'); window.scrollTo({top: panel.getBoundingClientRect().top + scrollY - head.offsetHeight - 6});
      });
    }
  }

  const sk = el => el.dataset.id + '@' + el.dataset.hash;  // content change => unviewed again
  function setHunk(el, v, noRefresh) {
    if (v) state[sk(el)] = 1; else delete state[sk(el)];
    el.classList.toggle('viewed', v); el.querySelector('.hchk').checked = v;
    if (v) el.classList.remove('peek');
    save(); if (!noRefresh) refresh();
  }
  // fsnap[path]: the file's viewed hunks just before it became fully viewed, so unchecking the
  // file restores them. Recorded on every transition to fully viewed, whatever caused it.
  const FSNAPKEY = KEY + ':fsnap';
  const fsnap = store.get(FSNAPKEY, {});
  let lastViewed = null;  // path -> viewed hunk keys at the previous refresh
  function refresh() {
    let done = 0;
    const now = {};
    body.querySelectorAll('.file').forEach(fel => {
      const hs = [...fel.querySelectorAll('.hunk')], vs = hs.filter(h => h.classList.contains('viewed')), d = vs.length;
      done += d;
      const all = hs.length > 0 && d === hs.length, path = fel.dataset.path;
      now[path] = vs.map(sk);
      if (lastViewed && !SINGLE) {  // a one-hunk page must not touch the full page's snapshots
        const was = lastViewed[path] || [];
        if (all && was.length < hs.length) { fsnap[path] = was; setOpen(fel, false); }  // just completed: fold it, like GitHub
        else if (!all) delete fsnap[path];
      }
      fel.classList.toggle('fviewed', all); fel.querySelector('.fchk').checked = all;
      fel.querySelector('.fprog').textContent = `${d}/${hs.length} hunks`;
      const a = navfiles.querySelector(`[href="#${fel.id}"]`);
      a.classList.toggle('done', all); a.querySelector('.cnt').textContent = `${d}/${hs.length}`;
    });
    lastViewed = now;
    if (!SINGLE) store.set(FSNAPKEY, fsnap);
    sec.querySelector('.prprog').style.width = (100 * done / Math.max(1, hunkEls.length)) + '%';
    sec.querySelector('.prprogtxt').textContent = `${done}/${hunkEls.length} hunks viewed`;
    ng.querySelector('.cnt').textContent = `${done}/${hunkEls.length}`;
    refreshTotals();
  }
  function refreshCounts() {  // line counts follow the whitespace toggle
    body.querySelectorAll('.file').forEach(fel => { fel.querySelector('.stat').innerHTML = dstat(sumCnt([...fel.querySelectorAll('.hunk')])); });
    sec.querySelector('.prstat').innerHTML = dstat(sumCnt(hunkEls));
  }
  hunkEls.forEach(el => {
    let v = !!state[sk(el)];
    if (!v && el.dataset.prev && state[el.dataset.prev]) { v = true; state[sk(el)] = 1; }  // same content as a hunk viewed before
    const same = el._h.same_as;  // identical hunk of the PR this one is stacked on, viewed there
    if (!v && same && PR[same[0]] && PR[same[0]].isViewed(same[1])) { v = true; state[sk(el)] = 1; }
    el.classList.toggle('viewed', v); el.querySelector('.hchk').checked = v;
  });
  save();
  const api = {P, D, sec, hunkEls, setHunk, refresh, refreshCounts, isCollapsed, setCollapsed, setOpen, setTab: k => setTab(k),
    isViewed: k => !!state[k],
    markTrivial() { hunkEls.filter(el => el.dataset.trivial === '1').forEach(el => setHunk(el, true, true)); refresh(); },
    reset() { state = {}; save(); hunkEls.forEach(el => setHunk(el, false, true)); refresh(); }};
  PR[P] = api; PRLIST.push(api);
  refreshCounts(); refresh();
  return api;
}
function refreshTotals() {}  // progress is per PR, in each PR's header
if (!SINGLE) nav.insertAdjacentHTML('beforeend', '<div class="legend"><span class="dot important">●</span> important <span class="dot question">●</span> question · n/m = hunks viewed</div>');
ROOT.prs.forEach(mountPR);

const openPRs = () => PRLIST.filter(p => !p.isCollapsed());
{ // file list shown or hidden, remembered separately from the viewed state
  const old = ROOT.prs[0] && store.get('review:' + ROOT.prs[0].title + ':nonav', null);
  if (store.get('review:nonav', old === '1' || old === 1 || old === true)) document.body.classList.add('nonav');
}
// show a hunk even if a filter of its PR would hide it
function clearFilters(sec) {
  ['hideviewed', 'onlyflag', 'onlyask', 'onlychg'].forEach(f => sec.classList.remove(f));
  const all = sec.querySelector('.seg input[value=""]'); if (all) all.checked = true;
}
let cur = -1;
const prOf = el => PR[el.dataset.pr];
function setHunkParam(el) {
  try { const u = new URL(location.href); u.searchParams.set('hunk', el.dataset.pr + ':' + el.dataset.g); u.hash = ''; history.replaceState(null, '', u); } catch (e) {}
}
// would this hunk show if its file were open? (its PR is open and its PR's filters keep it)
const candidate = el => {
  const sec = el.closest('.pr');
  return !sec.classList.contains('collapsed') && !el.classList.contains('viewed')
    && !(sec.classList.contains('onlyflag') && !el.classList.contains('flag'))
    && !(sec.classList.contains('onlyask') && !el.classList.contains('hasask'))
    && !(sec.classList.contains('onlychg') && !el.classList.contains('chg'));
};
function go(dir) {
  if (SINGLE) { const t = dir > 0 ? SINGLE.next : SINGLE.prev; if (t) location.href = t + '.html'; return; }
  let at = cur;  // without a focused hunk, start at the screen position (a folded hunk counts at its file header)
  if (at < 0) {
    const anchor = el => el.offsetParent !== null ? el : el.closest('.file').querySelector('.fhead');
    const i = ALL.findIndex(el => { const a = anchor(el); return a.offsetParent !== null && a.getBoundingClientRect().top >= HH(el) - 1; });
    at = i < 0 ? ALL.length : (dir > 0 ? i - 1 : i);
  }
  const order = dir > 0 ? ALL.slice(at + 1) : ALL.slice(0, Math.max(0, at)).reverse();
  const target = order.find(candidate) || (dir > 0 ? ALL.find(candidate) : [...ALL].reverse().find(candidate));
  if (!target) return;
  ALL.forEach(el => el.classList.remove('focus')); reveal(target); target.classList.add('focus'); cur = ALL.indexOf(target);
  setHunkParam(target);
  window.scrollTo({top: target.getBoundingClientRect().top + window.scrollY - HH(target), behavior: 'smooth'});
}
function reveal(el) {
  const p = prOf(el); if (p && p.isCollapsed()) p.setCollapsed(false);
  el.classList.add('peek'); el.classList.remove('folded'); if (p) p.setOpen(el.closest('.file'), true);
}
// in-page links (To do list, notes, file list): open the target first, so a viewed hunk or a closed PR does not hide it
// a To do link: open the hunk, put its comment right under the sticky bars, and flash the comment and its code line
function flash(x) { if (!x) return; x.classList.remove('flash'); void x.offsetWidth; x.classList.add('flash'); }
function focusTodo(t) {
  const s = t.closest('.pr'), p = s && PR[s.id.slice(2)];
  if (t.classList.contains('hunk')) reveal(t); else if (p && p.isCollapsed()) p.setCollapsed(false);
  const pane = t.closest('.pane'); if (pane && pane.hidden && p) p.setTab(pane.dataset.pane);
  const box = t.querySelector('.ask') || t;
  const row = t.dataset && t.dataset.askline ? t.querySelector(`tr[data-n="${t.dataset.askline}"]`) : null;
  document.querySelectorAll('tr.askline').forEach(r => r.classList.remove('askline'));
  if (row) row.classList.add('askline');
  const go = () => {
    const hb = t.classList.contains('hunk') ? t.querySelector('.hbar').offsetHeight : 0;
    window.scrollTo({top: box.getBoundingClientRect().top + window.scrollY - HH(t) - hb - 10});
  };
  requestAnimationFrame(() => requestAnimationFrame(go)); setTimeout(go, 250);
  flash(box); flash(row);
}
document.addEventListener('click', e => {
  const a = e.target.closest('a[href^="#"]'); if (!a) return;
  const t = document.getElementById(a.getAttribute('href').slice(1)); if (!t) return;
  if (a.hasAttribute('data-todo')) { e.preventDefault(); history.replaceState(null, '', a.getAttribute('href')); focusTodo(t); return; }
  if (t.classList.contains('hunk')) { reveal(t); return; }
  const s = t.closest('.pr'), p = s && PR[s.id.slice(2)]; if (!p) return;
  if (p.isCollapsed()) p.setCollapsed(false);
  if (t.classList.contains('file')) p.setOpen(t, true);  // the file list opens the file it jumps to
}, true);
// "N" = hunk N of the first open PR; "101:N" or "101#N" = hunk N of that PR
function findHunk(spec) {
  const m = /^\s*(?:(\w+)\s*[:#]\s*)?#?(\d+)\s*$/.exec(String(spec || ''));
  if (!m) return null;
  const p = m[1] ? PR[m[1]] : (openPRs()[0] || PRLIST[0]);
  return p ? p.hunkEls.find(el => el.dataset.g === String(+m[2])) || null : null;
}
function gotoHunk(spec) {
  const t = findHunk(spec);
  if (!t) return false;
  clearFilters(t.closest('.pr'));
  ALL.forEach(el => el.classList.remove('focus'));
  reveal(t); t.classList.add('focus'); cur = ALL.indexOf(t);
  t.scrollIntoView({block: 'start'}); setHunkParam(t);
  return true;
}
{
  const g = new URLSearchParams(location.search).get('hunk');
  const target = g && !SINGLE ? findHunk(/[:#]/.test(g) ? g : (PRLIST[0] ? PRLIST[0].P + ':' + g : g)) : null;
  if (g && !SINGLE) status(target ? `?hunk=${g}: found` : `?hunk=${g}: no such hunk`);
  if (target) {
    // show it even if it is viewed or a filter would hide it
    clearFilters(target.closest('.pr'));
    reveal(target); target.classList.add('focus'); cur = ALL.indexOf(target);
    // Chrome restores the old scroll position on reload; switch that off and jump again after load
    try { history.scrollRestoration = 'manual'; } catch (e) {}
    let userMoved = false;
    ['wheel', 'keydown', 'mousedown', 'touchstart'].forEach(ev =>
      window.addEventListener(ev, () => { userMoved = true; }, {once: true, passive: true}));
    const jump = () => { if (!userMoved) target.scrollIntoView({block: 'start'}); };
    [0, 50, 150, 300, 600, 1000, 1500].forEach(t => setTimeout(jump, t));
    window.addEventListener('load', jump);
    window.addEventListener('pageshow', jump);
  }
}
if (SINGLE) {
  document.body.classList.add('single', 'nonav');
  const s = SINGLE, P = ROOT.prs[0].prefix, link = (n, t) => n ? `<a href="${n}.html">${t}</a>` : `<span style="color:var(--muted)">${t}</span>`;
  main.insertAdjacentHTML('afterbegin', `<div class="pager">${link(s.prev, '← #' + (s.prev || ''))}
    <b>${esc(ROOT.prs[0].label || '')} hunk #${s.g} of ${s.total}</b> ${link(s.next, '#' + (s.next || '') + ' →')}
    <a href="${esc(s.full)}?hunk=${P}:${s.g}">full page</a> <span style="color:var(--muted)">keys: j / k = next / previous hunk</span></div>`);
  ALL.forEach(el => el.classList.add('peek'));
}
// Tab / Shift+Tab from a viewed checkbox goes to the next / previous shown viewed checkbox;
// checking one with Space moves on to the next, so Space, Space, ... walks the review
function focusBox(from, dir) {
  const boxes = [...document.querySelectorAll('input.hchk, input.fchk')].filter(c => c.offsetParent !== null || c === from);
  const next = boxes[boxes.indexOf(from) + dir];
  if (!next) return false;
  next.focus({preventScroll: true});
  const box = next.closest('.hunk') || next.closest('.file');  // keep it below the sticky headers
  const top = box.getBoundingClientRect().top, h = next.matches('.hchk') ? HH(box) : box.closest('.pr').querySelector('.prhead').offsetHeight;
  if (top < h || top > innerHeight - 40) window.scrollTo({top: top + scrollY - h});
  return true;
}
// every GitHub link reuses one tab: open it once, then just navigate it and bring it forward
document.addEventListener('click', e => {
  const a = e.target.closest('a[href^="https://github.com/"]');
  if (!a || e.button || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
  e.preventDefault();
  if (a.dataset.text && navigator.clipboard) navigator.clipboard.writeText(a.dataset.text).then(() => {
    a.textContent = '✓ copied'; setTimeout(() => a.textContent = '↗', 1500);
    toast('Draft copied to clipboard. On GitHub, click + on the line and paste.');
  }, () => toast('Could not copy the draft. Use "copy comment".'));
  const w = window.open(a.href, 'gh');
  if (w) w.focus();
});
document.addEventListener('keydown', e => {
  if (e.key !== 'Tab' || e.metaKey || e.ctrlKey || e.altKey || !e.target.matches('input.hchk, input.fchk')) return;
  if (focusBox(e.target, e.shiftKey ? -1 : 1)) e.preventDefault();  // past the last one: normal Tab
}, true);
let spaceBox = null;  // the checkbox a Space press is toggling (mouse clicks do not move the focus)
document.addEventListener('keydown', e => { spaceBox = e.key === ' ' && e.target.matches('input.hchk, input.fchk') ? e.target : null; }, true);
document.addEventListener('change', e => {
  const c = e.target;
  if (c !== spaceBox) return;
  spaceBox = null;
  if (c.checked) setTimeout(() => focusBox(c, 1), 0);  // after the hunk or file has folded
}, true);
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === 'j') go(1); else if (e.key === 'k') go(-1);
  else if (e.key === 'v' && cur >= 0) { const el = ALL[cur]; prOf(el).setHunk(el, !el.classList.contains('viewed')); go(1); }
  else if (e.key === '?') toggleHelp();
});
document.querySelector('#topbar .ttl').textContent = document.title;
{
  const c = document.getElementById('splitchk'); c.checked = SPLIT;
  c.addEventListener('change', () => {
    SPLIT = c.checked; store.set('review:split', SPLIT);
    document.querySelectorAll('.hunk').forEach(el => { if (el._h) paintDiff(el, el._hideWS); });
  });
  document.querySelector('#topbar .navbtn').addEventListener('click', () => store.set('review:nonav', document.body.classList.toggle('nonav')));
}
function toggleHelp(anchor) {
  const h = document.getElementById('help'); h.hidden = !h.hidden;
  if (!h.hidden && anchor) { const r = anchor.getBoundingClientRect(); h.style.top = (r.bottom + 6) + 'px'; h.style.right = Math.max(8, innerWidth - r.right) + 'px'; }
}
document.addEventListener('click', e => {
  const b = e.target.closest('.helpbtn'); if (b) { e.stopPropagation(); toggleHelp(b); return; }
  const h = document.getElementById('help'); if (!h.hidden && !e.target.closest('#help')) h.hidden = true;
  document.querySelectorAll('details.more[open]').forEach(d => { if (!d.contains(e.target)) d.open = false; });
});
</script></body></html>
"""



# ---------------------------------------------------------------------------------------------
# PR setup, checks, the note-writer brief and the Claude Code skill
# ---------------------------------------------------------------------------------------------

def _run(*cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout


def cmd_init(args):
    """Fetch PRs with `gh`, find stacks, and write diffs, chunks, order stubs and the config."""
    out = pathlib.Path(args.dir).resolve()
    (out / "diffs").mkdir(parents=True, exist_ok=True)
    clone = pathlib.Path(args.clone).resolve() if args.clone else None
    fields = "number,title,url,baseRefName,headRefOid,author"
    prs, prev_head = [], None
    for n in args.prs:
        meta = json.loads(_run("gh", "pr", "view", str(n), "-R", args.repo, "--json", fields))
        cfg = {"prefix": str(n), "label": f"#{n} " + meta["title"][:40], "url": meta["url"],
               "title": f"{args.repo} #{n}: {meta['title']}", "notes_dir": f"notes-{n}",
               "order": f"order-{n}.txt", "overview_file": f"overview-{n}.md",
               "pages_dir": f"pages-{n}", "diff": f"diffs/{n}.diff"}
        if args.mode == "explain":
            cfg["default_tab"] = "overview"
        if clone:
            ref = f"ez-{n}"
            _run("git", "fetch", "-q", "origin", f"pull/{n}/head:{ref}", cwd=clone)
            _run("git", "fetch", "-q", "origin", meta["baseRefName"], cwd=clone)
            stacked = prev_head and subprocess.run(
                ["git", "merge-base", "--is-ancestor", prev_head, ref], cwd=clone).returncode == 0
            base = prev_head if stacked else _run(
                "git", "merge-base", ref, f"origin/{meta['baseRefName']}", cwd=clone).strip()
            (out / cfg["diff"]).write_text(_run("git", "diff", base, ref, cwd=clone))
            cfg["git"] = {"repo": str(clone), "base": base, "head": ref}
            own = _run("git", "rev-list", "--count", f"{base}..{ref}", cwd=clone).strip()
            print(f"#{n}: {own} own commits" + (f", stacked on {prev_head}" if stacked else ""))
            prev_head = ref
        else:  # without a clone a stacked PR shows its whole diff against its base branch
            (out / cfg["diff"]).write_text(_run("gh", "pr", "diff", str(n), "-R", args.repo))
            print(f"#{n}: full diff against {meta['baseRefName']} (pass --clone to split stacks)")
        files = parse_diff((out / cfg["diff"]).read_text())
        order = out / cfg["order"]
        if not order.exists():  # tests and generated files last; edit into a reading order
            key = lambda f: (bool(re.search(r"(^|/)tests?/|test_", f["path"])), f["path"])
            order.write_text("".join(f["path"] + "\n" for f in sorted(files, key=key)))
        (out / cfg["notes_dir"]).mkdir(exist_ok=True)
        split_to(files, out / f"chunks-{n}")
        print(f"   {len(files)} files, {sum(len(f['hunks']) for f in files)} hunks -> chunks-{n}/")
        prs.append(cfg)
    conf = out / "ez-review.json"
    title = args.title or f"{args.repo}: " + ", ".join(f"#{n}" for n in args.prs)
    conf.write_text(json.dumps({"title": title, "prs": prs}, indent=1, ensure_ascii=False))
    print(f"wrote {conf}\nnext: write notes (see `brief`), then `check` and `render-multi`")


def split_to(files, out):
    out.mkdir(parents=True, exist_ok=True)
    for f in files:
        with open(out / (f["path"].replace("/", "__") + ".chunks.txt"), "w") as fh:
            fh.write(f"FILE {f['path']}  (+{f['add']} -{f['del']}, {len(f['hunks'])} hunks)\n\n")
            for h in f["hunks"]:
                fh.write(f"===== HUNK {h['id']}\n{h['header']}\n")
                for t, o, n, b in h["lines"]:
                    fh.write(f"{t}{n if n is not None else o:>6} {b}\n")
                fh.write("\n")


def cmd_check(args):
    """Report notes coverage and draft comments for every PR in a config."""
    conf_path = pathlib.Path(args.config).resolve()
    os.chdir(conf_path.parent)
    bad = 0
    for cfg in json.loads(conf_path.read_text())["prs"]:
        for p in sorted(pathlib.Path(cfg["notes_dir"]).glob("**/*.json")):
            try:
                json.loads(p.read_text())
            except ValueError as e:
                print(f"  BAD JSON {p}: {e}")
                bad += 1
        notes, _ = load_notes(cfg["notes_dir"])
        ids = [h["id"] for f in parse_diff(pathlib.Path(cfg["diff"]).read_text()) for h in f["hunks"]]
        missing = [i for i in ids if not notes["hunks"].get(i, {}).get("note")]
        extra = sorted(set(notes["hunks"]) - set(ids))
        asks = [(i, h["ask"]) for i, h in notes["hunks"].items() if isinstance(h.get("ask"), dict)]
        print(f"#{cfg['prefix']}: {len(ids) - len(missing)}/{len(ids)} hunks with notes, "
              f"{len(asks)} draft comments" + (f", unknown ids: {extra}" if extra else ""))
        for i in missing:
            print("  missing", i)
        for i, a in asks:
            print(f"  {a.get('priority', '?'):8} {i}  {a.get('title', '')}")
        bad += len(missing)
    sys.exit(1 if bad else 0)


def cmd_posted(args):
    """Write the review threads USER started on a PR, for the page's "Already posted" list."""
    raw = _run("gh", "api", "--paginate", f"repos/{args.repo}/pulls/{args.pr}/comments")
    comments = json.loads(raw.replace("]\n[", ",").replace("][", ","))
    result = []
    for r in sorted((c for c in comments if not c.get("in_reply_to_id") and c["user"]["login"] == args.user),
                    key=lambda c: c["created_at"]):
        replies = [c for c in comments if c.get("in_reply_to_id") == r["id"]]
        text = " ".join(re.sub(r"```.*?```", "[code]", r["body"], flags=re.S).split())
        result.append({"where": f'{r["path"].split("/")[-1]}:{r.get("line") or r.get("original_line")}',
                       "text": text[:140] + ("…" if len(text) > 140 else ""),
                       "url": f"https://github.com/{args.repo}/pull/{args.pr}#discussion_r{r['id']}",
                       "replies": len(replies),
                       "author_replied": any(c["user"]["login"] != args.user and "bot" not in c["user"]["login"]
                                             for c in replies)})
    pathlib.Path(args.out).write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(f"{len(result)} threads")


def cmd_brief(args):
    """Print the note-writer brief from SKILL.md, with the mode and subject filled in."""
    skill = (pathlib.Path(__file__).resolve().parent / "SKILL.md").read_text()
    brief = skill.split("<!-- brief -->\n", 1)[1].split("<!-- /brief -->", 1)[0]
    print(brief.replace("__MODE__", args.mode).replace("__WHAT__", args.what), end="")


def main():
    ap = argparse.ArgumentParser(description="E-Z-Review: HTML review pages for GitHub PRs.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", help="fetch PRs and write diffs, chunks, order stubs and the config")
    i.add_argument("--repo", required=True, help="OWNER/NAME")
    i.add_argument("--prs", required=True, nargs="+", type=int, help="PR numbers; list a stack bottom-up")
    i.add_argument("--clone", default="", help="local clone: splits stacks into own commits")
    i.add_argument("--dir", default=".", help="output folder")
    i.add_argument("--title", default="")
    i.add_argument("--mode", choices=["review", "explain"], default="review")
    b = sub.add_parser("brief", help="print the note-writer brief")
    b.add_argument("--mode", choices=["review", "explain"], default="review")
    b.add_argument("--what", default="the PRs on this page")
    k = sub.add_parser("check", help="notes coverage and draft comments per PR")
    k.add_argument("config")
    p = sub.add_parser("posted", help="fetch a user's review threads on a PR")
    p.add_argument("repo")
    p.add_argument("pr")
    p.add_argument("user")
    p.add_argument("out")
    s = sub.add_parser("split", help="one chunk dump per file, for note writers")
    s.add_argument("diff")
    s.add_argument("out_dir")
    r = sub.add_parser("render", help="one PR, from a diff and a notes folder")
    r.add_argument("diff")
    r.add_argument("notes_dir")
    r.add_argument("out")
    r.add_argument("--title", required=True)
    r.add_argument("--url", default="")
    r.add_argument("--overview", default="")
    r.add_argument("--posted", default="", help="JSON list of posted threads [{where, text, url, replies}]")
    r.add_argument("--seed-viewed", default="", help="JSON list of hunk ids to mark viewed once")
    r.add_argument("--pages-dir", default="", help="also write one page per hunk: DIR/<n>.html")
    r.add_argument("--since", default="", help="label for 'changed since' markers, e.g. a commit")
    r.add_argument("--order", default="", help="text file: file paths in reading order")
    r.add_argument("--subst", default="", help="JSON file {regex: replacement} applied to note text")
    r.add_argument("--prefix", default="pr", help="short PR id for element ids and ?hunk=PREFIX:N")
    m = sub.add_parser("render-multi", help="one page for several PRs, each collapsible")
    m.add_argument("config")
    m.add_argument("out")
    c = sub.add_parser("carry", help="move notes from an old diff to a new diff of the same PR")
    c.add_argument("old_diff")
    c.add_argument("old_notes")
    c.add_argument("new_diff")
    c.add_argument("out_dir")
    args = ap.parse_args()
    {"init": cmd_init, "brief": cmd_brief, "check": cmd_check, "posted": cmd_posted,
     "split": cmd_split, "render": cmd_render,
     "render-multi": cmd_render_multi, "carry": cmd_carry}[args.cmd](args)


if __name__ == "__main__":
    main()
