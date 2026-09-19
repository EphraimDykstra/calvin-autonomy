#!/usr/bin/env python3
"""Audit a tree for private workspace material and personal absolute paths."""
from pathlib import Path
import argparse, json, os, re, sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from engineering_assistant.identity import find_identity_leaks, require_redactable
ALLOW={'AGENTS.md','CLAUDE.md','README.md','.gitignore','pyproject.toml'}
PRIVATE_NAMES=re.compile(r'(^|[._-])(env|auth|secret|token|credential|key)([._-]|$)',re.I)
PRIVATE_COMPONENTS={'courses','course-pack','course_packs','course-content','assignments','runs','logs','memory'}
AUDIT_EXEMPT={'scripts/check_distribution.py','tests/test_setup.py','src/engineering_assistant/identity.py','tests/test_course_pack.py','templates/verification.json'}
IGNORED_COMPONENTS={'.venv','.git','.calvin-autonomy','__pycache__','cache','build','dist','worktrees'}

# Claude Code plugin manifests (issue #41).  The plugin spec requires `name` and
# `owner.name`, which the generic identity-key check treats as personal fields.
# For exactly these two paths the KEY check is replaced by a stricter,
# schema-aware one: a closed key allowlist, package-id names, and fixed project
# labels as the only person-shaped values, with `email` and `url` rejected.
# Every VALUE is still scanned for personal paths and forbidden names, and the
# text-level scans above still run.  This is not an exemption.
PLUGIN_MANIFESTS={'.claude-plugin/marketplace.json','.claude-plugin/plugin.json'}
PROJECT_LABELS={'Calvin Autonomy','Calvin Schoolwork'}
PACKAGE_ID=re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
MANIFEST_KEYS={
    'marketplace':{'name','owner','description','plugins'},
    'owner':{'name'},
    'entry':{'name','displayName','source','description','category','keywords'},
    'plugin':{'name','displayName','description','agents'},
}

def plugin_manifest_errors(rel, data, forbidden_names=()):
    problems=[]
    def keys(obj, kind, where):
        if not isinstance(obj, dict):
            problems.append(f'{where} is not an object'); return {}
        for key in sorted(set(obj)-MANIFEST_KEYS[kind]):
            problems.append(f'{where}.{key} is not a permitted key')
        return obj
    def package_id(value, where):
        if not isinstance(value, str) or not PACKAGE_ID.fullmatch(value):
            problems.append(f'{where} is not a package id')
    def label(value, where):
        if value not in PROJECT_LABELS:
            problems.append(f'{where} is not a project label')
    if rel.endswith('marketplace.json'):
        top=keys(data,'marketplace','$')
        package_id(top.get('name'),'$.name')
        owner=keys(top.get('owner'),'owner','$.owner')
        label(owner.get('name'),'$.owner.name')
        entries=top.get('plugins')
        if not isinstance(entries, list): problems.append('$.plugins is not a list'); entries=[]
        for i,entry in enumerate(entries):
            entry=keys(entry,'entry',f'$.plugins[{i}]')
            package_id(entry.get('name'),f'$.plugins[{i}].name')
            if 'displayName' in entry: label(entry['displayName'],f'$.plugins[{i}].displayName')
    else:
        top=keys(data,'plugin','$')
        package_id(top.get('name'),'$.name')
        if 'displayName' in top: label(top['displayName'],'$.displayName')
    # Values: personal paths and forbidden names, key names ignored.
    def values(item, where):
        if isinstance(item, dict):
            for key, child in item.items(): values(child, f'{where}.{key}')
        elif isinstance(item, list):
            for i, child in enumerate(item): values(child, f'{where}[{i}]')
        elif isinstance(item, str):
            problems.extend(f'{where}: {leak}' for leak in find_identity_leaks([item], forbidden_names))
    values(data,'$')
    return problems

def _ignored(rel):
    return any(part in IGNORED_COMPONENTS or part.endswith('.egg-info') for part in rel.parts)

def _private_name(path):
    return any(PRIVATE_NAMES.search(part) for part in path.parts)

def audit(root, forbidden_names=()):
    root=Path(root).resolve(); errors=[]
    paths = list(root.rglob('*'))
    # Reject secret-like filenames before opening any file in the tree.
    for p in paths:
        rel=p.relative_to(root)
        if _ignored(rel): continue
        if any(part=='workspace' for part in rel.parts): continue
        if any(part.casefold() in PRIVATE_COMPONENTS for part in rel.parts):
            errors.append(f'private course/run path: {rel}'); continue
        # The audit implementation and its tests necessarily contain generic
        # detector patterns and path fixtures; do not treat those patterns as
        # leaked user data.
        if rel.as_posix() in AUDIT_EXEMPT: continue
        # Check every path component before any file probe or content read.
        if _private_name(rel): errors.append(f'secret-like name: {rel}')
    if errors:
        return errors
    for p in paths:
        rel=p.relative_to(root)
        if _ignored(rel): continue
        if any(part=='workspace' for part in rel.parts): continue
        if any(part.casefold() in PRIVATE_COMPONENTS for part in rel.parts): continue
        if rel.as_posix() in AUDIT_EXEMPT: continue
        if _private_name(rel): continue
        if rel.as_posix() in {'scripts/check_distribution.py','tests/test_setup.py','src/engineering_assistant/identity.py','tests/test_course_pack.py'}: continue
        if p.is_symlink() or not p.is_file(): continue
        if p.is_file():
            try: text=p.read_text(errors='ignore')
            except OSError: continue
            # Same matcher as the pull-request text scan; see text_findings.
            kinds={kind for kind,_ in text_findings(text,forbidden_names)}
            if 'personal path' in kinds: errors.append(f'personal path in {rel}')
            if 'forbidden name' in kinds: errors.append(f'forbidden name in {rel}')
            if rel.as_posix() in PLUGIN_MANIFESTS:
                try:
                    problems=plugin_manifest_errors(rel.as_posix(), json.loads(text), forbidden_names)
                except (ValueError, TypeError, json.JSONDecodeError):
                    problems=['not valid JSON']
                if problems: errors.append(f'identity metadata in {rel}: {"; ".join(problems)}')
            elif p.suffix.casefold() == '.json':
                try:
                    leaks=find_identity_leaks(json.loads(text), forbidden_names)
                except (ValueError, TypeError, json.JSONDecodeError):
                    leaks=[]
                if leaks: errors.append(f'identity metadata in {rel}')
    return errors
# Names for the forbidden-name scan (issue #20) come only from this
# environment variable, separated by ';' or newlines ("Doe, Jane" is a real
# name form, so not commas).  Not a config file: gitignored files are absent
# in every worktree, so the scan would silently not run where most work
# happens, and PRIVATE_NAMES would flag an obviously named config file.  An
# environment variable adds nothing to the tree and cannot be committed.
# Never set it in CI to test fixture names: tests/test_identity.py holds them
# and is not exempt, so every branch would fail.
NAMES_ENV='CALVIN_FORBIDDEN_NAMES'

# The repository's own canonical slug necessarily contains the owner's GitHub
# handle: it is in the clone URL and in the one line a student types to install
# the plugin.  That is public project metadata, not leaked coursework identity,
# and it is the one place a forbidden name legitimately appears.  Excising just
# this exact string before scanning keeps bare-surname entries useful in the
# name list; the alternatives are dropping them (losing the protection that
# matters) or exempting whole files (losing more).
PERMITTED_NAME_STRINGS=('EphraimDykstra/calvin-autonomy',)

def _without_permitted(text,permitted=None):
    # Injectable so tests can exercise the mechanism with invented names: this
    # file is not audit-exempt, so spelling the real handle in a fixture would
    # fail the very scan it is testing.
    for entry in (PERMITTED_NAME_STRINGS if permitted is None else permitted):
        text=text.replace(entry,'')
    return text

PERSONAL_PATH=re.compile(r'/Users/[^\s"\']+')

def text_findings(text,forbidden_names=()):
    """Personal paths and forbidden names in one piece of text.

    The one matcher.  `audit` scans tracked files and check_pr_text.py scans
    a pull request's title, body and commit messages, and they have to agree:
    two matchers drift, and the half that is wrong is the half nobody is
    watching.

    Returns a list of (kind, offset).  Never the matched text: a finding is
    reported into a build log, and a log that names the name has published
    exactly what the scan exists to keep out.
    """
    findings=[('personal path',m.start()) for m in PERSONAL_PATH.finditer(text)]
    scannable=_without_permitted(text).casefold()
    for name in forbidden_names:
        if not isinstance(name,str) or not name.strip(): continue
        position=scannable.find(name.casefold())
        if position>=0: findings.append(('forbidden name',position))
    return findings

# The variable holds the names themselves, and a path to the file that holds
# them looks exactly like one harmless name: it matches nothing, the scan
# reports "1 name, clean", and the gate goes green having checked nobody.
# Coordinators have written the wrong invocation into briefs more than once,
# so refuse the mistake rather than trusting everyone to notice the count.
def _refuse_a_path(raw):
    one=raw.strip()
    if not one or ';' in one or '\n' in one:
        return
    looks_like_path=one.startswith(('/','~','./','../')) or one.endswith(('.txt','.json','.env'))
    if looks_like_path or Path(one).expanduser().exists():
        raise ValueError(
            f'{NAMES_ENV} holds the names themselves, semicolon separated, not a path to them. '
            f'Got something that looks like a file: {one!r}. Read the file into the variable '
            f'instead, as {NAMES_ENV}="$(cat <file>)", or the scan checks one nonsense name and '
            'passes having checked nobody.')

def forbidden_names_from_env(environ=None):
    raw=(os.environ if environ is None else environ).get(NAMES_ENV,'')
    _refuse_a_path(raw)
    names=[n.strip() for n in re.split(r'[;\n]',raw) if n.strip()]
    for n in names: require_redactable(n,f'a name in {NAMES_ENV}')
    return names

def main(argv=None, environ=None):
    ap=argparse.ArgumentParser(); ap.add_argument('root',nargs='?',default='.'); a=ap.parse_args(argv)
    try: names=forbidden_names_from_env(environ)
    except ValueError as exc: print(exc,file=sys.stderr); return 2
    e=audit(a.root,names)
    if e: print('\n'.join(e),file=sys.stderr); return 1
    # Say whether the name scan ran; a pass must not imply names were checked.
    scan=f'{len(names)} name{"s"*(len(names)!=1)}, clean' if names else f'not run, {NAMES_ENV} is not set'
    print(f'distribution audit passed (forbidden-name scan: {scan})'); return 0
if __name__=='__main__': raise SystemExit(main())
