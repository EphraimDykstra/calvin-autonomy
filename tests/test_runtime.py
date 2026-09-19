import hashlib,io,json,tempfile,unittest,zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from engineering_assistant.runtime import *
from engineering_assistant.calculations import evaluate,check_calculation
from engineering_assistant.course_profile import set_course_profile
from engineering_assistant.verification import build_verification_report
from engineering_assistant.evidence import review_evidence
from engineering_assistant.rendering import render_text_pdf
from engineering_assistant.cli import main as cli_main

class RuntimeTests(unittest.TestCase):
 def plan(self,workspace,source,deliverables=None):
  text='Reviewed course method.'; document_id='guide-1'
  atomic_json(Path(workspace)/'courses'/'demo'/'catalog.json',{'course':'demo','documents':[{'id':document_id,'sha256':'guide-hash','active':True,'status':'extracted','blocks':[{'locator':'page:1','text':text}]}]})
  course_evidence={'document_id':document_id,'source_sha256':'guide-hash','locator':'page:1','text_sha256':hashlib.sha256(text.encode()).hexdigest(),'review_status':'reviewed'}
  review_evidence(workspace,'demo',document_id,'page:1','Reviewed method statement and its course context.')
  profile=set_course_profile(workspace,'demo',{'schema_version':1,'review_status':'reviewed','precedence':['current_assignment','reviewed_course_guidance'],'rules':{'reporting':'concise'},'rendering':{'body_font_size':11,'line_spacing':1.2,'margin_inches':1,'title_page':True,'abstract':True,'number_body_pages':True,'table_captions_above':True,'figure_captions_below':True},'evidence':[course_evidence]})
  return {
   'requirements':[{'id':'q1','text':'answer'}],
   'evidence':[
    {'document_id':'current-assignment','source_sha256':sha256(source),'locator':'line:1','text_sha256':hashlib.sha256(source.read_text().encode()).hexdigest()},
    course_evidence,
   ],
   'course_profile_sha256':profile['sha256'],
   'deliverables':deliverables or [{'path':'deliverables/submission.pdf','format':'pdf'}],
   'verification':{'calculations_required':False,'reason':'test fixture covers a prose-only requirement'},
  }

 def inspection(self,path,relative):
  return {'artifact_path':relative,'artifact_sha256':sha256(path),'all_pages_reviewed':True,'legible':True,'requirements_present':True,'identity_checked':True,'no_clipping':True,'unresolved':[],'notes':'Reviewed every rendered page, equation, table, and page break.'}

 def verifier_report(self,workspace,run_id):
  state=load_run(workspace,run_id)
  report=build_verification_report(
   state,
   requirement_findings=[{'requirement_id':item['id'],'passed':True,'evidence':['solution.sections'],'notes':'Requirement is covered by the current solution.'} for item in state['plan']['requirements']],
   method_checks=[{'id':'course-method','passed':True,'notes':'Method matches reviewed course evidence.'}],
   numerical_checks=[{'id':'calculation-record','passed':True,'notes':'Required calculations are checked, or the plan documents why none are required.'}],
   format_checks=[{'id':'declared-format','passed':True,'notes':'Registered artifacts match the declared deliverable format.'}],
   identity_checks=[{'id':'placeholder-identity','passed':True,'notes':'Only approved run identity fields are present.'}],
  )
  return record_verification_report(workspace,run_id,report)

 def ready_run(self,workspace,source,run_id):
  """Drive a run all the way to a genuine ready state."""
  start_run(workspace,run_id,'demo',source); set_plan(workspace,run_id,self.plan(workspace,source))
  record_solution(workspace,run_id,{'sections':[{'requirement_ids':['q1']}],'calculations':[],'unresolved':[]}); record_checks(workspace,run_id,[])
  run=run_dir(workspace,run_id); artifact=run/'deliverables'/'submission.pdf'
  render_text_pdf({'title':'Result','sections':[{'body':'answer'}]},artifact)
  record_artifact(workspace,run_id,artifact); self.verifier_report(workspace,run_id)
  inspect_artifact(workspace,run_id,'deliverables/submission.pdf',self.inspection(artifact,'deliverables/submission.pdf'))
  self.assertTrue(status_run(workspace,run_id)['readiness']['ready'])
  return run,artifact

 def test_calculation_rejects_code_and_checks_units(self):
  self.assertAlmostEqual(evaluate('a*(b+2)',{'a':3,'b':4}),18)
  self.assertRaises(ValueError,evaluate,"__import__('os')",{})
  self.assertTrue(check_calculation({'id':'x','expression':'2+2','expected':4,'unit':'N'})['passed'])
  self.assertFalse(check_calculation({'id':'x','expression':'2+2','expected':5,'unit':'N'})['passed'])
 def test_run_only_ready_after_checks_and_inspection(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment')
   s=start_run(root/'w','r1','demo',source)
   set_plan(root/'w','r1',self.plan(root/'w',source))
   record_solution(root/'w','r1',{'title':'x','sections':[{'heading':'Answer','body':'4','requirement_ids':['q1']}],'calculations':[],'unresolved':[]})
   record_checks(root/'w','r1',[])
   self.assertFalse(readiness(load_run(root/'w','r1'))['ready'])
   p=run_dir(root/'w','r1')/'deliverables'/'submission.pdf'; render_text_pdf({'title':'Result','sections':[{'body':'4'}]},p)
   record_artifact(root/'w','r1',p)
   self.verifier_report(root/'w','r1')
   result=inspect_artifact(root/'w','r1','deliverables/submission.pdf',self.inspection(p,'deliverables/submission.pdf'))
   self.assertTrue(result['readiness']['ready'])
 def test_renderer_produces_pdf(self):
  with tempfile.TemporaryDirectory() as d:
   out=render_text_pdf({'title':'Test','sections':[{'heading':'Results','body':'Concise result.'}]},Path(d)/'x.pdf')
   self.assertTrue(out.read_bytes().startswith(b'%PDF'))
 def test_renderer_produces_course_style_technical_report(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'run'; out=root/'deliverables'/'report.pdf'
   solution={'document_type':'technical_report','title':'Heat Transfer Lab','metadata':{'course':'ENGR 328','date':'[Date]'},'abstract':'Measured and calculated results are summarized.','sections':[{'heading':'Results','body':'All reported quantities include units.','equations':['q = m cp DeltaT'],'tables':[{'caption':'Table 1: Energy balance results.','headers':['Quantity','Value','Unit'],'rows':[['Heat rate','10.2','kW']]}]}],'appendices':[{'heading':'Appendix A: Calculations','body':'Calculation record.'}]}
   render_text_pdf(solution,out)
   self.assertTrue(out.read_bytes().startswith(b'%PDF'))
   self.assertGreater(out.stat().st_size,1500)
 def test_changed_artifact_must_be_reregistered_and_all_artifacts_inspected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   deliverables=[{'path':'deliverables/a.pdf','format':'pdf'},{'path':'deliverables/b.pdf','format':'pdf'}]
   start_run(workspace,'r2','demo',source); set_plan(workspace,'r2',self.plan(workspace,source,deliverables))
   record_solution(workspace,'r2',{'sections':[{'requirement_ids':['q1']}],'calculations':[],'unresolved':[]}); record_checks(workspace,'r2',[])
   run=run_dir(workspace,'r2'); a=run/'deliverables'/'a.pdf'; b=run/'deliverables'/'b.pdf'; render_text_pdf({'title':'A','sections':[{'body':'a'}]},a); render_text_pdf({'title':'B','sections':[{'body':'b'}]},b)
   record_artifact(workspace,'r2',a); record_artifact(workspace,'r2',b); a.write_bytes(a.read_bytes()+b'changed')
   with self.assertRaises(ValueError): inspect_artifact(workspace,'r2','deliverables/a.pdf',self.inspection(a,'deliverables/a.pdf'))
   record_artifact(workspace,'r2',a); self.assertEqual(len(load_run(workspace,'r2')['artifacts']),2); self.verifier_report(workspace,'r2')
   first=inspect_artifact(workspace,'r2','deliverables/a.pdf',self.inspection(a,'deliverables/a.pdf')); self.assertFalse(first['readiness']['ready'])
   second=inspect_artifact(workspace,'r2','deliverables/b.pdf',self.inspection(b,'deliverables/b.pdf')); self.assertTrue(second['readiness']['ready'])

 def test_cli_renders_and_gates_all_declared_pdf_docx_and_xlsx_artifacts(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   deliverables=[
    {'path':'deliverables/submission.pdf','format':'pdf'},
    {'path':'deliverables/submission.docx','format':'docx'},
    {'path':'deliverables/results.xlsx','format':'xlsx'},
   ]
   start_run(workspace,'multi','demo',source); set_plan(workspace,'multi',self.plan(workspace,source,deliverables))
   solution={'title':'Result','sections':[{'heading':'Answer','body':'4','requirement_ids':['q1']}],'calculations':[],'unresolved':[]}
   solution_path=root/'solution.json'; atomic_json(solution_path,solution)
   with redirect_stdout(io.StringIO()):
    self.assertEqual(cli_main(['--workspace',str(workspace),'render','multi',str(solution_path)]),0)
   state=load_run(workspace,'multi')
   self.assertEqual({item['path'] for item in state['artifacts']},{item['path'] for item in deliverables})
   record_checks(workspace,'multi',[]); self.verifier_report(workspace,'multi')
   for index,item in enumerate(deliverables):
    path=run_dir(workspace,'multi')/item['path']
    result=inspect_artifact(workspace,'multi',item['path'],self.inspection(path,item['path']))
    self.assertEqual(result['readiness']['ready'],index==len(deliverables)-1)

 def test_integrity_gates_stale_input_plan_solution_checks_and_artifact(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   start_run(workspace,'integrity','demo',source); plan=self.plan(workspace,source); set_plan(workspace,'integrity',plan)
   solution={'sections':[{'requirement_ids':['q1']}],'calculations':[{'id':'sum','expression':'2+2','expected':4,'unit':'dimensionless'}],'unresolved':[]}
   record_solution(workspace,'integrity',solution)
   record_checks(workspace,'integrity',[check_calculation(solution['calculations'][0])])
   run=run_dir(workspace,'integrity'); artifact=run/'deliverables'/'submission.pdf'; render_text_pdf({'title':'Current','sections':[{'body':'result'}]},artifact)
   record_artifact(workspace,'integrity',artifact)
   self.verifier_report(workspace,'integrity')
   self.assertTrue(inspect_artifact(workspace,'integrity','deliverables/submission.pdf',self.inspection(artifact,'deliverables/submission.pdf'))['readiness']['ready'])

   (run/'input'/'a.txt').write_text('changed')
   self.assertIn('assignment input is missing or changed',readiness(load_run(workspace,'integrity'),run)['blockers'])
   (run/'input'/'a.txt').write_text('assignment')
   (run/'plan.json').write_text('{}')
   self.assertIn('plan record is missing or changed',readiness(load_run(workspace,'integrity'),run)['blockers'])
   atomic_json(run/'plan.json',plan)
   (run/'solution.json').write_text('{}')
   self.assertIn('solution record is missing or changed',readiness(load_run(workspace,'integrity'),run)['blockers'])
   atomic_json(run/'solution.json',solution)
   verification=load_run(workspace,'integrity')['verification_report']; (run/'verification.json').write_text('{}')
   self.assertIn('structured verifier report record is missing or changed',readiness(load_run(workspace,'integrity'),run)['blockers'])
   atomic_json(run/'verification.json',verification)
   artifact.write_bytes(b'%PDF-stale')
   self.assertIn('one or more deliverable artifacts are missing or changed',readiness(load_run(workspace,'integrity'),run)['blockers'])

 def test_solution_change_invalidates_checks_and_artifacts(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   start_run(workspace,'stale','demo',source); set_plan(workspace,'stale',self.plan(workspace,source))
   first={'sections':[{'requirement_ids':['q1']}],'calculations':[{'id':'a','expression':'2+2','expected':4,'unit':'dimensionless'}]}
   record_solution(workspace,'stale',first); record_checks(workspace,'stale',[check_calculation(first['calculations'][0])])
   run=run_dir(workspace,'stale'); artifact=run/'deliverables'/'submission.pdf'; render_text_pdf({'title':'First','sections':[{'body':'result'}]},artifact)
   record_artifact(workspace,'stale',artifact)
   self.verifier_report(workspace,'stale')
   second={'sections':[{'requirement_ids':['q1']}],'calculations':[{'id':'b','expression':'3+3','expected':6,'unit':'dimensionless'}]}
   state=record_solution(workspace,'stale',second)
   self.assertEqual(state['checks'],[]); self.assertFalse(state['artifacts'][0]['inspected'])
   blockers=readiness(state,run)['blockers']
   self.assertIn('calculation checks are missing or stale',blockers)
   self.assertIn('one or more deliverable artifacts were rendered from a stale solution',blockers)

 def test_plan_requires_unique_ids_and_run_ids_do_not_overwrite(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   start_run(workspace,'r1','demo',source)
   with self.assertRaises(ValueError): start_run(workspace,'r1','demo',source)
   with self.assertRaises(ValueError): set_plan(workspace,'r1',{'requirements':[{'id':'q','text':'a'},{'id':'q','text':'b'}]})

 def test_false_ready_inputs_are_rejected_or_blocked(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   start_run(workspace,'unsafe','demo',source); plan=self.plan(workspace,source); plan['evidence'][1]['locator']='page:999'; plan['verification']={'calculations_required':True}; set_plan(workspace,'unsafe',plan)
   record_solution(workspace,'unsafe',{'sections':[{'requirement_ids':['q1']}],'calculations':[],'unresolved':[]}); record_checks(workspace,'unsafe',[])
   run=run_dir(workspace,'unsafe'); artifact=run/'deliverables'/'submission.pdf'; artifact.parent.mkdir(); artifact.write_bytes(b'not a pdf')
   with self.assertRaisesRegex(ValueError,'valid pdf'): record_artifact(workspace,'unsafe',artifact)
   render_text_pdf({'title':'Result','sections':[{'body':'answer'}]},artifact); record_artifact(workspace,'unsafe',artifact); self.verifier_report(workspace,'unsafe')
   bad_report=self.inspection(artifact,'deliverables/submission.pdf'); bad_report['legible']=False
   # The failing verdict is now recorded rather than refused (#28), and still blocks.
   rejected=inspect_artifact(workspace,'unsafe','deliverables/submission.pdf',bad_report)
   self.assertFalse(rejected['readiness']['ready'])
   self.assertIn('inspection rejected deliverables/submission.pdf: failed visual check: legible',rejected['readiness']['blockers'])
   result=inspect_artifact(workspace,'unsafe','deliverables/submission.pdf',self.inspection(artifact,'deliverables/submission.pdf'))
   self.assertFalse(result['readiness']['ready'])
   self.assertTrue(any('locator or text hash is stale' in value for value in result['readiness']['blockers']))
   self.assertIn('reproducible calculations are required but missing',result['readiness']['blockers'])

 def test_status_recomputes_readiness_after_artifact_mutation(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   start_run(workspace,'status','demo',source); set_plan(workspace,'status',self.plan(workspace,source))
   record_solution(workspace,'status',{'sections':[{'requirement_ids':['q1']}],'calculations':[],'unresolved':[]}); record_checks(workspace,'status',[])
   run=run_dir(workspace,'status'); artifact=run/'deliverables'/'submission.pdf'; render_text_pdf({'title':'Result','sections':[{'body':'answer'}]},artifact); record_artifact(workspace,'status',artifact); self.verifier_report(workspace,'status')
   inspect_artifact(workspace,'status','deliverables/submission.pdf',self.inspection(artifact,'deliverables/submission.pdf'))
   self.assertTrue(status_run(workspace,'status')['readiness']['ready'])
   artifact.write_bytes(artifact.read_bytes()+b'changed')
   status=status_run(workspace,'status'); self.assertFalse(status['readiness']['ready']); self.assertEqual(status['effective_stage'],'stale')
   # The inspection summary must not report a pass on bytes that have since changed.
   self.assertEqual(status['inspections'][0]['status'],'stale')

 def test_readiness_rereads_saved_inspection_verdicts(self):
  """A saved report that fails a visual check must never certify an artifact."""
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   run,artifact=self.ready_run(workspace,source,'verdicts')
   honest=self.inspection(artifact,'deliverables/submission.pdf')
   degraded=({'legible':False},{'all_pages_reviewed':False},{'requirements_present':False},{'identity_checked':False},{'no_clipping':False},{'unresolved':['page 3 is unreadable']},{'notes':'   '})
   # A report that records no findings at all is still refused at the point of
   # inspection; a report that records a rejection is stored instead (#28).  What
   # neither may ever do is certify the artifact, which is what this test guards.
   unrecordable=({'notes':'   '},)
   for mutation in degraded:
    if mutation in unrecordable:
     with self.assertRaises(ValueError,msg=mutation):
      inspect_artifact(workspace,'verdicts','deliverables/submission.pdf',{**honest,**mutation})
    # A report saved by any other writer is re-read, not trusted.
    # Every hash stays self-consistent; only the recorded verdicts degrade.
    state=load_run(workspace,'verdicts'); record=state['artifacts'][0]
    report={**honest,**mutation}; record['inspection_report']=report; record['inspection_sha256']=digest(report)
    save_run(workspace,state)
    status=status_run(workspace,'verdicts')
    self.assertFalse(status['readiness']['ready'],mutation)
    self.assertEqual(status['effective_stage'],'stale',mutation)
    # The saved inspected flag still reads True; only re-reading the report blocks.
    self.assertIs(load_run(workspace,'verdicts')['artifacts'][0]['inspected'],True,mutation)
    if mutation in unrecordable:
     self.assertIn('one or more artifact inspection reports do not certify the artifact',status['readiness']['blockers'],mutation)
    else:
     self.assertTrue(any(value.startswith('inspection rejected') for value in status['readiness']['blockers']),mutation)

 def test_readiness_without_the_run_directory_cannot_certify(self):
  """Readiness must fail closed when it cannot check the run against disk."""
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   run,artifact=self.ready_run(workspace,source,'anchor')
   state=load_run(workspace,'anchor')
   self.assertTrue(readiness(state,run)['ready'])
   unanchored=readiness(state)
   self.assertFalse(unanchored['ready'])
   self.assertIn('readiness cannot be certified without the run directory',unanchored['blockers'])
   # Destroying every anchored record must not become invisible without a root.
   artifact.write_bytes(b'not a pdf at all')
   (run/'input'/'a.txt').write_text('a different assignment')
   for name in ('plan.json','solution.json','verification.json'): (run/name).write_text('{}')
   state=load_run(workspace,'anchor')
   self.assertFalse(readiness(state,run)['ready'])
   self.assertFalse(readiness(state)['ready'])

 def test_course_profile_change_after_ready_makes_the_run_stale(self):
  """An upstream reviewed-profile edit must invalidate an already ready run."""
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   self.ready_run(workspace,source,'upstream')
   path=workspace/'courses'/'demo'/'profile.json'
   profile=json.loads(path.read_text()); profile['rules']={'reporting':'verbose'}; atomic_json(path,profile)
   status=status_run(workspace,'upstream')
   self.assertFalse(status['readiness']['ready'])
   self.assertEqual(status['effective_stage'],'stale')
   self.assertIn('plan course profile is missing or stale',status['readiness']['blockers'])

 def test_declared_format_rejects_truncated_disguised_and_compressed_payloads(self):
  """Malformed or hostile bytes must not register as a deliverable."""
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   deliverables=[{'path':'deliverables/submission.pdf','format':'pdf'},{'path':'deliverables/book.xlsx','format':'xlsx'}]
   start_run(workspace,'formats','demo',source); set_plan(workspace,'formats',self.plan(workspace,source,deliverables))
   record_solution(workspace,'formats',{'sections':[{'requirement_ids':['q1']}],'calculations':[],'unresolved':[]}); record_checks(workspace,'formats',[])
   run=run_dir(workspace,'formats'); pdf=run/'deliverables'/'submission.pdf'
   render_text_pdf({'title':'Real','sections':[{'body':'answer'}]},pdf); valid=pdf.read_bytes()
   for label,payload in (
    ('empty file',b''),
    ('truncated pdf',valid[:len(valid)//3]),
    ('header only',b'%PDF-1.4\n'),
    ('garbage wearing a pdf header and trailer',b'%PDF-'+b'\x00'*512+b'%%EOF'),
    ('zip renamed to pdf',b'PK\x03\x04'+b'\x00'*64),
   ):
    pdf.write_bytes(payload)
    with self.assertRaises(ValueError,msg=label): record_artifact(workspace,'formats',pdf)
   # A compressed payload is judged on its manifest alone and never expanded.
   book=run/'deliverables'/'book.xlsx'
   with zipfile.ZipFile(book,'w',zipfile.ZIP_DEFLATED) as archive: archive.writestr('payload.bin',b'\0'*(4*1024*1024))
   self.assertLess(book.stat().st_size,64*1024)
   with patch.object(zipfile.ZipFile,'read',side_effect=AssertionError('archive contents were decompressed')):
    with self.assertRaisesRegex(ValueError,'not a valid xlsx file'): record_artifact(workspace,'formats',book)

 def verified_run(self,workspace,source,run_id,solution=None):
  """Drive a run to the verified stage, with real calculations and checks."""
  solution=solution or {'title':'Result','sections':[{'heading':'Answer','body':'4','requirement_ids':['q1']}],'calculations':[{'id':'sum','expression':'2+2','expected':4,'unit':'dimensionless'}],'unresolved':[]}
  start_run(workspace,run_id,'demo',source); set_plan(workspace,run_id,self.plan(workspace,source))
  record_solution(workspace,run_id,solution)
  record_checks(workspace,run_id,[check_calculation(item) for item in solution['calculations']])
  run=run_dir(workspace,run_id); artifact=run/'deliverables'/'submission.pdf'
  render_text_pdf({'title':'Result','sections':[{'body':'4'}]},artifact)
  record_artifact(workspace,run_id,artifact); self.verifier_report(workspace,run_id)
  return run,artifact,solution

 def rejection(self,path,relative):
  """A report from a reviewer who opened the artifact and found real defects."""
  report=self.inspection(path,relative)
  report['legible']=False
  report['unresolved']=['figure 2 is illegible at the required page size','plot 3 axis runs to a negative sum of squared error']
  report['notes']='Reviewed every page. Body structure and identity are correct; the analysis figures are not.'
  return report

 def test_failed_inspection_is_recorded_and_named_rather_than_refused(self):
  """A reviewer who finds defects must be able to record that verdict (#28)."""
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   run,artifact,_=self.verified_run(workspace,source,'rejected')
   relative='deliverables/submission.pdf'

   # Before anyone looks, the run is not inspected and says so.
   before=status_run(workspace,'rejected')
   self.assertEqual([item['status'] for item in before['inspections']],['not_inspected'])
   self.assertIn('one or more deliverable artifacts are not inspected',before['readiness']['blockers'])

   report=self.rejection(artifact,relative)
   result=inspect_artifact(workspace,'rejected',relative,report)

   # The outcome is unmissable in the returned record, which is what the CLI prints.
   self.assertEqual(result['inspection'],'rejected')
   self.assertEqual(result['artifact'],relative)
   self.assertTrue(result['findings'])

   # The verdict is stored, not thrown away.
   saved=load_run(workspace,'rejected')['artifacts'][0]
   self.assertEqual(saved['inspection_report'],report)
   self.assertEqual(saved['inspection_sha256'],digest(report))
   self.assertIs(saved['inspected'],False)

   # It is a blocker that names what the reviewer actually found.
   self.assertFalse(result['readiness']['ready'])
   named=[value for value in result['readiness']['blockers'] if value.startswith('inspection rejected')]
   self.assertEqual(len(named),1,result['readiness']['blockers'])
   self.assertIn(relative,named[0]); self.assertIn('legible',named[0])
   self.assertIn('figure 2 is illegible at the required page size',named[0])
   self.assertIn('negative sum of squared error',named[0])

   # And never again reports the two sentences that mean "nobody looked".
   self.assertNotIn('run has not reached inspected stage',result['readiness']['blockers'])
   self.assertNotIn('one or more deliverable artifacts are not inspected',result['readiness']['blockers'])

   after=status_run(workspace,'rejected')
   self.assertEqual(after['effective_stage'],'rejected')
   self.assertEqual([item['status'] for item in after['inspections']],['rejected'])
   self.assertEqual(after['inspections'][0]['artifact'],relative)
   self.assertTrue(after['inspections'][0]['findings'])
   self.assertNotEqual(before['inspections'][0]['status'],after['inspections'][0]['status'])

 def test_a_rejected_inspection_can_never_reach_ready(self):
  """Widening what can be recorded must not widen what can be certified (#28)."""
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   run,artifact,_=self.verified_run(workspace,source,'gate')
   relative='deliverables/submission.pdf'
   honest=self.inspection(artifact,relative)
   for mutation in ({'legible':False},{'all_pages_reviewed':False},{'requirements_present':False},{'identity_checked':False},{'no_clipping':False},{'unresolved':['page 3 is unreadable']}):
    result=inspect_artifact(workspace,'gate',relative,{**honest,**mutation})
    self.assertFalse(result['readiness']['ready'],mutation)
    self.assertEqual(result['inspection'],'rejected',mutation)
    self.assertIs(load_run(workspace,'gate')['artifacts'][0]['inspected'],False,mutation)
    self.assertTrue(any(value.startswith('inspection rejected') for value in result['readiness']['blockers']),mutation)
    # A hand-forced ready stage must still be recomputed as stale.
    state=load_run(workspace,'gate'); state['stage']='ready'; save_run(workspace,state)
    self.assertEqual(status_run(workspace,'gate')['effective_stage'],'stale',mutation)
   # The same artifact still passes on an honest report, so the gate is intact.
   passing=inspect_artifact(workspace,'gate',relative,honest)
   self.assertTrue(passing['readiness']['ready']); self.assertEqual(passing['inspection'],'passed')
   self.assertEqual(status_run(workspace,'gate')['inspections'][0]['status'],'passed')

 def test_a_report_that_records_nothing_is_still_refused(self):
  """Recording a rejection is widened; recording a non-report is not (#28)."""
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   run,artifact,_=self.verified_run(workspace,source,'malformed')
   relative='deliverables/submission.pdf'
   honest=self.inspection(artifact,relative)
   for label,report in (
    ('not an object',['legible']),
    ('no notes',{**honest,'notes':'   '}),
    ('notes missing',{key:value for key,value in honest.items() if key!='notes'}),
    ('another artifact path',{**honest,'artifact_path':'deliverables/other.pdf'}),
    ('another artifact sha',{**honest,'artifact_sha256':'0'*64}),
    ('unresolved is not a list',{**honest,'unresolved':'page 3 is unreadable'}),
   ):
    with self.assertRaises(ValueError,msg=label): inspect_artifact(workspace,'malformed',relative,report)
   self.assertNotIn('inspection_report',load_run(workspace,'malformed')['artifacts'][0])

 def test_re_recording_a_solution_cannot_reuse_a_passing_inspection(self):
  """Regression cover for the readiness restructure: the inspected flag still gates."""
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   run,artifact,solution=self.verified_run(workspace,source,'reuse')
   relative='deliverables/submission.pdf'
   self.assertTrue(inspect_artifact(workspace,'reuse',relative,self.inspection(artifact,relative))['readiness']['ready'])
   # A byte-identical solution leaves every hash equal, so only the inspected flag
   # stands between this run and a false ready on a report that predates the re-record.
   record_solution(workspace,'reuse',solution)
   record_checks(workspace,'reuse',[check_calculation(item) for item in solution['calculations']])
   self.verifier_report(workspace,'reuse')
   status=status_run(workspace,'reuse')
   self.assertFalse(status['readiness']['ready'])
   self.assertIn('one or more deliverable artifacts are not inspected',status['readiness']['blockers'])
   self.assertEqual(status['inspections'][0]['status'],'stale')

 def test_discarded_downstream_records_are_reported_not_dropped_silently(self):
  """Every writer that invalidates downstream work must say what it destroyed (#14)."""
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   run,artifact,solution=self.verified_run(workspace,source,'discard')
   relative='deliverables/submission.pdf'
   inspect_artifact(workspace,'discard',relative,self.inspection(artifact,relative))

   # Re-registering an artifact drops the verifier report and that artifact's inspection.
   state=record_artifact(workspace,'discard',artifact)
   entry=state['discarded'][-1]
   self.assertEqual(entry['operation'],'record_artifact')
   self.assertIn('structured verifier report',entry['records'])
   self.assertTrue(any(relative in value for value in entry['records']),entry['records'])
   self.assertTrue(entry['at'])

   # Re-recording a solution drops the checks as well.
   self.verifier_report(workspace,'discard')
   state=record_solution(workspace,'discard',{**solution,'title':'Revised'})
   entry=state['discarded'][-1]
   self.assertEqual(entry['operation'],'record_solution')
   self.assertIn('calculation checks',entry['records'])
   self.assertIn('structured verifier report',entry['records'])

   # Recording checks drops a verifier report that was written before them.
   record_artifact(workspace,'discard',artifact)
   record_checks(workspace,'discard',[check_calculation(item) for item in solution['calculations']])
   self.verifier_report(workspace,'discard')
   state=record_checks(workspace,'discard',[check_calculation(item) for item in solution['calculations']])
   self.assertEqual(state['discarded'][-1]['operation'],'record_checks')
   self.assertIn('structured verifier report',state['discarded'][-1]['records'])

   # Accepting a new plan drops everything downstream of it.
   state=set_plan(workspace,'discard',self.plan(workspace,source))
   entry=state['discarded'][-1]
   self.assertEqual(entry['operation'],'set_plan')
   for record in ('solution','calculation checks','deliverable artifacts'):
    self.assertIn(record,entry['records'])

   # The history is durable and visible from status, not only from the return value.
   self.assertEqual(status_run(workspace,'discard')['discarded'],load_run(workspace,'discard')['discarded'])
   self.assertEqual(len(load_run(workspace,'discard')['discarded']),4)

 def test_cli_render_reports_what_rendering_discarded(self):
  """render calls record_solution internally, so it must report the loss too (#14)."""
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   run,artifact,solution=self.verified_run(workspace,source,'render')
   relative='deliverables/submission.pdf'
   inspect_artifact(workspace,'render',relative,self.inspection(artifact,relative))
   self.assertTrue(status_run(workspace,'render')['readiness']['ready'])
   solution_path=root/'solution.json'; atomic_json(solution_path,solution)
   with redirect_stdout(io.StringIO()):
    self.assertEqual(cli_main(['--workspace',str(workspace),'render','render',str(solution_path)]),0)
   records=[value for entry in load_run(workspace,'render')['discarded'] for value in entry['records']]
   self.assertIn('calculation checks',records)
   self.assertIn('structured verifier report',records)
   self.assertTrue(any('inspection' in value for value in records),records)
   self.assertTrue(status_run(workspace,'render')['discarded'])

 def test_a_forward_run_discards_nothing_and_stays_silent(self):
  """A log that fires on an ordinary run would be noise, not a signal (#14)."""
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'a.txt'; source.write_text('assignment'); workspace=root/'w'
   run,artifact,_=self.verified_run(workspace,source,'forward')
   inspect_artifact(workspace,'forward','deliverables/submission.pdf',self.inspection(artifact,'deliverables/submission.pdf'))
   status=status_run(workspace,'forward')
   self.assertTrue(status['readiness']['ready'])
   self.assertEqual(status['discarded'],[])
   self.assertEqual(load_run(workspace,'forward').get('discarded',[]),[])
