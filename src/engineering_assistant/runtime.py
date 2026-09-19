"""Durable assignment run state and readiness checks."""
from __future__ import annotations
import json
import zipfile
from pathlib import Path
from .common import atomic_json, digest, now, sha256, permitted_source, safe_relative
from .identity import run_identity
from .evidence import resolve_evidence
from .course_profile import load_course_profile
from .verification import validate_verification_report
from .ingest import extract_source_blocks

def run_dir(workspace: Path, run_id: str) -> Path:
    if not isinstance(run_id,str) or not run_id or '/' in run_id or '\\' in run_id or run_id.startswith('.'):
        raise ValueError('invalid run id')
    return Path(workspace)/'assignments'/run_id

def start_run(
    workspace: Path,
    run_id: str,
    course: str,
    input_path: Path,
    *,
    display_name: str | None = None,
    student_id: str | None = None,
    identity: dict | None = None,
) -> dict:
    """Start a private run with optional, explicitly supplied identity.

    The identity is stored only in this run's state.  Course catalogs and
    reusable matching examples never receive it.
    """
    root=run_dir(workspace,run_id)
    if (root/'run.json').exists(): raise ValueError('run id already exists')
    root.mkdir(parents=True,exist_ok=True)
    if not input_path.is_file() or input_path.is_symlink() or not permitted_source(input_path): raise ValueError('assignment must be a permitted regular file')
    target=root/'input'/input_path.name; target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(input_path.read_bytes())
    extraction=extract_source_blocks(target)
    state={'schema_version':1,'run_id':run_id,'course':course,'created_at':now(),'stage':'received','identity':run_identity(display_name, student_id, identity), 'input':{'name':input_path.name,'path':'input/'+input_path.name,'sha256':sha256(target),'extraction':extraction},'requirements':[],'checks':[],'artifacts':[],'unresolved':['requirements manifest not created']}
    atomic_json(root/'run.json',state); return state

def load_run(workspace:Path,run_id:str)->dict:
    p=run_dir(workspace,run_id)/'run.json'
    if not p.is_file(): raise FileNotFoundError(p)
    return json.loads(p.read_text())

def save_run(workspace:Path,state:dict)->None:
    atomic_json(run_dir(workspace,state['run_id'])/'run.json',state)

_DOWNSTREAM_RECORDS={
    'solution':lambda state: bool(state.get('solution')),
    'calculation checks':lambda state: bool(state.get('checks')),
    'structured verifier report':lambda state: isinstance(state.get('verification_report'),dict),
    'deliverable artifacts':lambda state: bool(state.get('artifacts')),
    'artifact inspections':lambda state: any(isinstance(a,dict) and isinstance(a.get('inspection_report'),dict) for a in state.get('artifacts',[])),
}

def _note_discarded(state:dict,operation:str,names,extra=())->list[str]:
    """Record which completed downstream records an operation invalidates.

    Every writer below is right to drop stale downstream state; doing it silently
    is what leaves a run quietly incomplete while the stage still looks plausible.
    Only records that were actually present are named, so an ordinary forward run
    writes nothing here and the log stays a signal.
    """
    discarded=[name for name in names if _DOWNSTREAM_RECORDS[name](state)]+[value for value in extra if value]
    if discarded: state.setdefault('discarded',[]).append({'at':now(),'operation':operation,'records':discarded})
    return discarded

def _course_evidence_blockers(state:dict,root:Path)->list[str]:
    """Resolve plan evidence against the current assignment or course catalog."""
    workspace=root.parent.parent
    return [
        f"plan {message}"
        for message in resolve_evidence(
            workspace,
            state.get('course',''),
            state.get('plan',{}).get('evidence',[]),
            current_input_sha256=state.get('input',{}).get('sha256'),
            current_input_extraction=state.get('input',{}).get('extraction'),
            require_current_assignment=True,
        )
    ]

def _artifact_format_error(path:Path,expected:str)->str | None:
    """Parse supported deliverables so renamed or corrupt bytes cannot pass."""
    expected=str(expected or '').casefold().lstrip('.')
    if path.suffix.casefold()!=f'.{expected}': return f'artifact extension does not match requested {expected} format'
    try:
        if expected=='pdf':
            from pypdf import PdfReader
            with path.open('rb') as handle:
                header=handle.read(5)
                handle.seek(max(0,path.stat().st_size-2048)); tail=handle.read()
            if header!=b'%PDF-' or b'%%EOF' not in tail: return 'artifact is not a valid pdf file'
            if len(PdfReader(str(path)).pages)<1: return 'PDF artifact contains no pages'
        elif expected in {'docx','xlsx'}:
            with zipfile.ZipFile(path) as archive:
                required='word/document.xml' if expected=='docx' else 'xl/workbook.xml'
                if required not in archive.namelist(): return f'artifact is not a valid {expected} file'
        elif expected=='png':
            from PIL import Image
            with Image.open(path) as image: image.verify()
        else: return f'unsupported deliverable format: {expected}'
    except Exception: return f'artifact is not a valid {expected} file'
    return None

def set_plan(workspace:Path,run_id:str,plan:dict)->dict:
    state=load_run(workspace,run_id); root=run_dir(workspace,run_id)
    if not isinstance(plan,dict) or not isinstance(plan.get('requirements'),list): raise ValueError('plan requires requirements list')
    requirement_ids=[r.get('id') for r in plan['requirements'] if isinstance(r,dict)]
    if any(not isinstance(value,str) or not value.strip() for value in requirement_ids) or len(requirement_ids)!=len(plan['requirements']):
        raise ValueError('every plan requirement needs a non-empty id')
    if len(set(requirement_ids))!=len(requirement_ids): raise ValueError('plan requirement ids must be unique')
    # A changed plan invalidates every downstream record.  Say which ones existed.
    _note_discarded(state,'set_plan',('solution','calculation checks','structured verifier report','deliverable artifacts','artifact inspections'))
    state['plan']=plan; state['plan_sha256']=digest(plan); state['requirements']=plan['requirements']; state['stage']='grounded'; state['unresolved']=[]
    state.pop('solution',None); state.pop('solution_sha256',None); state.pop('checks_for_solution_sha256',None)
    state.pop('verification_report',None); state.pop('verification_sha256',None)
    state['checks']=[]; state['artifacts']=[]
    if not plan['requirements']: state['unresolved'].append('requirements manifest is empty')
    atomic_json(root/'plan.json',plan)
    save_run(workspace,state); return state

_REQUIRED_VISUAL_CHECKS=('all_pages_reviewed','legible','requirements_present','identity_checked','no_clipping')

def _inspection_record_error(report,artifact_path,artifact_sha256)->str | None:
    """Return why a report cannot be recorded against this artifact at all, or None.

    These are the rules a report must satisfy to be a *record of an inspection*,
    separately from what it concludes.  A report about different bytes, or one
    that names nothing, is a mistake rather than a verdict, so ``inspect_artifact``
    still refuses it.  A report that merely fails its checks is a verdict, and is
    recorded: see ``_inspection_findings``.
    """
    if not isinstance(report,dict): return 'inspection report must be an object'
    if report.get('artifact_path')!=artifact_path or report.get('artifact_sha256')!=artifact_sha256:
        return 'inspection report does not match the registered artifact'
    if report.get('unresolved') is not None and not isinstance(report.get('unresolved'),list):
        return 'inspection report unresolved findings must be a list'
    if not isinstance(report.get('notes'),str) or not report['notes'].strip(): return 'inspection report needs substantive notes'
    return None

def _inspection_findings(report)->list[str]:
    """Return the recorded reasons a report does not certify its artifact.

    This is the only place the visual-inspection verdict rules are spelled out.
    ``readiness`` re-reads a saved report through this function, so a stored
    rejection cannot become acceptable later just because it is already in
    run.json, and an empty result is the only thing that certifies.
    """
    if not isinstance(report,dict): return []
    findings=[f'failed visual check: {key}' for key in _REQUIRED_VISUAL_CHECKS if report.get(key) is not True]
    unresolved=report.get('unresolved')
    if isinstance(unresolved,list): findings.extend(f'unresolved finding: {value}' for value in unresolved)
    elif unresolved is not None: findings.append('unresolved findings are not a list')
    return findings

def _artifact_bytes_changed(root:Path,artifact:dict)->bool:
    """Report whether the artifact on disk still matches its registered hash."""
    try:
        path=safe_relative(root,artifact['path'])
        return path.is_symlink() or not path.is_file() or sha256(path)!=artifact.get('sha256')
    except (KeyError,OSError,TypeError,ValueError): return True

def _inspection_status(root:Path,artifact)->dict:
    """Describe one artifact's inspection so a caller need not parse blockers.

    This summary must never claim more than ``readiness`` would certify, so it
    checks the artifact on disk too: a report that passed the bytes registered
    yesterday says nothing about the bytes sitting there now.
    """
    path=artifact.get('path') if isinstance(artifact,dict) else None
    report=artifact.get('inspection_report') if isinstance(artifact,dict) else None
    if not isinstance(report,dict): return {'artifact':path,'status':'not_inspected','findings':[]}
    findings=_inspection_findings(report)
    if artifact.get('inspection_sha256')!=digest(report) or report.get('artifact_sha256')!=artifact.get('sha256') or report.get('artifact_path')!=path:
        status='stale'
    elif findings: status='rejected'
    elif _inspection_record_error(report,path,artifact.get('sha256')) or artifact.get('inspected') is not True: status='stale'
    elif _artifact_bytes_changed(root,artifact): status='stale'
    else: status='passed'
    return {'artifact':path,'status':status,'findings':findings}

def readiness(state:dict, root:Path | None=None)->dict:
    blockers=[]
    # 'rejected' is a run someone inspected and turned down.  It is listed here only
    # so the blockers can say that instead of 'nobody looked'; the gate below is
    # re-derived from the artifact records and never trusts this stage.
    if state.get('stage') not in ('inspected','rejected','ready'): blockers.append('run has not reached inspected stage')
    if not state.get('plan',{}).get('requirements'): blockers.append('requirements manifest missing or empty')
    if not state.get('solution'): blockers.append('solution missing')
    if not state.get('artifacts'): blockers.append('deliverable artifacts missing')
    else:
        for artifact in state.get('artifacts',[]):
            if not isinstance(artifact,dict): blockers.append('artifact record is invalid'); continue
            report=artifact.get('inspection_report')
            if not isinstance(report,dict): blockers.append('one or more deliverable artifacts are not inspected'); continue
            if artifact.get('inspection_sha256')!=digest(report) or report.get('artifact_sha256')!=artifact.get('sha256') or report.get('artifact_path')!=artifact.get('path'):
                blockers.append('one or more artifact inspection reports are missing or stale'); continue
            # A saved report is re-read, never trusted: the verdicts it records are
            # re-derived here, and a recorded rejection names what the reviewer found
            # rather than reporting the sentence that means nobody looked.
            findings=_inspection_findings(report)
            if findings: blockers.append(f"inspection rejected {artifact.get('path')}: "+'; '.join(findings))
            elif _inspection_record_error(report,artifact.get('path'),artifact.get('sha256')):
                blockers.append('one or more artifact inspection reports do not certify the artifact')
            # The flag is checked independently of the report, and must stay that way:
            # record_solution clears it while leaving the passing report in place, so
            # folding these two branches together would let a re-recorded solution
            # reach ready on an inspection that predates it.
            elif artifact.get('inspected') is not True: blockers.append('one or more deliverable artifacts are not inspected')
    if state.get('unresolved'): blockers.extend(state['unresolved'])
    plan=state.get('plan')
    if isinstance(plan,dict):
        if state.get('plan_sha256')!=digest(plan): blockers.append('plan hash is missing or stale')
        deliverables=plan.get('deliverables')
        if not isinstance(deliverables,list) or not deliverables: blockers.append('requested deliverables are missing from the plan')
        elif any(not isinstance(item,dict) or not item.get('path') or not item.get('format') for item in deliverables):
            blockers.append('each requested deliverable needs a path and format')
        verification=plan.get('verification')
        if not isinstance(verification,dict) or not isinstance(verification.get('calculations_required'),bool):
            blockers.append('plan must declare whether reproducible calculations are required')
        elif verification['calculations_required'] is False and not str(verification.get('reason','')).strip():
            blockers.append('a non-calculation assignment needs a verification reason')
    solution=state.get('solution')
    if isinstance(solution,dict):
        solution_hash=digest(solution)
        if state.get('solution_sha256')!=solution_hash: blockers.append('solution hash is missing or stale')
        calculations=solution.get('calculations',[])
        if not isinstance(calculations,list): blockers.append('solution calculations must be a list')
        elif state.get('plan',{}).get('verification',{}).get('calculations_required') is True and not calculations:
            blockers.append('reproducible calculations are required but missing')
        elif calculations:
            expected_ids=[item.get('id') for item in calculations if isinstance(item,dict)]
            check_ids=[item.get('id') for item in state.get('checks',[]) if isinstance(item,dict)]
            if state.get('checks_for_solution_sha256')!=solution_hash: blockers.append('calculation checks are missing or stale')
            if len(expected_ids)!=len(calculations) or len(set(expected_ids))!=len(expected_ids) or any(not value for value in expected_ids):
                blockers.append('calculation ids must be present and unique')
            elif sorted(expected_ids)!=sorted(check_ids): blockers.append('calculation checks do not cover every calculation')
        for artifact in state.get('artifacts',[]):
            if isinstance(artifact,dict) and artifact.get('source_solution_sha256')!=solution_hash:
                blockers.append('one or more deliverable artifacts were rendered from a stale solution')
    if root is not None:
        root=Path(root)
        blockers.extend(_course_evidence_blockers(state,root))
        try:
            profile=load_course_profile(root.parent.parent,state.get('course',''))
            if state.get('plan',{}).get('course_profile_sha256')!=digest(profile):
                blockers.append('plan course profile is missing or stale')
        except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError):
            blockers.append('reviewed course profile is missing or invalid')
        source=state.get('input',{})
        try:
            input_path=safe_relative(root,source['path'])
            if input_path.is_symlink() or not input_path.is_file() or sha256(input_path)!=source.get('sha256'):
                blockers.append('assignment input is missing or changed')
        except (KeyError,TypeError,OSError,ValueError): blockers.append('assignment input is missing or changed')
        for filename,key,label in (('plan.json','plan_sha256','plan'),('solution.json','solution_sha256','solution'),('verification.json','verification_sha256','structured verifier report')):
            path=root/filename
            if key not in state: continue
            try:
                if path.is_symlink() or not path.is_file(): raise OSError
                value=json.loads(path.read_text())
                if digest(value)!=state.get(key): blockers.append(f'{label} record is missing or changed')
            except (OSError,ValueError,TypeError,json.JSONDecodeError): blockers.append(f'{label} record is missing or changed')
        for artifact in state.get('artifacts',[]):
            if not isinstance(artifact,dict) or not artifact.get('path'): continue
            try:
                path=safe_relative(root,artifact['path'])
                if path.is_symlink() or not path.is_file() or sha256(path)!=artifact.get('sha256'):
                    blockers.append('one or more deliverable artifacts are missing or changed')
            except (OSError,TypeError,ValueError): blockers.append('one or more deliverable artifacts are missing or changed')
        requested=state.get('plan',{}).get('deliverables',[])
        registered={item.get('path'):item for item in state.get('artifacts',[]) if isinstance(item,dict)}
        for item in requested if isinstance(requested,list) else []:
            if not isinstance(item,dict) or not item.get('path') or not item.get('format'): continue
            artifact=registered.get(item['path'])
            if artifact is None: blockers.append(f"requested deliverable is missing: {item['path']}"); continue
            try:
                path=safe_relative(root,item['path']); error=_artifact_format_error(path,item['format'])
                if error: blockers.append(error)
            except (OSError,TypeError,ValueError): blockers.append(f"requested deliverable is invalid: {item['path']}")
    else:
        # Without the run directory none of the evidence above can be checked
        # against disk.  Refuse to certify rather than report an unanchored ready.
        blockers.append('readiness cannot be certified without the run directory')
    required={r.get('id') for r in state.get('plan',{}).get('requirements',[]) if isinstance(r,dict) and r.get('id')}
    covered=set()
    for section in state.get('solution',{}).get('sections',[]) if isinstance(state.get('solution'),dict) else []:
        covered.update(section.get('requirement_ids',[]) if isinstance(section,dict) else [])
    missing=required-covered
    if missing: blockers.append('requirements without solution coverage: '+', '.join(sorted(missing)))
    for check in state.get('checks',[]):
        if check.get('passed') is not True: blockers.append(f"check failed: {check.get('id','unnamed')}")
    report=state.get('verification_report')
    if not isinstance(report,dict): blockers.append('structured verifier report is missing')
    else:
        try:
            validate_verification_report(state,report)
            if state.get('verification_sha256')!=digest(report): blockers.append('structured verifier report hash is stale')
        except (ValueError,KeyError,TypeError) as exc:
            blockers.append(f'structured verifier report is invalid: {exc}')
    return {'ready':not blockers,'blockers':list(dict.fromkeys(blockers))}

def record_solution(workspace:Path,run_id:str,solution:dict)->dict:
    state=load_run(workspace,run_id); root=run_dir(workspace,run_id)
    if not isinstance(solution,dict): raise ValueError('solution must be object')
    # Checks, the verifier report and every inspection describe the previous solution.
    _note_discarded(state,'record_solution',('calculation checks','structured verifier report','artifact inspections'))
    state['solution']=solution; state['solution_sha256']=digest(solution); state['stage']='solved'; state['unresolved']=list(solution.get('unresolved',[]))
    state['checks']=[]; state.pop('checks_for_solution_sha256',None); state.pop('verification_report',None); state.pop('verification_sha256',None)
    for artifact in state.get('artifacts',[]):
        if isinstance(artifact,dict): artifact['inspected']=False
    atomic_json(root/'solution.json',solution); save_run(workspace,state); return state

def record_checks(workspace:Path,run_id:str,checks:list[dict])->dict:
    if not isinstance(checks,list) or any(not isinstance(check,dict) for check in checks): raise ValueError('checks must be a list of objects')
    state=load_run(workspace,run_id)
    _note_discarded(state,'record_checks',('structured verifier report',))
    state['checks']=checks; state['checks_for_solution_sha256']=state.get('solution_sha256'); state.pop('verification_report',None); state.pop('verification_sha256',None); state['stage']='checked'; save_run(workspace,state); return state

def record_verification_report(workspace:Path,run_id:str,report:dict)->dict:
    state=load_run(workspace,run_id)
    validated=validate_verification_report(state,report)
    state['verification_report']=validated; state['verification_sha256']=digest(validated); state['stage']='verified'
    atomic_json(run_dir(workspace,run_id)/'verification.json',validated); save_run(workspace,state); return state

def record_artifact(workspace:Path,run_id:str,path:Path)->dict:
    state=load_run(workspace,run_id); root=run_dir(workspace,run_id)
    if path.is_symlink() or not path.is_file(): raise ValueError('artifact is not a safe regular file')
    rel=path.resolve().relative_to(root.resolve()).as_posix()
    requested=next((item for item in state.get('plan',{}).get('deliverables',[]) if isinstance(item,dict) and item.get('path')==rel),None)
    if requested is None: raise ValueError('artifact is not declared in the assignment plan')
    format_error=_artifact_format_error(path,requested.get('format'))
    if format_error: raise ValueError(format_error)
    value={'path':rel,'sha256':sha256(path),'source_solution_sha256':state.get('solution_sha256'),'inspected':False}
    existing=next((a for a in state.setdefault('artifacts',[]) if a.get('path')==rel),None)
    # Re-registering replaces this artifact's own inspection; the others keep theirs.
    _note_discarded(state,'record_artifact',('structured verifier report',),
                    (f'inspection of {rel}',) if existing is not None and isinstance(existing.get('inspection_report'),dict) else ())
    if existing is None: state['artifacts'].append(value)
    else: existing.clear(); existing.update(value)
    state.pop('verification_report',None); state.pop('verification_sha256',None)
    state['stage']='rendered'; save_run(workspace,state); return state

def inspect_artifact(workspace:Path,run_id:str,artifact:str,report:dict)->dict:
    state=load_run(workspace,run_id); root=run_dir(workspace,run_id)
    found=next((a for a in state.get('artifacts',[]) if a.get('path')==artifact),None)
    if found is None: raise ValueError('artifact not registered')
    error=_inspection_record_error(report,artifact,found.get('sha256'))
    if error: raise ValueError(error)
    path=root/artifact
    if not path.is_file() or path.is_symlink(): raise ValueError('artifact is missing or unsafe')
    if sha256(path)!=found.get('sha256'): raise ValueError('artifact changed after registration; render or register it again before inspection')
    # The report is stored whatever it concludes: a rejection is the outcome this
    # gate exists to produce, and losing it is what made 'rejected' look like
    # 'nobody looked'.  Only an empty findings list marks the artifact inspected.
    findings=_inspection_findings(report)
    found['inspected']=not findings; found['inspection_report']=report; found['inspection_sha256']=digest(report)
    rejected=[a for a in state.get('artifacts',[]) if isinstance(a,dict) and _inspection_findings(a.get('inspection_report'))]
    state['stage']='rejected' if rejected else 'inspected'; state['inspection_at']=now(); save_run(workspace,state)
    result=readiness(state,root)
    if result['ready']: state['stage']='ready'; save_run(workspace,state)
    # Recording a rejection succeeds, so the verdict leads the returned record
    # rather than hiding inside it: this is what the CLI prints.
    return {'inspection':'rejected' if findings else 'passed','artifact':artifact,'findings':findings,'state':state,'readiness':result}

def status_run(workspace:Path,run_id:str)->dict:
    state=load_run(workspace,run_id); root=run_dir(workspace,run_id)
    current=readiness(state,root)
    effective='ready' if current['ready'] else ('stale' if state.get('stage')=='ready' else state.get('stage'))
    inspections=[_inspection_status(root,artifact) for artifact in state.get('artifacts',[]) if isinstance(artifact,dict)]
    return {'state':state,'effective_stage':effective,'readiness':current,'inspections':inspections,'discarded':state.get('discarded',[])}
