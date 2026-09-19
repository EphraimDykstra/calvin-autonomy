#!/usr/bin/env python3
"""Install this repository's managed skills and host adapters into a project."""
from pathlib import Path
import argparse, hashlib, shlex, shutil, sys

ROOT = Path(__file__).resolve().parents[1]
MANAGED = '.calvin-autonomy-managed'

def digest(path):
    h=hashlib.sha256()
    if path.is_file(): h.update(path.read_bytes())
    else:
        for p in sorted(path.rglob('*')):
            if p.is_file(): h.update(str(p.relative_to(path)).encode()+b'\0'+p.read_bytes())
    return h.hexdigest()

def install_tree(src, dst, force=False, managed=None):
    if not src.exists(): return []
    dst.mkdir(parents=True, exist_ok=True); changed=[]
    for s in sorted(src.rglob('*')):
        rel=s.relative_to(src); d=dst/rel
        if s.is_dir(): d.mkdir(parents=True, exist_ok=True); continue
        if d.exists() and not (force and str(d) in (managed or set())): continue
        d.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(s,d); changed.append(str(d))
    return changed

def _write_launcher(target, content, managed, newline='\n'):
    key=str(target)
    if target.exists() and key not in (managed or set()): return []
    if target.exists() and target.read_bytes()==content.replace('\n',newline).encode(): return []
    target.parent.mkdir(parents=True,exist_ok=True)
    with open(target,'w',newline=newline) as handle: handle.write(content)
    target.chmod(0o755); return [key]

def install_launcher(project, managed=None, plugin=False):
    """Write the sh launcher and a Windows .cmd twin.

    In a project install the launcher prefers the project's own venv.  In
    plugin mode it must not: the student's project may hold an unrelated
    .venv, and the package lives in the plugin's venv, which is this
    interpreter.
    """
    fallback=shlex.quote(sys.executable)
    if plugin:
        content=f'#!/bin/sh\nexec {fallback} -m engineering_assistant.cli "$@"\n'
        cmd=f'@echo off\n"{sys.executable}" -m engineering_assistant.cli %*\n'
    else:
        content=(
            '#!/bin/sh\n'
            'project_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)\n'
            'for project_python in "$project_root/.venv/bin/python" "$project_root/.venv/Scripts/python.exe"; do\n'
            '  if [ -x "$project_python" ]; then\n'
            '    exec "$project_python" -m engineering_assistant.cli "$@"\n'
            '  fi\n'
            'done\n'
            f'exec {fallback} -m engineering_assistant.cli "$@"\n'
        )
        # cmd.exe expands %ERRORLEVEL% inside a parenthesised block when the
        # block is parsed, so branch with goto and let `exit /b` return the
        # interpreter's own status.
        cmd=(
            '@echo off\n'
            'set "project_python=%~dp0..\\..\\.venv\\Scripts\\python.exe"\n'
            'if not exist "%project_python%" goto fallback\n'
            '"%project_python%" -m engineering_assistant.cli %*\n'
            'exit /b\n'
            ':fallback\n'
            f'"{sys.executable}" -m engineering_assistant.cli %*\n'
        )
    bin_dir=project/'.calvin-autonomy/bin'
    return (_write_launcher(bin_dir/'coursework',content,managed)
            + _write_launcher(bin_dir/'coursework.cmd',cmd,managed,newline='\r\n'))

# Claude Code keeps an installed plugin in a versioned cache that is replaced
# on update and swept about 14 days later, and deletes the plugin's data
# directory on uninstall.  Student work written under either would be lost
# without warning, so neither may ever hold a project or a workspace.
PLUGIN_STORES=(('.claude','plugins','cache'),('.claude','plugins','data'))

def plugin_store(path):
    parts=Path(path).resolve().parts
    for store in PLUGIN_STORES:
        for i in range(len(parts)-len(store)+1):
            if parts[i:i+len(store)]==store: return '/'.join(store)
    return None

def refuse_unsafe_location(project, ws, plugin):
    for label,path in (('project root',project),('workspace',ws)):
        store=plugin_store(path)
        if store:
            return f'refusing to put the {label} inside the Claude Code plugin store (~/{store}): it is deleted on plugin update or uninstall'
        if plugin and (path==ROOT.resolve() or ROOT.resolve() in path.parents):
            return f'refusing to put the {label} inside the plugin source tree; run from your own project folder'
    return None

def main(argv=None):
    ap=argparse.ArgumentParser(description='Install project-scoped Calvin Autonomy skills.')
    ap.add_argument('--project-root', type=Path, default=Path('.'), help='directory opened in Claude Code or Codex')
    ap.add_argument('--workspace', type=Path, default=Path('workspace'))
    ap.add_argument('--force', action='store_true', help='refresh files previously marked managed')
    ap.add_argument('--plugin', action='store_true', help='skills and agents come from the Claude Code plugin; install only the launcher, templates and workspace')
    args=ap.parse_args(argv); project=args.project_root.resolve()
    ws=(args.workspace if args.workspace.is_absolute() else project/args.workspace).resolve()
    problem=refuse_unsafe_location(project,ws,args.plugin)
    if problem:
        print(problem,file=sys.stderr); return 2
    project.mkdir(parents=True,exist_ok=True); ws.mkdir(parents=True,exist_ok=True)
    marker=ws/MANAGED; old={}
    prior_managed=set()
    if marker.exists():
        for line in marker.read_text().splitlines():
            if line.startswith('managed='): prior_managed.add(line.split('=',1)[1])
    changed=[]
    # In plugin mode the host loads skills and agents from the plugin itself;
    # copying them here as well would show every skill twice.
    if not args.plugin:
        for srcname, destinations in [('skills',['.agents/skills','.claude/skills']),('roles',['.agents/roles','.claude/roles'])]:
            src=ROOT/srcname
            for dest in destinations: changed += install_tree(src,project/dest,args.force,prior_managed)
        for srcname,dest in [('.codex/agents','.codex/agents'),('.claude/agents','.claude/agents')]:
            changed += install_tree(ROOT/srcname,project/dest,args.force,prior_managed)
    changed += install_tree(ROOT/'templates',project/'.calvin-autonomy/templates',args.force,prior_managed)
    changed += install_launcher(project,prior_managed,args.plugin)
    lines=['schema_version=1','source_digest='+digest(ROOT/'skills')]
    if args.plugin: lines.append('mode=plugin')
    all_managed=sorted(prior_managed.union(changed))
    lines += ['managed='+p for p in all_managed]
    marker.write_text('\n'.join(lines)+'\n')
    print(f'project_root={project} workspace={ws} installed_or_preserved={len(changed)} force={args.force} plugin={args.plugin}')
    return 0
if __name__=='__main__': raise SystemExit(main())
