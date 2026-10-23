"""Stamp the public HTML with its source version and unique Actions build ID."""
import os
import re
import sys
from pathlib import Path

VERSION = re.compile(r'(<span id="site-version">)(v[0-9]{8}-[1-9][0-9]*)(?:\+[a-z0-9.]+)?(</span>)')


def stamp(path, environment):
    source = path.read_text(encoding='utf-8')
    if len(VERSION.findall(source)) != 1:
        raise ValueError('Expected one visible site version')
    values = [environment.get(key, '') for key in ['GITHUB_SHA', 'GITHUB_RUN_NUMBER', 'GITHUB_RUN_ATTEMPT']]
    suffix = ''
    if any(values):
        sha, run, attempt = values
        if not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', sha) or not all(re.fullmatch(r'[1-9][0-9]{0,15}', value) for value in [run, attempt]):
            raise ValueError('Invalid build version metadata')
        suffix = '+' + sha[:7] + '.' + run + '.' + attempt
    base = VERSION.search(source)[2]
    release = base + suffix
    cache_version = re.compile(r'([?&]v=)' + re.escape(base[1:]) + r'(?:\+[a-z0-9.]+)?(?=[\x22\x27])')
    updated = VERSION.sub(lambda match: match[1] + release + match[3], source)
    updated = cache_version.sub(lambda match: match[1] + release[1:], updated)
    # The artifact's first-party module graph shares the same unique version.
    # Updating only HTML would let a new footer coexist with cached old imports.
    for module in path.parent.rglob('*.js'):
        if module.name == 'three.min.js':
            continue
        original = module.read_text(encoding='utf-8')
        stamped = cache_version.sub(lambda match: match[1] + release[1:], original)
        if stamped != original:
            module.write_text(stamped, encoding='utf-8')
    path.write_text(updated, encoding='utf-8')
    return release


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 scripts/stamp_version.py _site/index.html')
    print('Site version: ' + stamp(Path(sys.argv[1]), os.environ))
