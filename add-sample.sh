#!/bin/sh
# Add a generated animation result to samples/ as three sibling items:
#   samples/NAME/     verbatim copy of the evidence folder (Blender backups and caches skipped);
#                     each --extra folder or file is copied verbatim to samples/NAME/extra/<basename>
#   samples/NAME.mp4  web-sized H.264 encode of the supplied video
#   samples/NAME.md   written afterwards by the agent (see docs/samples.md)
# Then rank the agent chats that most likely produced the evidence.
set -eu

usage() {
  echo "usage: $0 <source-dir> <video.mov|video.mp4> [--name NAME] [--extra PATH]..." >&2
  exit 2
}
die() { echo "add-sample: $*" >&2; exit 1; }

[ $# -ge 2 ] || usage
src_arg=$1
video_arg=$2
shift 2
name=
extra_args=
while [ $# -gt 0 ]; do
  case $1 in
    --name) [ $# -ge 2 ] || usage; name=$2; shift 2 ;;
    --extra) [ $# -ge 2 ] || usage; extra_args="$extra_args$2
"; shift 2 ;;
    *) usage ;;
  esac
done

[ -d "$src_arg" ] || die "source folder not found: $src_arg"
[ -f "$video_arg" ] || die "video not found: $video_arg"
case $video_arg in
  *.mov|*.MOV|*.mp4|*.MP4) ;;
  *) die "video must be .mov or .mp4: $video_arg" ;;
esac
src=$(CDPATH= cd -- "$src_arg" && pwd)
video=$(CDPATH= cd -- "$(dirname -- "$video_arg")" && pwd)/$(basename -- "$video_arg")
[ -n "$name" ] || name=$(basename -- "$src")
printf '%s\n' "$name" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._-]*$' \
  || die "invalid sample name: $name"

# Extra sources (folders or files): absolute, distinct basenames, outside the evidence folder.
extras=
if [ -n "$extra_args" ]; then
  [ ! -e "$src/extra" ] || die "evidence already has an 'extra' entry; cannot add --extra sources"
  while IFS= read -r arg; do
    [ -n "$arg" ] || continue
    if [ -d "$arg" ]; then
      dir=$(CDPATH= cd -- "$arg" && pwd)
      case $src/ in
        "$dir"/*) die "extra folder contains the evidence folder: $arg" ;;
      esac
    elif [ -f "$arg" ]; then
      dir=$(CDPATH= cd -- "$(dirname -- "$arg")" && pwd)/$(basename -- "$arg")
      case $dir in
        *.blend[0-9]*|*.pyc|*/.DS_Store) die "extra file is not evidence: $arg" ;;
      esac
    else
      die "extra not found: $arg"
    fi
    case $dir/ in
      "$src"/*) die "extra is inside the evidence folder: $arg" ;;
    esac
    base=$(basename -- "$dir")
    if printf '%s' "$extras" | while IFS= read -r e; do [ "$(basename -- "$e")" != "$base" ] || exit 1; done; then :
    else die "two extras share the name: $base"; fi
    extras="$extras$dir
"
  done <<EOF
$extra_args
EOF
fi

repo=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$repo"
samples=$repo/samples
for item in "$samples/$name" "$samples/$name.mp4" "$samples/$name.md"; do
  [ ! -e "$item" ] || die "already exists, samples are never overwritten: ${item#"$repo"/}"
done
case $src/ in
  "$samples"/*) die "source is already inside samples/: $src" ;;
esac
command -v ffmpeg >/dev/null || die "ffmpeg not found"
command -v ffprobe >/dev/null || die "ffprobe not found"

max_width=${SAMPLE_MAX_WIDTH:-1920}
max_fps=${SAMPLE_FPS:-30}
crf=${SAMPLE_CRF:-24}
docker_root=${DOCKER_ROOT:-$repo/../ldraw-mecha-docker}

work=$(mktemp -d)
copied=
trap 'rm -rf "$work"; if [ -n "$copied" ]; then rm -rf "$samples/$name"; fi' EXIT
trap 'exit 1' INT TERM

probe() {
  ffprobe -v error -select_streams v:0 \
    -show_entries stream=codec_name,width,height,r_frame_rate:format=duration,size \
    -of default=noprint_wrappers=1 "$1" | tr '\n' ' '
}

echo "== video"
echo "source: $(probe "$video")"
src_fps=$(ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate \
  -of default=noprint_wrappers=1:nokey=1 "$video")
filters="scale='min($max_width,iw)':-2"
if awk -v r="$src_fps" -v m="$max_fps" 'BEGIN { split(r, a, "/"); exit !(a[2] && a[1] / a[2] > m) }'; then
  filters="$filters,fps=$max_fps"
fi
filters="$filters,format=yuv420p"
ffmpeg -nostdin -hide_banner -loglevel error -stats -i "$video" -map 0:v:0 -an \
  -vf "$filters" -c:v libx264 -preset slow -crf "$crf" -movflags +faststart \
  "$work/video.mp4"
echo "sample: $(probe "$work/video.mp4")"

# Copy a folder verbatim except Blender backups, Python caches and Finder files, then prove it.
copy_tree() {
  rsync -a --exclude .DS_Store --exclude '*.blend[0-9]*' --exclude __pycache__ --exclude '*.pyc' "$1/" "$2/"
  diff -r -x .DS_Store -x '*.blend[0-9]*' -x __pycache__ -x '*.pyc' "$1" "$2" >/dev/null \
    || die "copy of $1 does not match the source"
  echo "copied: $(cd "$2" && find . -type f | wc -l | tr -d ' ') files to ${2#"$repo"/}/"
  (cd "$1" && find . -type f \( -name .DS_Store -o -name '*.blend[0-9]*' -o -name '*.pyc' \)) \
    | sed "s|^\./|skipped (not evidence): ${1#"$repo"/}/|"
}

copy_file() {
  mkdir -p "$(dirname -- "$2")"
  cp -p "$1" "$2"
  cmp -s "$1" "$2" || die "copy of $1 does not match the source"
  echo "copied: ${2#"$repo"/}"
}

echo "== evidence"
mkdir -p "$samples"
copied=1
copy_tree "$src" "$samples/$name"
while IFS= read -r dir; do
  [ -n "$dir" ] || continue
  if [ -d "$dir" ]; then
    copy_tree "$dir" "$samples/$name/extra/$(basename -- "$dir")"
  else
    copy_file "$dir" "$samples/$name/extra/$(basename -- "$dir")"
  fi
done <<EOF
$extras
EOF
mv "$work/video.mp4" "$samples/$name.mp4"
copied=

echo "== publish check"
files=$(cd "$repo" && find "samples/$name" "samples/$name.mp4" -type f | sort)
ignored=$(printf '%s\n' "$files" | git check-ignore --stdin || true)
large=$(printf '%s\n' "$files" | git check-attr filter --stdin | awk -F': ' '$3 != "lfs" { print $1 }' \
  | while IFS= read -r f; do [ "$(wc -c <"$f")" -le 5242880 ] || echo "$f"; done)
[ -z "$large" ] || printf '%s\n' "$large" | sed 's/^/warning: non-LFS file over 5 MB: /'
if [ -n "$ignored" ]; then
  printf '%s\n' "$ignored" | sed 's/^/error: git ignores sample file: /' >&2
  exit 1
fi
echo "ok: all $(printf '%s\n' "$files" | wc -l | tr -d ' ') files are committable"

# A source in another checkout (e.g. an experiment clone) has its own chats and paths.
src_root=$(git -C "$src" rev-parse --show-toplevel 2>/dev/null || true)

python3 -I - "$name" "$src" "$repo" "$docker_root" "$src_root" <<'PY'
import datetime as dt
import glob
import json
import os
import re
import sys

name, src, repo, docker_root, src_root = sys.argv[1:]
docker_root = os.path.realpath(docker_root)
backup = re.compile(r"\.blend\d+$")
rels, mtimes = [], []
for root, _, names in os.walk(src):
    for n in names:
        if n == ".DS_Store" or backup.search(n) or n.endswith(".pyc"):
            continue
        path = os.path.join(root, n)
        rels.append(os.path.relpath(path, src))
        mtimes.append(os.path.getmtime(path))
utc = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc)
first, last = utc(min(mtimes)), utc(max(mtimes))
blends = sorted(r for r in rels if r.endswith(".blend"))

models = set()
for r in rels:
    if r.endswith(".json"):
        try:
            text = open(os.path.join(src, r), errors="replace").read()
        except OSError:
            continue
        models |= set(re.findall(r'[\w./~-]+\.(?:mpd|ldr)\b', text))

print("== facts")
print(f"sample: samples/{name}/  (source {src})")
print(f"evidence mtimes (UTC): {first:%Y-%m-%d %H:%M:%S} .. {last:%Y-%m-%d %H:%M:%S}")
print("blend files:", ", ".join(f"{name}/{b}" for b in blends) or "none")
print("models referenced:", ", ".join(sorted(models)) or "none found")
print(f"summary links: [{name}.mp4]({name}.mp4)  [{name}/]({name}/)")
extra = os.path.join(repo, "samples", name, "extra")
for e in sorted(os.listdir(extra)) if os.path.isdir(extra) else []:
    e += "/" if os.path.isdir(os.path.join(extra, e)) else ""
    print(f"extra source: [{name}/extra/{e}]({name}/extra/{e})")

# The source as chats would spell it: relative to its project, else parent/name.
if src.startswith(repo + os.sep):
    key = os.path.relpath(src, repo)
elif src.startswith(docker_root + os.sep):
    key = os.path.relpath(src, os.path.join(docker_root, "data"))
    src_root = ""
elif src_root:
    key = os.path.relpath(src, src_root)
else:
    key = os.path.join(os.path.basename(os.path.dirname(src)), os.path.basename(src))
edge = r"(?<![A-Za-z0-9_.-])"
mention = re.compile(edge + re.escape(key) + r"(?![A-Za-z0-9_-])")
ref = re.compile(edge + re.escape(key) + r"/([^\s\"'\\`<>()\[\]{},;|*]+)")
relset = set(rels)
stamp = re.compile(r'"timestamp"\s*:\s*"([^"]+)"')


def parse(ts):
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def window(start, end):
    if start and start > last:
        return "after"
    if end and end < first:
        return "before"
    return "overlaps" if start and end else "unknown"


def score(path, source, model_of):
    try:
        text = open(path, errors="replace").read()
    except OSError:
        return None
    total = len(mention.findall(text))
    if not total:
        return None
    hits = set()
    for tail in ref.findall(text):
        tail = tail.rstrip(".:")
        if tail in relset:
            hits.add(tail)
    stamps = stamp.findall(text)
    start = parse(stamps[0]) if stamps else None
    end = parse(stamps[-1]) if stamps else None
    # Long sessions can span the evidence window yet only reach the folder later.
    hit = mention.search(text)
    line = text[text.rfind("\n", 0, hit.start()) + 1:text.find("\n", hit.start())]
    first = stamp.search(line)
    first = parse(first.group(1)) if first else start
    found = sorted({m for m in map(model_of, text.splitlines()) if m and m != "<synthetic>"})
    return dict(path=path, source=source, hits=sorted(hits), total=total, start=start,
                end=end, first=first, flag=window(first, end), models=found)


def record(line, marker):
    if marker not in line:
        return {}
    try:
        return json.loads(line)
    except ValueError:
        return {}


# Models the agent itself ran on, not model names quoted in tool output.
claude_model = lambda line: ((record(line, '"type":"assistant"').get("message") or {}).get("model")
                             if '"type":"assistant"' in line else None)
codex_model = lambda line: (record(line, '"turn_context"').get("payload") or {}).get("model")

candidates = []
projects = {repo, src_root} - {""}
slugs = {re.sub(r"[^A-Za-z0-9]", "-", p) for p in projects}
claude_dirs = [d for d in glob.glob(os.path.expanduser("~/.claude/projects/*"))
               if any(os.path.basename(d) == s or os.path.basename(d).startswith(s + "--") for s in slugs)]
for d in claude_dirs:
    for path in glob.glob(os.path.join(d, "**", "*.jsonl"), recursive=True):
        c = score(path, "claude", claude_model)
        if c:
            candidates.append(c)
for base in ("~/.codex/sessions", "~/.codex/archived_sessions"):
    for path in glob.glob(os.path.join(os.path.expanduser(base), "**", "*.jsonl"), recursive=True):
        try:
            with open(path, errors="replace") as fh:
                meta = json.loads(fh.readline()).get("payload", {})
        except (OSError, ValueError):
            continue
        if meta.get("cwd") not in projects:
            continue
        c = score(path, "codex", codex_model)
        if c:
            candidates.append(c)

docker = []
chats = os.path.join(docker_root, "data", "chats")
outputs = os.path.join(docker_root, "data", "output")
ids = set(os.listdir(chats)) if os.path.isdir(chats) else set()
if src.startswith(outputs + os.sep):
    exact = {os.path.relpath(src, outputs).split(os.sep)[0]}
else:
    exact = {i for i in ids if i in os.path.basename(src)}
for i in sorted(ids):
    msgs = os.path.join(chats, i, "messages.jsonl")
    if i not in exact:
        try:
            if not mention.search(open(msgs, errors="replace").read()):
                continue
        except OSError:
            continue
    try:
        chat = json.load(open(os.path.join(chats, i, "chat.json")))
    except (OSError, ValueError):
        chat = {}
    try:
        llms = sorted(set(re.findall(r'"_llm_model"\s*:\s*"([^"]+)"', open(msgs).read())))
    except OSError:
        llms = []
    start, end = (utc(chat[k]) if chat.get(k) else None for k in ("created_at", "updated_at"))
    docker.append(dict(path=os.path.join(chats, i), exact=i in exact, title=chat.get("title"),
                       start=start, end=end, flag=window(start, end), models=llms))

fmt = lambda t: f"{t:%Y-%m-%d %H:%M}" if t else "?"
print("== chat candidates (best first)")


def show_docker(c):
    print(f"docker {'exact' if c['exact'] else 'mentions name'}: {c['path']}")
    print(f"  title: {c['title']!r}  {fmt(c['start'])} .. {fmt(c['end'])} UTC  window: {c['flag']}"
          f"  models: {', '.join(c['models']) or '?'}")


# An exact chat-ID match is certain; name mentions rank with the other chats.
for c in docker:
    if c["exact"]:
        show_docker(c)
loose = [c for c in docker if not c["exact"]]
for c in sorted(loose, key=lambda c: c["flag"] == "after"):
    if c["flag"] != "after":
        show_docker(c)
# A chat that started after the evidence was last written cannot have produced it.
candidates.sort(key=lambda c: (c["flag"] == "after", -len(c["hits"]), -c["total"],
                               c["flag"] != "overlaps"))
for c in candidates[:10]:
    print(f"{c['source']}: {c['path']}")
    print(f"  {len(c['hits'])}/{len(rels)} evidence files referenced, {c['total']} mentions of {key}, "
          f"{fmt(c['start'])} .. {fmt(c['end'])} UTC, first mention {fmt(c['first'])}, window: {c['flag']}"
          + (" (cannot have produced it)" if c["flag"] == "after" else ""))
    if c["models"]:
        print(f"  models: {', '.join(c['models'])}")
    if c["hits"]:
        print(f"  files: {', '.join(c['hits'][:12])}{' ...' if len(c['hits']) > 12 else ''}")
if len(candidates) > 10:
    print(f"... {len(candidates) - 10} more candidates omitted")
for c in loose:
    if c["flag"] == "after":
        show_docker(c)
if not candidates and not docker:
    print(f"no chat mentions {key}; search manually")
print(f"next: write samples/{name}.md following docs/samples.md")
PY
