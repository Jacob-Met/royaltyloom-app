'use strict';
(()=>{
 const panel=document.createElement('details');panel.className='statement-history';panel.id='reviewFilePanel';
 panel.innerHTML='<summary>Open a statement or draft file</summary><label class="field">Statement or draft JSON<input id="reviewFile" type="file" accept=".json,application/json"></label><p id="reviewFileStatus" role="status" aria-live="polite"></p><div id="reviewFilePreview" hidden><p id="reviewFileSummary"></p><ol id="reviewFileHistory"></ol><p id="reviewFileEffect"></p><button type="button" class="btn" id="replaceReviewFile">Replace current draft</button> <button type="button" class="btn ghost" id="cancelReviewFile">Cancel</button></div>';
 $('statementHistory').after(panel);
 const style=document.createElement('style');style.textContent='#reviewFileHistory{list-style:none;padding:0;margin:16px 0}#reviewFileHistory li{border-top:1px solid var(--line);padding:12px 0}#reviewFileHistory strong,#reviewFileHistory span{display:block}#reviewFileHistory span{font-size:13px;color:var(--muted);margin-top:4px}';document.head.append(style);
 const status=$('reviewFileStatus'),preview=$('reviewFilePreview');let pending=null,serial=0;
 const fingerprint=()=>JSON.stringify({fields:[...document.querySelectorAll('.workflow input,.workflow textarea')].map(x=>[x.id,x.value,x.checked]),people:$('people').innerHTML,period:$('statementPeriod').value});
 function setSourceCorrectionView(active){
  panel.querySelector('summary').textContent=active?'Review correction copy':'Open a statement or draft file';
  $('reviewFile').closest('label').hidden=active;
 }
 const fail=message=>{pending=null;preview.hidden=true;setSourceCorrectionView(false);status.textContent=message;};
 const text=(v,label,max)=>{if(typeof v!=='string'||v.length>max)throw Error('Invalid '+label+' in review file.');return v;};
 function sourceFrom(d){
  if(!d||!Array.isArray(d.transactions)||!Array.isArray(d.collaborators)||typeof d.statement_hash!=='string')throw Error('Choose a Royalty Loom review JSON exported from Download review JSON.');
  if(!d.transactions.length||d.transactions.length>2000||!d.collaborators.length||d.collaborators.length>100)throw Error('Review file has an unsupported number of transactions or creators.');
  const quote=v=>'"'+String(v).replaceAll('"','""')+'"';
  const rows=d.transactions.map(t=>{
   if(!['sale','refund','fee'].includes(t.type)||!Number.isSafeInteger(t.cents)||t.cents<=0)throw Error('Invalid source transaction amount or type.');
   return [text(t.id,'transaction ID',200),t.type,(t.cents/100).toFixed(2),text(t.description||'','description',5000),...(d.source_date_review?[text(d.source_dates?.[t.id],'source date',10)]:[])].map(quote).join(',');
  });
  const collaborators=d.collaborators.map(p=>{
   if(p.share_basis!=='equal'&&(!Number.isInteger(p.share_bps)||p.share_bps<0||p.share_bps>10000))throw Error('Invalid creator share.');
   return {name:text(p.name,'creator name',200),email:text(p.email,'creator email',320),...(p.share_basis==='equal'?{share_basis:'equal'}:{share_bps:p.share_bps}),evidence:text(p.evidence||'','agreement evidence',10000)};
  });
  const source={project:text(d.project,'project',500),agreement:text(d.agreement,'agreement',100000),sales_csv:'id,type,amount,description'+(d.source_date_review?',date':'')+'\n'+rows.join('\n'),collaborators,illustrative:d.illustrative===true};
  if(Object.hasOwn(d,'agreement_review'))source.agreement_review=JSON.parse(JSON.stringify(d.agreement_review));
  if(d.source_date_review===true)source.source_date_review=true;
  if(d.project_id!==undefined)source.project_id=text(d.project_id,'project identity',100);
  if(d.reporting_period)source.reporting_period={start:text(d.reporting_period.start,'period start',10),end:text(d.reporting_period.end,'period end',10)};
  if(d.statement_context){source.statement_context={};for(const [key,max] of [['issuer',100],['help_email',254],['payment_note',1000]])source.statement_context[key]=text(d.statement_context[key]||'',key,max);}
  if(d.advance_recovery)source.advance_recovery=advanceInputFrom(d.advance_recovery);
  return source;
 }
 function draftCopiesFrom(d){
  if(!d||d.version!==1||!Object.hasOwn(d,'this_tab')||!Object.hasOwn(d,'saved'))return null;
  const copies=[];
  for(const [label,value] of [['This tab',d.this_tab],['Saved draft',d.saved]]){
   if(value===null)continue;
   const raw=JSON.stringify(value),draft=parseDraftSnapshot(raw);
   if(raw.length>4*1024*1024||draft.project.length>500||draft.agreement.length>100000||draft.sales.length>2*1024*1024)throw Error('Draft copy is too large.');
   const scan=value=>{if(value&&typeof value==='object')for(const key of Object.keys(value)){if(['__proto__','constructor','prototype'].includes(key))throw Error('Invalid draft copy fields.');scan(value[key]);}};scan(draft);
   if(draft.project_id!==undefined&&draft.project_id!==null&&(typeof draft.project_id!=='string'||draft.project_id.length>100))throw Error('Invalid draft project identity.');
   if(!copies.some(copy=>JSON.stringify(copy.draft)===raw))copies.push({label,draft});
  }
  if(!copies.length)throw Error('This file has no draft copies.');
  return copies;
 }
 function previewDraftCopies(copies,file,before){
  pending={draftCopies:copies,before};
  $('reviewFileHistory').replaceChildren();
  for(const copy of copies){
   const row=document.createElement('li'),title=document.createElement('strong'),description=document.createElement('span');
   title.textContent=copy.draft.project||'Untitled project';
   description.textContent=copy.label+' · '+copy.draft.people.length+' creators'+(copy.draft.period_label?' · '+copy.draft.period_label:'');
   row.append(title,description);$('reviewFileHistory').append(row);
  }
  $('replaceReviewFile').textContent='Keep draft copies';
  $('reviewFileSummary').textContent=copies.length+' draft '+(copies.length===1?'copy':'copies');
  $('reviewFileEffect').textContent='Choose a copy to open after importing.';
  preview.hidden=false;status.textContent=file.name;
 }

 function previewRefusedSource(source,label,issue,file,before){
  const draft={version:1,project:source.project,project_id:source.project_id,
   agreement:source.agreement,sales:source.sales_csv,illustrative:source.illustrative,
    source_provenance:source.source_provenance||null,
   statement_context:source.statement_context||{},reporting_period:source.reporting_period||{start:'',end:''},
   period_label:label,source_date_review:source.source_date_review===true,
   advance_recovery:source.advance_recovery||null,agreement_review:null,
   people:source.collaborators.map(person=>({name:person.name,email:person.email,
    share:person.share_basis==='equal'?'equal':String(person.share_bps/100),evidence:person.evidence}))};
  draftCopiesFrom({version:1,this_tab:draft,saved:null});
  previewDraftCopies([{label:'Original statement source',draft}],file,before);
  const original=document.createElement('details'),heading=document.createElement('summary'),agreement=document.createElement('pre');
  heading.textContent='Original agreement';agreement.textContent=source.agreement;
  agreement.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere;font:inherit';
  original.append(heading,agreement);$('reviewFileHistory').firstElementChild.append(original);
  $('replaceReviewFile').textContent='Keep source for correction';
  $('reviewFileSummary').textContent='Source needs correction';
  $('reviewFileEffect').textContent='Keep an uncalculated draft copy. Earlier balance history and payment records are not imported.';
  setSourceCorrectionView(true);status.textContent=issue.reason;
 }
 window.previewStatementSourceCorrection=(source,label,issue,name)=>{
  serial++;fail('');
  previewRefusedSource(source,label,issue,{name},fingerprint());
  panel.open=true;$('replaceReviewFile').focus({preventScroll:true});
  preview.scrollIntoView({block:'center',behavior:'smooth'});
 };
 async function importDraftCopies(copies){
  const button=$('replaceReviewFile');button.disabled=true;$('reviewFile').disabled=true;$('cancelReviewFile').disabled=true;
  try{
   await withDraftLock(()=>{
    const original=new Set(readDraftCopies().map(copy=>copy.key)),added=[];
    try{for(const copy of copies){const key=retainDraftCopy(copy.draft);if(!original.has(key))added.push(key);}}
    catch(error){for(const key of added)localStorage.removeItem(key);throw error;}
   });
   if($('draftCopySearch'))$('draftCopySearch').value='';
   showDraftCopies();$('draftCopies').open=true;
   serial++;fail('Draft copies imported.');if(typeof closeHistory==='function')closeHistory();setStatus('Draft copies imported. Choose a copy to open.');$('draftCopies').scrollIntoView({block:'start',behavior:'smooth'});
  }catch(error){fail('Could not keep draft copies: '+error.message);}
  finally{button.disabled=false;$('reviewFile').disabled=false;$('cancelReviewFile').disabled=false;}
 }
 $('reviewFile').addEventListener('change',async()=>{
  const request=++serial;pending=null;preview.hidden=true;const file=$('reviewFile').files[0];if(!file)return;
  const before=fingerprint();status.textContent='Reading and recalculating review file…';
  try{
   if(file.size>8*1024*1024)throw Error('Choose a file smaller than 8 MB.');
   const d=JSON.parse(await file.text()),copies=draftCopiesFrom(d);
   if(request!==serial)return;
   if(copies){previewDraftCopies(copies,file,before);return;}
   if(file.size>2*1024*1024)throw Error('Review file is too large. Choose a file smaller than 2 MB.');
   const source=sourceFrom(d),payload={project_data:source,statement_hash:d.statement_hash,prior_statements:d.prior_statements||[]};
   let checked;
   try{checked=await api('/api/review/preview',payload);}
   catch(error){
    if(!error.agreementIssue)throw error;
    if(request!==serial)return;
    if(before!==fingerprint())throw Error('Your draft changed while the file was being checked. Choose the file again; your edits were kept.');
    previewRefusedSource(source,text(d.period_label||'','period label',80),error.agreementIssue,file,before);return;
   }
   const calculated=checked.statement;
   if(request!==serial)return;
   if(before!==fingerprint())throw Error('Your draft changed while the file was being checked. Choose the file again; your edits were kept.');
   if(calculated.agreement_review)source.agreement_review=calculated.agreement_review;source.project_id=calculated.project_id;pending={source,payload,label:text(d.period_label||'','period label',80),before};
   $('reviewFileHistory').replaceChildren();for(const prior of checked.prior_statements){const li=document.createElement('li'),title=document.createElement('strong'),balance=document.createElement('span');title.textContent=prior.period_label||(prior.reporting_period?periodCaption(prior.reporting_period):'Earlier period');balance.textContent='$'+(prior.closing_cents/100).toFixed(2)+' closing advance · '+(prior.already_saved?'Already saved':'Restore this period');li.append(title,balance);$('reviewFileHistory').append(li);}
   $('replaceReviewFile').textContent=checked.prior_statements.some(p=>!p.already_saved)?'Restore history and open draft':'Replace current draft';
   $('reviewFileSummary').textContent=calculated.project+' · '+calculated.collaborators.length+' creators · '+calculated.transactions.length+' transactions · Recalculated net $'+calculated.net+(source.reporting_period?' · '+source.reporting_period.start+' to '+source.reporting_period.end:'');
   $('reviewFileEffect').textContent='Your current draft will be kept in Saved draft copies. Earlier periods will be saved; this statement opens as your editable draft.';
   preview.hidden=false;status.textContent=file.name+' is ready to review. Your current draft is unchanged.'; 
  }catch(e){if(request===serial)fail('Could not open review file: '+e.message+' Your current draft was kept.');}
  finally{$('reviewFile').value='';}
 });
 $('cancelReviewFile').addEventListener('click',()=>{serial++;fail('Import cancelled. Your current draft was kept.');});
 $('replaceReviewFile').addEventListener('click',async()=>{
  if(!pending)return;
  if(pending.draftCopies)return importDraftCopies(pending.draftCopies);
  if(pending.before!==fingerprint())return fail('Your draft changed after preview. Choose the file again; your edits were kept.');
  const {source,label,payload,before}=pending;const request=serial,button=$('replaceReviewFile');button.disabled=true;$('cancelReviewFile').disabled=true;$('reviewFile').disabled=true;
  try{
   await draftSavePromise;
   await withDraftLock(()=>{
    if(request!==serial||before!==fingerprint())throw Error('Your draft changed after preview. Choose the file again.');
    const mine=currentDraftSnapshot(),latest=localStorage.getItem(DRAFT_KEY);
    retainDraftCopy(mine);
    if(latest)retainDraftCopy(parseDraftSnapshot(latest));
   });
   showDraftCopies();
   await api('/api/review/restore',payload);
  }catch(e){button.disabled=false;return fail('Could not restore review history: '+e.message+' Your current draft was kept.');}finally{button.disabled=false;$('cancelReviewFile').disabled=false;$('reviewFile').disabled=false;}
  if(request!==serial||before!==fingerprint())return fail('Earlier balance history was restored, but your draft changed and was kept. Choose the file again to open it.');
  try{sessionStorage.setItem(DRAFT_ALTERNATE_KEY,JSON.stringify(currentDraftSnapshot()));}
  catch(e){return fail('Could not keep the return draft: '+e.message+' Your current draft was kept.');}
  restoringDraft=true;
  try{sourceDateReview=source.source_date_review===true;restoreProjectIdentity(source.project_id);restoreSourceProvenance(null);restoreStatementContext(source.statement_context);restoreAdvanceRecovery(source.advance_recovery);$('project').value=source.project;$('agreement').value=source.agreement;$('sales').value=source.sales_csv;$('periodStart').value=source.reporting_period?.start||'';$('periodEnd').value=source.reporting_period?.end||'';$('people').replaceChildren();for(const p of source.collaborators)addPerson(p);restoreAgreementReview(source.agreement_review);illustrative=source.illustrative;invalidate();$('statementPeriod').value=label;}finally{restoringDraft=false;}
  window.dispatchEvent(new Event('royalty-history-restored'));saveDraft();showDraftUndo();fail('Review file opened as an editable draft. Your previous draft is in Saved draft copies.');$('project').focus();$('project').scrollIntoView({block:'center',behavior:'smooth'});
 });
})();