"""Record and publish which third-party versions each released image contains.

    collect TAG IMAGE [--platform P ...] [--compose FILE] > versions.json
    render versions.json ... > VERSIONS.md

`collect` runs the already-pushed image once per platform and asks it for its
OS, Python and installed packages, then resolves the other images compose.yaml
names (Postgres, Caddy). Those are pinned to exact versions, but official images
are rebuilt under the same tag for OS patches, so their digest is what the tag
held on the day of the release. `render` turns any number of those records into one matrix, newest
release first. CI attaches both to the GitHub release for each version tag.

Standard library only, so it runs on a bare CI runner. Needs Docker.
"""

import argparse
import json
import os
import re
import subprocess
import sys

# Run inside the image. `python` is whatever the image puts on PATH, which is
# exactly the interpreter gunicorn runs under.
PROBE = r"""
import importlib.metadata, json, platform
os_release = dict(
    line.rstrip("\n").split("=", 1)
    for line in open("/etc/os-release")
    if "=" in line
)
print(json.dumps({
    "os": os_release.get("PRETTY_NAME", "").strip('"'),
    "python": platform.python_version(),
    "packages": {
        d.metadata["Name"].lower().replace("_", "-"): d.version
        for d in importlib.metadata.distributions()
    },
}))
"""


def run(*args):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE, text=True).stdout


def probe_image(image, platform):
    return json.loads(run("docker", "run", "--rm", "--platform", platform, "--entrypoint", "python", image, "-c", PROBE))


def compose_images(compose_file):
    # Compose refuses to render without the required variables, whose values
    # are irrelevant to which images it names.
    env = dict(os.environ, DJANGO_SECRET_KEY="x", POSTGRES_PASSWORD="x")
    out = subprocess.run(
        ["docker", "compose", "-f", compose_file, "config", "--images"],
        check=True, stdout=subprocess.PIPE, text=True, env=env,
    ).stdout
    return sorted(set(out.split()))


def probe_companion(image, platform):
    run("docker", "pull", "--quiet", "--platform", platform, image)
    inspect = json.loads(run("docker", "image", "inspect", image))[0]
    env = dict(e.split("=", 1) for e in inspect["Config"].get("Env", []))
    os_release = run("docker", "run", "--rm", "--platform", platform, "--entrypoint", "cat", image, "/etc/os-release")
    pretty = re.search(r'^PRETTY_NAME="?(.*?)"?$', os_release, re.M)
    return {
        "digest": (inspect.get("RepoDigests") or [""])[0].partition("@")[2],
        "os": pretty.group(1) if pretty else "",
        # Official images advertise their upstream version this way:
        # PG_VERSION in postgres, CADDY_VERSION in caddy.
        "versions": {k: v for k, v in env.items() if k.endswith("_VERSION")},
    }


def collect(args):
    own_repo = args.image.rsplit(":", 1)[0]
    platforms = {p: probe_image(args.image, p) for p in args.platform}
    # The rest comes from the image rather than from this run, so a release
    # recorded after the fact gets its own commit and date, not today's.
    # docker/metadata-action writes these labels; a local build has neither.
    inspect = json.loads(run("docker", "image", "inspect", args.image))[0]
    labels = inspect["Config"].get("Labels") or {}
    record = {
        "tag": args.tag,
        "image": args.image,
        # After a pull by tag this is the multi-arch index: the digest to pin.
        "digest": (inspect.get("RepoDigests") or [""])[0].partition("@")[2],
        "commit": labels.get("org.opencontainers.image.revision", ""),
        "released": labels.get("org.opencontainers.image.created", inspect["Created"])[:10],
        "platforms": platforms,
        "companions": {},
    }
    if args.compose:
        for image in compose_images(args.compose):
            if image.rsplit(":", 1)[0] != own_repo:
                record["companions"][image] = probe_companion(image, args.platform[0])
    json.dump(record, sys.stdout, indent=2, sort_keys=True)
    print()


def version_key(record):
    return tuple(int(n) if n.isdigit() else n for n in re.split(r"[.\-+]", record["tag"].lstrip("v")))


def per_platform(record, get):
    """One value when every platform agrees, otherwise each labelled by arch."""
    values = {p.rsplit("/", 1)[-1]: get(data) for p, data in record["platforms"].items()}
    distinct = set(values.values()) - {None}
    if not distinct:
        return "—"
    if len(distinct) == 1:
        return distinct.pop()
    return "<br>".join(f"{arch}: {v or '—'}" for arch, v in values.items())


def table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def render(args):
    records = []
    for path in args.files:
        with open(path) as f:
            records.append(json.load(f))
    records.sort(key=version_key, reverse=True)
    tags = [f"`{r['tag']}`" for r in records]
    out = [
        "# Third-party versions by release",
        "",
        "What each published `ghcr.io/ajp442/planfc` image contains, newest release first.",
        "The `latest` and `MAJOR.MINOR` tags move; each points at the newest release it matches.",
        "",
        "## Inside the planfc image",
        "",
    ]
    rows = [
        ["Released"] + [r.get("released") or "—" for r in records],
        ["Platforms"] + [", ".join(p.rsplit("/", 1)[-1] for p in r["platforms"]) for r in records],
        ["Digest"] + [f"`{r['digest'][:19]}…`" if r.get("digest") else "—" for r in records],
        ["Base OS"] + [per_platform(r, lambda d: d["os"]) for r in records],
        ["Python"] + [per_platform(r, lambda d: d["python"]) for r in records],
    ]
    packages = sorted({name for r in records for d in r["platforms"].values() for name in d["packages"]})
    rows += [[name] + [per_platform(r, lambda d: d["packages"].get(name)) for r in records] for name in packages]
    out += [table(["Component"] + tags, rows), ""]

    companions = sorted({image for r in records for image in r.get("companions", {})})
    if companions:
        out += [
            "## Alongside it, from compose.yaml",
            "",
            "The images `compose.yaml` pinned at each release. Official images are rebuilt",
            "under the same tag for OS patches, so the digest is what the tag held on release day.",
            "",
        ]
        rows = []
        for image in companions:
            found = [r.get("companions", {}).get(image) for r in records]
            keys = sorted({k for c in found if c for k in c["versions"]})
            rows += [[f"`{image}` {k}"] + [c["versions"].get(k, "—") if c else "—" for c in found] for k in keys]
            rows.append([f"`{image}` OS"] + [c["os"] or "—" if c else "—" for c in found])
            rows.append([f"`{image}` digest"] + [f"`{c['digest'][:19]}…`" if c and c["digest"] else "—" for c in found])
        out += [table(["Component"] + tags, rows), ""]

    missing = [r["tag"] for r in records if not r.get("companions")]
    if companions and missing:
        out += [f"Releases with no companion data ({', '.join(missing)}) were recorded after the fact, "
                "from their image alone.", ""]
    sys.stdout.write("\n".join(out))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(required=True)
    c = sub.add_parser("collect")
    c.add_argument("tag")
    c.add_argument("image")
    c.add_argument("--platform", action="append", default=[], help="repeatable; default linux/amd64")
    c.add_argument("--compose", help="also resolve the other images this compose file names")
    c.set_defaults(func=collect)
    r = sub.add_parser("render")
    r.add_argument("files", nargs="+")
    r.set_defaults(func=render)
    args = parser.parse_args()
    if args.func is collect and not args.platform:
        args.platform = ["linux/amd64"]
    args.func(args)


if __name__ == "__main__":
    main()
