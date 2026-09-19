from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from .common import atomic_json,digest,permitted_source,read_json
from .ingest import MAX_OCR_IMPORT_BYTES,auto_ocr_document,import_ocr_transcription,ingest,ocr_status,search
from .matching import match_examples,register_example
from .adaptation import build_adaptation_manifest
from .identity import run_identity
from .memory import forget_memory,list_memory,set_memory
from .runtime import *
from .artifact_rendering import render_declared_artifacts
from .verification import verify_solution
from .course_profile import course_coverage,course_onboarding_status,load_course_profile,set_course_profile
from .evidence import review_evidence
from .evaluation import evaluate_manifest
from .doctor import diagnose
from .curriculum import DEFAULT_CURRICULUM,coverage_report,load_packs,load_tool_packs

def _json_input(path:Path,max_bytes:int|None=None)->dict:
 if not path.is_file() or path.is_symlink() or not permitted_source(path): raise ValueError('JSON input must be a permitted regular file')
 if max_bytes is not None and path.stat().st_size>max_bytes: raise ValueError('JSON input exceeds the permitted size')
 return read_json(path)

def main(argv=None):
 p=argparse.ArgumentParser(prog='coursework'); p.add_argument('--workspace',type=Path,default=Path('workspace')); sub=p.add_subparsers(dest='cmd',required=True)
 q=sub.add_parser('ingest'); q.add_argument('source',type=Path); q.add_argument('--course',required=True); q.add_argument('--max-files',type=int,default=50); q.add_argument('--max-pages',type=int,default=100)
 q=sub.add_parser('search'); q.add_argument('query'); q.add_argument('--course',required=True); q.add_argument('--limit',type=int,default=8)
 q=sub.add_parser('ocr-status'); q.add_argument('--course',required=True)
 q=sub.add_parser('ocr-import'); q.add_argument('transcription',type=Path); q.add_argument('--course',required=True)
 q=sub.add_parser('ocr-run',help='transcribe one pending scan of PRINTED pages with the local OCR engine; handwriting and photographed worksheets go through ocr-import instead',description='Transcribe one pending source (ids from ocr-status) with the local OCR engine: Tesseract when installed, else RapidOCR. For bulk scans of printed pages only; neither engine reads handwriting reliably, so a handwritten or photographed worksheet is read by the host and recorded with ocr-import. The text is imported unreviewed and fails closed.'); q.add_argument('--course',required=True); q.add_argument('--document-id',required=True)
 q=sub.add_parser('example-add'); q.add_argument('example',type=Path); q.add_argument('--course',required=True)
 q=sub.add_parser('match'); q.add_argument('assignment',type=Path); q.add_argument('--course',required=True); q.add_argument('--limit',type=int,default=3)
 q=sub.add_parser('start'); q.add_argument('assignment',type=Path); q.add_argument('--course',required=True); q.add_argument('--run-id',required=True); q.add_argument('--display-name',help='optional private run display name'); q.add_argument('--student-id',help='optional private run identifier')
 q=sub.add_parser('accept-plan'); q.add_argument('run_id'); q.add_argument('plan',type=Path)
 q=sub.add_parser('record-solution'); q.add_argument('run_id'); q.add_argument('solution',type=Path)
 q=sub.add_parser('render'); q.add_argument('run_id'); q.add_argument('solution',type=Path)
 q=sub.add_parser('verify'); q.add_argument('run_id')
 q=sub.add_parser('verify-report'); q.add_argument('run_id'); q.add_argument('report',type=Path)
 q=sub.add_parser('inspect'); q.add_argument('run_id'); q.add_argument('--artifact',required=True); q.add_argument('--report',required=True,type=Path)
 q=sub.add_parser('status'); q.add_argument('run_id')
 q=sub.add_parser('profile-set'); q.add_argument('profile',type=Path); q.add_argument('--course',required=True)
 q=sub.add_parser('profile-show'); q.add_argument('--course',required=True)
 q=sub.add_parser('evidence-review'); q.add_argument('--course',required=True); q.add_argument('--document-id',required=True); q.add_argument('--locator',required=True); q.add_argument('--notes',required=True)
 q=sub.add_parser('evidence-queue'); q.add_argument('--course',required=True)
 q=sub.add_parser('onboarding-status'); q.add_argument('--course',required=True)
 q=sub.add_parser('coverage'); q.add_argument('--course',required=True); q.add_argument('--expected',type=Path,help='optional JSON naming assignment_families, methods and formatting_rules to check')
 q=sub.add_parser('evaluate'); q.add_argument('manifest',type=Path); q.add_argument('--out',type=Path)
 q=sub.add_parser('doctor'); q.add_argument('--project-root',type=Path,default=Path('.'))
 q=sub.add_parser('courses'); q.add_argument('--curriculum',type=Path,default=DEFAULT_CURRICULUM)
 q=sub.add_parser('adapt'); q.add_argument('current',type=Path); q.add_argument('prior',type=Path); q.add_argument('--out',type=Path); q.add_argument('--name'); q.add_argument('--student-id')
 q=sub.add_parser('init'); q.add_argument('--name'); q.add_argument('--student-id')
 q=sub.add_parser('memory'); m=q.add_subparsers(dest='memory_cmd',required=True)
 m.add_parser('list')
 s=m.add_parser('set'); s.add_argument('key'); s.add_argument('value'); s.add_argument('--scope',required=True); s.add_argument('--source',required=True)
 f=m.add_parser('forget'); f.add_argument('key')
 args=p.parse_args(argv); ws=args.workspace
 try:
  if args.cmd=='ingest': out=ingest(args.source,ws,args.course,args.max_files,args.max_pages)
  elif args.cmd=='search': out=search(ws,args.course,args.query,args.limit)
  elif args.cmd=='ocr-status': out=ocr_status(ws,args.course)
  elif args.cmd=='ocr-run': out=auto_ocr_document(ws,args.course,args.document_id)
  elif args.cmd=='ocr-import': out=import_ocr_transcription(ws,args.course,_json_input(args.transcription,MAX_OCR_IMPORT_BYTES))
  elif args.cmd=='example-add': out=register_example(ws,args.course,_json_input(args.example))
  elif args.cmd=='match': out=match_examples(ws,args.course,_json_input(args.assignment),args.limit)
  elif args.cmd=='start': out=start_run(ws,args.run_id,args.course,args.assignment,display_name=args.display_name,student_id=args.student_id)
  elif args.cmd=='accept-plan': out=set_plan(ws,args.run_id,_json_input(args.plan))
  elif args.cmd=='record-solution': out=record_solution(ws,args.run_id,_json_input(args.solution))
  elif args.cmd=='render':
   st=record_solution(ws,args.run_id,_json_input(args.solution)); profile=load_course_profile(ws,st['course'])
   paths=render_declared_artifacts(st['solution'],st['plan'],run_dir(ws,args.run_id),identity=st.get('identity'),style_profile=profile)
   for outpath in paths: out=record_artifact(ws,args.run_id,outpath)
  elif args.cmd=='verify':
   st=load_run(ws,args.run_id); out=record_checks(ws,args.run_id,verify_solution(st.get('solution',{})))
  elif args.cmd=='verify-report': out=record_verification_report(ws,args.run_id,_json_input(args.report))
  elif args.cmd=='inspect': out=inspect_artifact(ws,args.run_id,args.artifact,_json_input(args.report))
  elif args.cmd=='status': out=status_run(ws,args.run_id)
  elif args.cmd=='profile-set': out=set_course_profile(ws,args.course,_json_input(args.profile))
  elif args.cmd=='profile-show':
   value=load_course_profile(ws,args.course); out={'profile':value,'sha256':digest(value)}
  elif args.cmd=='evidence-review': out=review_evidence(ws,args.course,args.document_id,args.locator,args.notes)
  elif args.cmd=='evidence-queue': out=course_onboarding_status(ws,args.course)['review_queue']
  elif args.cmd=='onboarding-status': out=course_onboarding_status(ws,args.course)
  elif args.cmd=='coverage': out=course_coverage(ws,args.course,_json_input(args.expected) if args.expected else None)
  elif args.cmd=='evaluate':
   out=evaluate_manifest(ws,_json_input(args.manifest))
   if args.out:
    if args.out.is_symlink() or not permitted_source(args.out): raise ValueError('evaluation output path is not permitted')
    atomic_json(args.out,out)
  elif args.cmd=='doctor':
   project=args.project_root.resolve(); doctor_workspace=ws if ws.is_absolute() else project/ws
   out=diagnose(project,doctor_workspace)
  elif args.cmd=='courses':
   # Shipped-pack coverage, not workspace state: what this install can honestly
   # claim about a course before the student has ingested anything.
   out=coverage_report(load_packs(args.curriculum),load_tool_packs(args.curriculum))
  elif args.cmd=='adapt':
   current=_json_input(args.current); prior=_json_input(args.prior); out=build_adaptation_manifest(current,prior,{'name':args.name,'student_id':args.student_id})
   if args.out:
    if args.out.is_symlink() or not permitted_source(args.out): raise ValueError('adaptation output path is not permitted')
    atomic_json(args.out,out)
  elif args.cmd=='init':
   (ws/'student'/'memory').mkdir(parents=True,exist_ok=True)
   identity=run_identity(args.name,args.student_id)
   atomic_json(ws/'student'/'profile.json',{'schema_version':1,'identity':identity,'memory_policy':'explicit_updates_only'})
   (ws/'student'/'memory'/'index.md').write_text('# Student memory\n\nOnly explicit, reviewed project preferences belong here.\n')
   out={'workspace':str(ws),'profile':'student/profile.json','identity':identity}
  elif args.cmd=='memory':
   if args.memory_cmd=='list': out=list_memory(ws)
   elif args.memory_cmd=='set': out=set_memory(ws,args.key,args.value,scope=args.scope,source=args.source)
   elif args.memory_cmd=='forget': out=forget_memory(ws,args.key)
 except (OSError,ValueError,KeyError,json.JSONDecodeError) as exc:
  p.error(str(exc))
 print(json.dumps(out,indent=2,default=str)); return 0

if __name__=='__main__': raise SystemExit(main())
