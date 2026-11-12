'use strict';
(() => {
 const style=document.createElement('style');
 style.textContent='.statement-history{border-block:1px solid var(--line);margin:18px 0;padding:12px 0}.statement-history summary{cursor:pointer;font-weight:650;min-height:32px}.statement-history .history-search{max-width:440px;margin:12px 0}.history-list{list-style:none;padding:0;margin:0}.history-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:14px 0;border-top:1px solid var(--line);align-items:center}.history-name{font-weight:700;overflow-wrap:anywhere}.history-meta{color:var(--muted);font-size:12px}.history-amount{font-variant-numeric:tabular-nums;font-weight:700}.history-buttons{display:flex;gap:8px;flex-wrap:wrap;margin-top:6px}.history-buttons button{min-height:40px}.save-statement{display:flex;gap:10px;flex-wrap:wrap;align-items:end;width:100%;margin-top:10px}.save-statement label{font-size:12px;flex:1;max-width:260px}.save-statement input{margin-top:5px}.history-notice{font-size:13px;color:var(--muted);margin:8px 0}.history-active{border-left:3px solid var(--accent);padding-left:10px}@media(max-width:600px){.history-row{grid-template-columns:minmax(0,1fr)}.save-statement label{max-width:none}.save-statement .btn{width:auto}.history-buttons{gap:8px}.history-buttons .btn{width:auto}}';
 style.textContent+='.returning-work{border-top:1px solid var(--line);margin-top:18px;padding-top:14px}.returning-work h2{font:600 14px/1.4 system-ui,sans-serif;margin:0 0 5px}.returning-work .history-row{border-top:0;padding-top:5px}.browser-draft-shortcut{display:flex;justify-content:space-between;align-items:center;gap:16px;border-top:1px solid var(--line);padding:12px 0}.browser-draft-shortcut[hidden]{display:none}.browser-draft-shortcut p{margin:3px 0;overflow-wrap:anywhere}.browser-draft-shortcut .btn{flex-shrink:0}@media(max-width:600px){.browser-draft-shortcut{align-items:flex-start;flex-direction:column;gap:6px}.browser-draft-shortcut .btn{width:auto}}';
 style.textContent+='.history-balances{grid-column:1/-1;border-top:1px solid var(--line);padding-top:10px}.history-balances table{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}.history-balances caption{text-align:left;font-weight:650;padding-bottom:8px}.history-balances th,.history-balances td{padding:7px 4px;text-align:right;font-variant-numeric:tabular-nums;border-bottom:1px solid var(--line)}.history-balances th:first-child,.history-balances td:first-child{text-align:left;width:34%;overflow-wrap:anywhere}.history-balances th{font-size:11px;font-weight:600}.history-continuity{font-size:12px;margin:8px 0 0;color:inherit;opacity:.8}.history-balances td:last-child{font-weight:700}.history-net-label{font-size:11px;font-weight:400;display:block}.history-predecessor{padding:0;border:0;background:none;color:inherit;text-decoration:underline;font:inherit;cursor:pointer}';
 style.textContent+='#historyDialog{width:min(1000px,calc(100vw - 40px));max-width:1000px}.history-continuity{display:flex;flex-wrap:wrap;gap:6px 18px}.history-predecessor{min-height:32px;color:var(--accent)}';
 style.textContent+='.history-row{gap:6px;padding:10px 0;align-items:start}.history-balances{border-top:0;padding-top:0}.history-balances caption{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}.history-balances th,.history-balances td{padding:4px}.history-continuity{margin:4px 0}.history-net-label{display:inline;margin-right:8px}.history-meta{line-height:1.4}';
 style.textContent+='@media(max-width:600px){.history-balances-wide table,.history-balances-wide tbody{display:block}.history-balances-wide thead{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}.history-balances-wide tbody tr{display:block;border-top:1px solid var(--line);padding:8px 0}.history-balances-wide tbody th{display:block;width:auto!important;font-size:13px;padding:3px 0 7px;border:0}.history-balances-wide tbody td{display:flex;justify-content:space-between;gap:16px;width:auto;text-align:right;border:0;padding:3px 0;font-size:13px;white-space:nowrap}.history-balances-wide tbody td::before{content:attr(data-label);font-size:12px;font-weight:400;color:var(--muted);text-align:left}.history-balances-wide .history-continuity{margin-top:8px}}';
 style.textContent+='.history-copies{grid-column:1/-1;min-width:0;padding-top:4px}.history-copies>summary{min-height:44px;padding:6px 0;cursor:pointer;color:var(--accent);font-size:13px}.history-copy-list{list-style:none;margin:0;padding:0 0 0 12px;border-left:1px solid var(--line)}.history-copy-list>.history-row{padding:12px 0}.history-copies[open]>summary{margin-bottom:6px}';
 document.head.append(style);
 const panel=document.createElement('details');
 panel.className='statement-history'; panel.id='statementHistory';
 const summary=document.createElement('summary');summary.textContent='Saved statements';
 const note=document.createElement('p');note.className='history-notice';note.id='historyNotice';note.setAttribute('role','status');
 const searchLabel=document.createElement('label');searchLabel.className='history-search field';searchLabel.textContent='Find a project, period or reference';
 const search=document.createElement('input');search.type='text';search.id='historySearch';search.placeholder='Project, period or statement reference';search.autocomplete='off';searchLabel.append(search);
 const list=document.createElement('ul');list.className='history-list';list.id='historyList';
 const loadMore=document.createElement('button');loadMore.id='historyLoadMore';loadMore.type='button';loadMore.className='btn small ghost';loadMore.textContent='Load earlier statements';loadMore.hidden=true;
 panel.append(summary,searchLabel,note,loadMore,list);document.querySelector('.workflow').before(panel);
 const work=document.createElement('section');work.id='returningWork';work.className='returning-work';work.hidden=true;work.setAttribute('aria-label','Your current work');
 const latest=document.createElement('div');latest.id='latestSaved';latest.hidden=true;
 const latestHeading=document.createElement('h2');latestHeading.textContent='Latest saved statement';
 const latestList=document.createElement('ul');latestList.className='history-list';
 const latestNote=document.createElement('p');latestNote.className='history-meta';latestNote.textContent='Saved on this server; browser edits are separate.';
 latest.append(latestHeading,latestList,latestNote);
 const draft=document.createElement('div');draft.id='browserDraftShortcut';draft.className='browser-draft-shortcut';draft.hidden=true;
 const draftInfo=document.createElement('div');const draftName=document.createElement('p');draftName.className='history-name';
 const draftNote=document.createElement('p');draftNote.className='history-meta';draftNote.textContent='Current form in this browser. Changes are separate from saved statements.';
 const continueDraft=document.createElement('button');continueDraft.type='button';continueDraft.className='btn small ghost';continueDraft.id='continueBrowserDraft';continueDraft.textContent='Continue draft';
 continueDraft.addEventListener('click',()=>{const target=!$('project').value.trim()?$('project'):!$('agreement').value.trim()?$('agreement'):$('sales');target.focus();target.scrollIntoView({block:'center',behavior:'smooth'});});
 draftInfo.append(draftName,draftNote);draft.append(draftInfo,continueDraft);work.append(latest,draft);panel.before(work);
 function refreshDraftShortcut(){
  const hasInput=['project','agreement','sales'].some(id=>$(id).value.trim())||[...document.querySelectorAll('.person input')].some(input=>input.value.trim());
  draft.hidden=!hasInput;draftName.textContent='Browser draft · '+($('project').value.trim()||'Untitled project');work.hidden=latest.hidden&&draft.hidden;
 }
 for(const type of ['input','change','click'])document.addEventListener(type,()=>queueMicrotask(refreshDraftShortcut));
 style.textContent+='.history-record{grid-column:1/-1;border-top:1px solid var(--line);padding-top:10px}.history-record summary{cursor:pointer;font-weight:650;padding:5px 0}.history-record-content{padding-top:10px}.history-payment-title{font-weight:700;margin:0 0 6px}.history-record table{width:100%;border-collapse:collapse;font-size:13px;margin-top:12px;table-layout:fixed}.history-record th,.history-record td{padding:9px 5px;border-bottom:1px solid var(--line);text-align:left;overflow-wrap:anywhere}.history-record th:first-child{width:42%}.history-record th:nth-child(2){width:25%}.history-record small{display:block;font-weight:400;font-size:11px;color:var(--muted);overflow-wrap:anywhere}.history-record .history-payment-reason{font-size:12px;font-weight:400}.history-record .history-meta{margin:3px 0}';
 style.textContent+='@media(max-width:480px){.history-payment table,.history-payment tbody{display:block;width:100%}.history-payment thead{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}.history-payment .history-payment-recipient:not([hidden]){display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);column-gap:14px;border-top:1px solid var(--line);padding:16px 0}.history-payment .history-payment-recipient>th{grid-column:1/-1;width:auto;margin-bottom:12px;font-size:15px}.history-payment .history-payment-recipient>th,.history-payment .history-payment-recipient>td{display:block;border:0;padding:0;min-width:0}.history-payment .history-payment-recipient small{font-size:12px;margin-top:5px}.history-payment .history-payment-recipient .btn{margin-top:10px;min-height:38px;font-size:12px}.history-payment .history-payment-recipient>td:nth-child(2){font-size:17px;font-weight:650;font-variant-numeric:tabular-nums}.history-payment .history-payment-recipient>td:nth-child(3){text-align:right;font-size:13px}.history-payment .history-payment-recipient>td::before{display:block;margin-bottom:4px;font-size:10px;font-weight:400;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}.history-payment .history-payment-recipient>td:nth-child(2)::before{content:"Amount"}.history-payment .history-payment-recipient>td:nth-child(3)::before{content:"Status"}.history-payment tbody>tr:not(.history-payment-recipient):not([hidden]){display:block}.history-payment tbody>tr:not(.history-payment-recipient)>td{display:block;width:100%;box-sizing:border-box}}';
 style.textContent+='.history-allocation-tools{display:flex;gap:8px;align-items:center}.history-allocation-tools input{flex:1;min-width:0}.history-allocation-tools .btn{flex:0 0 auto;white-space:nowrap}';
 style.textContent+='@media(max-width:480px){.history-calculation table,.history-calculation tbody{display:block}.history-calculation thead{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}.history-calculation tbody tr{display:grid;grid-template-columns:minmax(0,.8fr) minmax(0,1.2fr);border-bottom:1px solid var(--line);padding:6px 0}.history-calculation tbody th{grid-column:1/-1;width:auto!important;border:0}.history-calculation tbody td{width:auto;border:0}.history-calculation tbody td:before{content:attr(data-label);display:block;font-size:11px;color:var(--muted);margin-bottom:4px}.history-calculation tbody td:last-child{overflow-wrap:normal}}';
 const controls=document.createElement('div');controls.className='save-statement';
 const label=document.createElement('label');label.textContent='Period or statement label (optional)';
 const period=document.createElement('input');period.type='text';period.maxLength=80;period.id='statementPeriod';period.placeholder='e.g. October 2026';period.value=restoredPeriodLabel;period.addEventListener('input',saveDraft);label.append(period);
 const saveButton=document.createElement('button');saveButton.type='button';saveButton.className='btn';saveButton.id='saveStatement';saveButton.textContent='Save statement';
 controls.append(label,saveButton);$('download').closest('.actions').append(controls);
 let currentSavedHash=null,requestNumber=0,openingNumber=0,paymentCopyRevision=0,searchTimer;
 function payoutLabel(item) {
  if(item.illustrative)return 'Illustrative example';
  if(!item.payout)return '';
  const review=item.payout.provider_review,unavailable=item.payout.provider_check?.verified===false;
  if(review?.verified&&Number.isInteger(review.success_items)&&Number.isInteger(review.total_items)&&review.total_items>0&&review.success_items>=0&&review.success_items<=review.total_items){
   const outcomes=review.success_items+' of '+review.total_items+' recipients successful';
   const batch=review.all_items_success?' · Complete':review.success_items===review.total_items?' · Batch not complete':'';
   return (unavailable?'Last known: ':'Saved outcome: ')+outcomes+batch+(unavailable?' · Latest check unavailable':'');
  }
  if(unavailable)return 'Latest check unavailable · No verified recipient outcomes saved';
  const labels={intent:'Payout outcome pending',uncertain:'Payout outcome unresolved',submitted:'Submitted to Sandbox — check recipient status'};
  return labels[item.payout.state] || 'Recorded payout — inspect status';
 }
 function contactLabel(item) {
  const contacts=item.contact_status;if(!contacts)return '';
  if(!contacts.payable_count)return 'No payout needed';
  if(contacts.missing_count)return contacts.missing_count+' payout '+(contacts.missing_count===1?'contact needed':'contacts needed');
  return 'Contacts complete';
 }
 async function get(path) {
  const r=await fetch(path);const data=await r.json();
  if(!r.ok)throw Error(data.error || 'Saved statements could not be loaded.');
  return data;
 }

 function calculationRecord(item){
  const details=document.createElement('details');details.className='history-calculation history-record';
  const summary=document.createElement('summary');summary.textContent='Saved allocation';
  const content=document.createElement('div');content.className='history-calculation-content history-record-content';details.append(summary,content);
  let request=0;
  details.addEventListener('toggle',async()=>{
   const current=++request;if(!details.open)return;
   content.textContent='Loading saved allocation…';
   try{
    const record=await get('/api/statements/'+item.statement_hash);
    if(current!==request||!details.open)return;
    if(!Array.isArray(record.statement?.collaborators))throw Error('Saved allocation unavailable');
    content.replaceChildren();
    const table=document.createElement('table'),head=document.createElement('thead'),heading=document.createElement('tr');table.setAttribute('aria-label','Saved allocation');
    const recovery=record.statement.collaborators.some(person=>Number.isInteger(person.royalty_cents)&&Number.isInteger(person.recovery_cents));
    for(const text of ['Recipient',recovery?'Share after recovery':'Share',recovery?'Total':'Amount']){const cell=document.createElement('th');cell.scope='col';cell.textContent=text;heading.append(cell);}head.append(heading);table.append(head);
    const body=document.createElement('tbody');
    for(const person of record.statement.collaborators){
     const row=document.createElement('tr'),name=document.createElement('th'),share=document.createElement('td'),amount=document.createElement('td');
     share.dataset.label=recovery?'Share after recovery':'Share';amount.dataset.label=recovery?'Total':'Amount';
     name.scope='row';name.textContent=person.name;
     if(person.email){const email=document.createElement('small');email.textContent=person.email;name.append(email);}
     share.textContent=person.share_basis==='equal'?'1/'+person.share_denominator+' equal share':Number.isInteger(person.share_bps)?(person.share_bps/100).toFixed(2).replace(/\.?0+$/,'')+'%':'—';
     amount.textContent=new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(Number(person.amount));
     if(recovery&&Number.isInteger(person.royalty_cents)&&Number.isInteger(person.recovery_cents)){
      for(const [label,cents] of [['Royalty',person.royalty_cents],['Recovery',person.recovery_cents]]){
       const part=document.createElement('small'),value=document.createElement('span');part.append(label+' ');value.style.whiteSpace='nowrap';value.textContent=new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(cents/100);part.append(value);amount.append(part);
      }
     }
     row.append(name,share,amount);body.append(row);
    }
    table.append(body);
    if(record.statement.collaborators.length>8){
     const tools=document.createElement('div');tools.className='history-allocation-tools';
     const search=document.createElement('input');search.type='search';search.placeholder='Find recipient';search.setAttribute('aria-label','Find a saved recipient by name or email');search.dataset.allocationSearch='';
     const clear=document.createElement('button');clear.type='button';clear.className='btn small ghost';clear.textContent='Clear filter';clear.dataset.clearAllocation='';clear.hidden=true;
     const count=document.createElement('p');count.className='history-meta';
     const keys=record.statement.collaborators.map(person=>((person.name||'')+' '+(person.email||'')).normalize('NFKC').toLocaleLowerCase());
     const filter=()=>{
      const query=search.value.trim().normalize('NFKC').toLocaleLowerCase();let shown=0;
      [...body.rows].forEach((row,index)=>{row.hidden=!!query&&!keys[index].includes(query);if(!row.hidden)shown++;});
      clear.hidden=!search.value;count.textContent=(query?shown+' of ':'')+keys.length+' recipients';
     };
     search.addEventListener('input',filter);clear.addEventListener('click',()=>{search.value='';filter();search.focus();});
     tools.append(search,clear);content.append(tools,count);filter();
    }
    content.append(table);
   }catch(error){if(current===request&&details.open)content.textContent='Saved allocation unavailable. Close and reopen to try again.';}
  });
  return details;
 }
 function paymentRecord(item){
  const details=document.createElement('details');details.className='history-payment history-record';
  const summary=document.createElement('summary');summary.textContent='Payment record';
  const content=document.createElement('div');content.className='history-payment-content history-record-content';details.append(summary,content);
  let request=0,recoveryCandidate='',paymentQuery='';
  const stamp=value=>{const date=new Date(value);return value&&!Number.isNaN(date.getTime())?date.toLocaleString(undefined,{timeZone:'UTC',year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})+' UTC':'Date unavailable';};
  async function loadPayment(message=''){
   const current=++request;if(!details.open)return;
   content.textContent='Loading saved payment…';
   try{
    const record=await get('/api/statements/'+item.statement_hash);
    if(current!==request||!details.open)return;
    item.payout=record.payout;
    for(const row of document.querySelectorAll('.history-row')){
     if(row.dataset.statementHash!==item.statement_hash)continue;
     const status=row.querySelector('.history-status');
     if(status){status.textContent=payoutLabel(item)||contactLabel(item);status.hidden=!status.textContent;}
    }
    content.replaceChildren();
    const payout=record.payout||{},review=payout.provider_review;
    const historical=payout.provider_check?.verified===false;
    const title=document.createElement('p');title.className='history-payment-title';
    title.textContent=historical?'Check unavailable':review?.verified?'Saved recipient outcomes':payout.state==='uncertain'?'Outcome unresolved':'No recipient outcome saved';
    content.append(title);
    const needsBatch=!/^[A-Za-z0-9_-]{1,30}$/.test(payout.payout_batch_id||'');
    let batchInput;
    if(needsBatch){
     const label=document.createElement('label');label.className='field';label.textContent='PayPal batch ID';
     batchInput=document.createElement('input');batchInput.type='text';batchInput.maxLength=30;batchInput.autocomplete='off';batchInput.placeholder='From PayPal Sandbox';batchInput.dataset.historyRecoveryBatch=item.statement_hash;batchInput.value=recoveryCandidate;
     batchInput.addEventListener('input',()=>{recoveryCandidate=batchInput.value;});
     label.append(batchInput);content.append(label);
    }
    const refresh=document.createElement('button');refresh.type='button';refresh.className='btn small ghost';refresh.textContent=needsBatch?'Check batch ID':'Refresh saved status';refresh.dataset.historyPaymentRefresh=item.statement_hash;
    const notice=document.createElement('p');notice.className='history-meta';notice.setAttribute('role','status');notice.textContent=message;notice.hidden=!message;
    refresh.addEventListener('click',async()=>{
     if(needsBatch&&!recoveryCandidate.trim()){notice.hidden=false;notice.textContent='Enter the batch ID from PayPal Sandbox.';batchInput.focus();return;}
     refresh.disabled=true;notice.hidden=false;notice.textContent='Checking saved batch…';
     let failure='';
     try{
      const response=await fetch('/api/statements/refresh',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({statement_hash:item.statement_hash,...(needsBatch?{recovery_batch_id:recoveryCandidate.trim()}:{})})});
      const result=await response.json();
      if(!response.ok)throw Error(result.error||'Saved status could not be checked.');
      if(!result.provider?.verified)failure=result.provider?.message||'The latest check did not verify recipient outcomes.';
     }catch(error){failure=error.message;}
     if(current===request&&details.open)await loadPayment(failure);
    });
    content.append(refresh,notice);
    if(review?.verified){
     const checked=document.createElement('p');checked.className='history-meta';
     checked.textContent=(historical?'Last checked ':'Checked ')+stamp(payout.provider_checked_at);content.append(checked);
    }
    if(historical){const latest=document.createElement('p');latest.className='history-meta';latest.textContent='Latest check unavailable · '+stamp(payout.provider_check.checked_at);content.append(latest);}
    if(!review?.verified||!Array.isArray(review.items))return;
    const people=record.statement.collaborators.filter(person=>person.cents>0);
    const matched=people.map(person=>review.items.filter(outcome=>outcome.name===person.name&&outcome.amount===person.amount&&typeof outcome.recipient==='string'&&outcome.recipient.toLowerCase()===person.email.toLowerCase()));
    if(review.items.length!==people.length||matched.some(rows=>rows.length!==1)){const note=document.createElement('p');note.textContent='Recipient details unavailable';content.append(note);return;}
    const table=document.createElement('table'),head=document.createElement('thead'),heading=document.createElement('tr');
    for(const text of ['Recipient','Amount','Status']){const cell=document.createElement('th');cell.scope='col';cell.textContent=text;heading.append(cell);}head.append(heading);table.append(head);
    const body=document.createElement('tbody'),recipientRows=[];
    people.forEach((person,index)=>{
     const outcome=matched[index][0],row=document.createElement('tr'),name=document.createElement('th'),amount=document.createElement('td'),status=document.createElement('td');
     row.className='history-payment-recipient';name.scope='row';name.textContent=person.name;
     const email=document.createElement('small');email.className='history-payment-email';email.textContent=person.email;name.append(email);
      appendPayoutItemReference(name,outcome,review.items);
     amount.textContent=new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(Number(person.amount));
     status.textContent=(historical?'Last known: ':'')+String(outcome.status||'Not checked').replaceAll('_',' ');
     row.append(name,amount,status);body.append(row);
     const entry={text:(person.name+' '+person.email+' '+payoutItemReference(outcome,review.items)).toLocaleLowerCase(),rows:[row]};recipientRows.push(entry);
     const copy=document.createElement('button');copy.type='button';copy.className='btn small ghost';copy.textContent='Copy payment details';copy.dataset.historyPaymentCopy=String(record.statement.collaborators.indexOf(person));name.append(copy);
     const copyRow=document.createElement('tr'),copyCell=document.createElement('td');copyCell.colSpan=3;
     const copyNote=document.createElement('p');copyNote.className='history-meta';copyNote.setAttribute('role','status');
     const copyText=document.createElement('textarea');copyText.readOnly=true;copyText.rows=9;copyText.setAttribute('aria-label','Personal saved payment details');copyText.hidden=true;
     copyCell.append(copyNote,copyText);copyRow.append(copyCell);copyRow.hidden=true;body.append(copyRow);entry.rows.push(copyRow);entry.copyRow=copyRow;entry.copyShown=false;
     copy.addEventListener('click',async()=>{
      const copyAttempt=++paymentCopyRevision;
      copy.disabled=true;entry.copyShown=true;copyRow.hidden=false;copyNote.textContent='Preparing personal payment details…';copyText.hidden=true;
      try{
       const response=await fetch('/api/statements/payment-copy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({statement_hash:item.statement_hash,collaborator_index:record.statement.collaborators.indexOf(person)})});
       const result=await response.json();if(!response.ok)throw Error(result.error||'Payment details unavailable.');
       if(copyAttempt!==paymentCopyRevision||current!==request||!details.open){copyNote.textContent='Another payment action was selected. Copy these details again if needed.';return;}
       copyText.value=result.text;
       try{await navigator.clipboard.writeText(result.text);if(copyAttempt===paymentCopyRevision&&current===request&&details.open)copyNote.textContent='Personal payment details copied.';}
       catch{if(copyAttempt!==paymentCopyRevision||current!==request||!details.open)return;copyText.hidden=false;copyText.focus();copyText.select();copyNote.textContent='Select and copy these personal payment details.';}
      }catch(error){copyNote.textContent=error.message;}
      finally{copy.disabled=false;}
     });

     if(outcome.reason&&typeof outcome.reason.message==='string'){const reason=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=3;cell.className='history-payment-reason';cell.textContent=outcome.reason.message;reason.append(cell);body.append(reason);entry.rows.push(reason);}
    });
    table.append(body);
    if(people.length>8){
     const label=document.createElement('label');label.className='field';label.textContent='Find a recipient';
     const search=document.createElement('input');search.type='search';search.placeholder='Name, email or PayPal item';search.autocomplete='off';search.dataset.paymentSearch=item.statement_hash;search.value=paymentQuery;label.append(search);
     const clear=document.createElement('button');clear.type='button';clear.className='btn small ghost';clear.textContent='Show all recipients';clear.dataset.clearPaymentSearch=item.statement_hash;
     const count=document.createElement('p');count.className='history-meta';count.setAttribute('role','status');
     const filter=()=>{
      paymentQuery=search.value;const query=paymentQuery.trim().toLocaleLowerCase();let visible=0;
      for(const entry of recipientRows){const match=!query||entry.text.includes(query);for(const row of entry.rows)row.hidden=!match||(row===entry.copyRow&&!entry.copyShown);if(match)visible++;}
      count.textContent=visible===0?'No recipient matches this name, email or PayPal item.':visible===people.length?people.length+' recipients':visible+' of '+people.length+' recipients';
      clear.hidden=!query;
     };
     search.addEventListener('input',filter);clear.addEventListener('click',()=>{search.value='';filter();search.focus();});
     content.append(label,clear,count);filter();
    }
    content.append(table);
   }catch(error){if(current===request&&details.open)content.textContent='Payment record unavailable. Close and reopen to try again.';}
  }
  details.addEventListener('toggle',()=>loadPayment());
  return details;
 }
 function makeRow(item,recent=false,earlier=false) {
    const row=document.createElement('li');row.className='history-row'+(item.statement_hash===currentSavedHash?' history-active':'');
    row.dataset.statementHash=item.statement_hash;
    const identity=document.createElement('div');
    const name=document.createElement('div');name.className='history-name';name.textContent=item.project;
    const meta=document.createElement('div');meta.className='history-meta';
    const saved=new Date(item.updated_at||item.saved_at);
    const savedLabel=earlier?saved.toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}):saved.toLocaleDateString();
    meta.textContent=(item.period_label?item.period_label+' · ':'')+(item.reporting_period?periodCaption(item.reporting_period)+' · ':'')+item.collaborator_count+' '+(item.collaborator_count===1?'creator':'creators')+' · '+item.transaction_count+' '+(item.transaction_count===1?'transaction':'transactions')+' · Saved '+savedLabel;
    const status=document.createElement('div');status.className='history-meta history-status';status.textContent=payoutLabel(item)||contactLabel(item);status.hidden=!status.textContent;
    const reference=document.createElement('div');reference.className='history-meta history-reference';reference.textContent='Ref. '+item.statement_hash.slice(0,12);reference.title=item.statement_hash;
    identity.append(name,meta,reference,status);
    const actions=document.createElement('div');const amount=document.createElement('div');amount.className='history-amount';amount.textContent=new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(Number(item.net));
    const buttons=document.createElement('div');buttons.className='history-buttons';
    for(const [text,next] of [['Open statement',false],['Start next period',true]]) {
     const button=document.createElement('button');button.type='button';button.className='btn small ghost';button.textContent=text;button.dataset[recent?'recentAction':'historyAction']=next?'next':'open';
     button.addEventListener('click',()=>open(item.statement_hash,next,button));buttons.append(button);
    }
    const netLabel=document.createElement('span');netLabel.className='history-net-label';netLabel.textContent='Net receipts';amount.prepend(netLabel);
    actions.append(amount,buttons);row.append(identity,actions,calculationRecord(item));if(item.payout)row.append(paymentRecord(item));if(!recent){const balances=balanceTable(item);if(balances)row.append(balances);}return row;
 }
 function balanceTable(item) {
  const balances=item.advance_balances;if(!balances)return null;
  const section=document.createElement('section');section.className='history-balances';
  const table=document.createElement('table');const caption=document.createElement('caption');caption.textContent='Advance balances · USD';table.append(caption);
  const head=document.createElement('thead'),heading=document.createElement('tr');
  for(const label of ['Creator','Opening','Recovered','Remaining']){const cell=document.createElement('th');cell.scope='col';cell.textContent=label;heading.append(cell);}head.append(heading);table.append(head);
  const body=document.createElement('tbody');
  for(const balance of balances.entries){const row=document.createElement('tr');const name=document.createElement('th');name.scope='row';name.textContent=balance.recipient_name;row.append(name);
   for(const [key,label] of [['opening_cents','Opening'],['recovered_cents','Recovered'],['closing_cents','Remaining']]){const cell=document.createElement('td');cell.dataset.label=label;cell.textContent=new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(balance[key]/100);if(cell.textContent.length>9)section.classList.add('history-balances-wide');row.append(cell);}body.append(row);}
  table.append(body);section.append(table);
  const continuity=document.createElement('div');continuity.className='history-continuity';
  const referenceLabel=reference=>reference.period_label||(reference.reporting_period?periodCaption(reference.reporting_period):'saved period');
  const link=(prefix,reference)=>{
   const part=document.createElement('span'),button=document.createElement('button');part.append(prefix);
   button.type='button';button.className='history-predecessor';button.textContent=referenceLabel(reference);button.dataset.balanceReference=reference.statement_hash;
   button.addEventListener('click',()=>open(reference.statement_hash,false,button));part.append(button);continuity.append(part);
  };
  if(balances.source)link('Opening reviewed from ',balances.source);
  else{const note=document.createElement('span');note.textContent=balances.source_missing?'Opening source is missing':'Opening entered for this statement';continuity.append(note);}
  if(balances.successor)link('Continued in ',balances.successor);
  section.append(continuity);return section;
 }
 function periodGroups(items) {
  const groups=new Map();
  for(const item of items){const key=item.saved_period_key||item.statement_hash;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(item);}
  return [...groups.values()];
 }
 function makePeriodRow(items) {
  const row=makeRow(items[0]);if(items.length===1)return row;
  const earlier=items.slice(1),copies=document.createElement('details');copies.className='history-copies';
  const title=document.createElement('summary');
  title.textContent=earlier.length+' earlier saved '+(earlier.length===1?'copy':'copies')+(earlier.some(item=>item.payout)?' · payout recorded':'');
  const versions=document.createElement('ul');versions.className='history-copy-list';
  for(const item of earlier)versions.append(makeRow(item,false,true));
  copies.open=earlier.some(item=>item.statement_hash===currentSavedHash);
  copies.append(title,versions);row.append(copies);return row;
 }
 let loadedStatements=[],nextCursor=null,loadedQuery='';
 function renderHistoryRows(){
  const expanded=new Set([...list.querySelectorAll('details[open]')].map(d=>[d.closest('[data-statement-hash]')?.dataset.statementHash,d.className].join('|')));
  const groups=periodGroups(loadedStatements);
  list.replaceChildren();
  for(const items of groups)list.append(makePeriodRow(items));
  for(const d of list.querySelectorAll('details'))if(expanded.has([d.closest('[data-statement-hash]')?.dataset.statementHash,d.className].join('|')))d.open=true;
  summary.textContent='Saved statements'+(groups.length?' · '+groups.length+(nextCursor?'+':''):'');
  note.textContent=loadedStatements.length
   ?(nextCursor?'Showing '+loadedStatements.length+' saved statements. Earlier statements are available.':loadedStatements.length>100?'Showing all '+loadedStatements.length+' matching saved statements.':'')
   :(search.value?'No saved statement matches this search.':'No saved statements yet.');
  loadMore.hidden=!nextCursor;loadMore.disabled=false;
 }
 async function refresh() {
  const request=++requestNumber,query=search.value;
  nextCursor=null;loadMore.hidden=true;
  note.textContent='Loading saved statements…';
  try {
   const result=await get('/api/statements?query='+encodeURIComponent(query));
   const recent=query?await get('/api/statements?query='):result;
   if(request!==requestNumber||search.value!==query)return;
   loadedStatements=result.statements;loadedQuery=query;nextCursor=result.next_cursor;
   renderHistoryRows();
   const newest=recent.statements[0];latestList.replaceChildren();latest.hidden=!newest;
   if(newest)latestList.append(makeRow(newest,true));refreshDraftShortcut();
  } catch(e){if(request===requestNumber&&search.value===query){note.textContent=e.message;}}
 }
 loadMore.addEventListener('click',async()=>{
  if(!nextCursor||loadMore.disabled||search.value!==loadedQuery)return;
  const request=requestNumber,query=loadedQuery,cursor=nextCursor;
  loadMore.disabled=true;note.textContent='Loading earlier statements…';
  try{
   const result=await get('/api/statements?query='+encodeURIComponent(query)+'&cursor='+encodeURIComponent(cursor));
   if(request!==requestNumber||search.value!==query)return;
   const known=new Set(loadedStatements.map(item=>item.statement_hash));
   const added=result.statements.filter(item=>!known.has(item.statement_hash));
   loadedStatements.push(...added);
   nextCursor=result.next_cursor;renderHistoryRows();
   const first=added.length?[...list.querySelectorAll('[data-statement-hash]')].find(row=>row.dataset.statementHash===added[0].statement_hash):null;
   if(first&&$('historyDialog').open){
    const copies=first.closest('.history-copies');if(copies)copies.open=true;
    first.tabIndex=-1;first.focus({preventScroll:true});first.scrollIntoView({block:'start',behavior:'instant'});
   }
  }catch(error){if(request===requestNumber&&search.value===query){note.textContent=error.message;loadMore.disabled=false;}}
 });
 let paymentNavigation=0;
 $('historyDialog').addEventListener('close',()=>{paymentNavigation++;if(note.textContent==='Loading recorded payment…')note.textContent='';});
 window.reviewRecordedPayment=async (digest,project)=>{
  const navigation=++paymentNavigation,dialog=$('historyDialog');
  panel.open=true;if(!dialog.open)dialog.showModal();search.value=project;
  note.textContent='Loading recorded payment…';
  try{
   const record=await get('/api/statements/'+encodeURIComponent(digest));
   if(navigation!==paymentNavigation||!dialog.open||search.value!==project)return;
   if(!record.payout)throw Error('The saved statement has no recorded payment.');
   await refresh();
   if(navigation!==paymentNavigation||!dialog.open||search.value!==project)return;
   let row=[...list.querySelectorAll('.history-row')].find(item=>item.dataset.statementHash===digest);
   if(!row){
    const item={...record,...record.statement,collaborator_count:record.statement.collaborators.length,transaction_count:record.statement.transactions.length};
    loadedStatements.unshift(item);
    row=makeRow(item);list.prepend(row);
    note.textContent='Selected recorded payment and latest project statements.';
   }
   for(let parent=row.parentElement;parent&&parent!==panel;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;
   const payment=row.querySelector('.history-payment');payment.open=true;
   const heading=payment.querySelector('summary');heading.focus();heading.scrollIntoView({block:'start',behavior:'instant'});
  }catch(error){if(navigation===paymentNavigation&&dialog.open&&search.value===project)note.textContent='Recorded payment could not be opened. Close and try again.';}
 };
 async function open(digest,next,button) {
  const draft=currentDraftSnapshot();
  const hasInput=[draft.project,draft.agreement,draft.sales,draft.period_label,...Object.values(draft.reporting_period||{}),...Object.values(draft.statement_context||{})].some(value=>typeof value==='string'&&value.trim()) ||
   draft.people.some(person=>Object.entries(person).some(([key,value])=>key!=='draft_row_id'&&typeof value==='string'&&value.trim())) ||
   !!(draft.mapping_draft||draft.advance_recovery||draft.advance_candidate||draft.source_provenance||draft.agreement_review||draft.source_date_review);
  if(hasInput && !window.confirm((next?'Start the next period?':'Open this saved statement?')+' Your current draft will be kept in Saved draft copies. Saved statements and payout records will remain.'))return;
  const opening=++openingNumber,submitted=JSON.stringify(currentDraftSnapshot()),messageRevision=statusRevision;
  const current=()=>{
   if(opening!==openingNumber)return false;
   if(JSON.stringify(currentDraftSnapshot())===submitted)return true;
   const message='Your draft changed while this saved statement was opening. Your current work was kept. Open the saved statement again when ready.';
   note.textContent=message;if(statusRevision===messageRevision)setStatus(message);
   return false;
  };
  button.disabled=true;
  try {
   const record=await get('/api/statements/'+digest);
   if(!current())return;
   const source=record.project_data;
   // Recheck saved inputs before opening. Unsupported agreement terms remain
   // editable as an uncalculated draft; they never restore payment approval.
   let calculated=null,sourceIssue=null;
   if(!next){
    try{calculated=await api('/api/preview',source);}
    catch(error){if(!error.agreementIssue)throw error;sourceIssue=error.agreementIssue;}
   }
   if(!current())return;
   if(calculated && calculated.statement_hash!==record.statement.statement_hash)
    throw Error('The current calculator differs from this saved statement. Your current draft was kept; use the saved review JSON before recalculating.');
   if(calculated?.agreement_review)source.agreement_review=calculated.agreement_review;
   await draftSavePromise;
   if(!current())return;
   if(hasInput){
    try{retainDraftCopy(JSON.parse(submitted));sessionStorage.setItem(DRAFT_ALTERNATE_KEY,submitted);}
    catch{throw Error('Your current draft could not be kept. Nothing was replaced. Download the current draft or free device storage before opening saved work.');}
   }
   restoringDraft=true;
   try {
    sourceDateReview=!next&&source.source_date_review===true;restoreProjectIdentity(source.project_id);restoreSourceProvenance(next?null:source.source_provenance);restoreStatementContext(source.statement_context);restoreAdvanceRecovery(source.advance_recovery,next);
    $('project').value=source.project;$('agreement').value=source.agreement;
    $('sales').value=next?'':source.sales_csv;$('periodStart').value=next?'':source.reporting_period?.start||'';$('periodEnd').value=next?'':source.reporting_period?.end||'';$('people').replaceChildren();
    for(const person of source.collaborators)addPerson(person);
    restoreAgreementReview(next||sourceIssue?null:source.agreement_review);
    illustrative=source.illustrative===true;invalidate();
   }finally{restoringDraft=false;}
   if(next)proposeAdvanceOpening(record);
   period.value=next?'':record.period_label;saveDraft();
   currentSavedHash=next||sourceIssue?null:digest;
   if(next){
    panel.open=false;
    window.showDeskView?.('sales');
    statusAnchor=$('sales');
    setStatus('New period started for '+source.project+'. The agreement and creators were copied. Enter only this period’s transactions, then calculate and review a new statement.'+(source.advance_recovery?' Review the opening advance balance in Splits for this period.':''));
    if(source.statement_context?.payment_note?.trim()){
     const reminder=document.createElement('p');reminder.textContent='The note to creators was copied too. Check its dates and payment instructions before sharing.';
     const review=document.createElement('button');review.id='reviewCopiedNote';review.type='button';review.className='btn small';review.textContent='Review copied note';
     review.addEventListener('click',()=>editStatementContact($('paymentNote')));
     $('status').append(reminder,review);
    }
    $('sales').focus();$('sales').scrollIntoView({behavior:'smooth',block:'center'});
   }else if(sourceIssue){
    panel.open=false;window.showDeskView?.('splits');$('agreementEditor').open=true;
    statusAnchor=$('agreement');
    setStatus('Opened saved source for review. '+sourceIssue.reason,true);
    showAgreementIssue(sourceIssue);
   }else{
    lastInput=source;render(calculated);
    const payout=payoutLabel({illustrative:source.illustrative,payout:record.payout});
    setStatus('Opened '+source.project+(record.period_label?' · '+record.period_label:'')+(payout?'. '+payout:'')+'.');
   }
   await refresh();
   if(hasInput){showDraftUndo();showDraftCopies();}
  }catch(e){if(opening===openingNumber){note.textContent=e.message;if(statusRevision===messageRevision)setStatus(e.message,true);}}
  finally{button.disabled=false;}
 }
 saveButton.addEventListener('click',async()=>{
  if(!last||!lastInput)return setStatus('Calculate a statement before saving it.',true);
  const digest=last.statement_hash;
  const source=lastInput;
  const label=period.value;
  const submitted=JSON.stringify(currentDraftSnapshot()),messageRevision=statusRevision;
  const canReport=()=>statusRevision===messageRevision||!$('status').textContent.trim();
  saveButton.disabled=true;
  try {
   const record=await api('/api/statements',{project_data:source,statement_hash:digest,period_label:label});
   currentSavedHash=digest;await refresh();
   if(canReport()){
    const unchanged=JSON.stringify(currentDraftSnapshot())===submitted;
    setStatus((unchanged?'Saved ':'Saved the earlier calculation for ')+record.statement.project+(record.period_label?' · '+record.period_label:'')+(unchanged?'.':'. Your newer draft was kept. Calculate and save it separately.'));
   }
  }catch(e){if(canReport())setStatus(e.message,true);}
  finally{saveButton.disabled=false;}
 });
 window.addEventListener('royalty-history-restored',refresh);
 search.addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(refresh,180);});
 panel.addEventListener('toggle',()=>{if(panel.open)refresh();});
 refreshDraftShortcut();
 // A payout stores its reviewed inputs server-side, so reopening the list reveals it.
 refresh();
})();


(() => {
 const root=document.createElement('details');root.id='deskBackup';root.className='desk-backup';
 root.innerHTML='<summary>Back up or move work</summary><p class="history-notice">Current draft includes the agreement, sales and creator details in this browser. Saved-desk backup includes saved statements, original exports and payout records.</p><div class="actions"><button type="button" class="btn small" id="downloadCurrentDraft">Download current draft</button><button type="button" class="btn small" id="downloadDeskBackup">Download saved-desk backup</button><label class="field">Open saved-desk backup<input type="file" id="deskBackupFile" accept=".json,application/json"></label></div><p id="deskBackupStatus" class="history-notice" role="status"></p><section id="deskBackupBlocked" hidden aria-labelledby="deskBackupBlockedTitle"><h3 id="deskBackupBlockedTitle">This saved period needs attention</h3><label id="deskBackupBlockedChoice" class="field" hidden>Period to review<select id="deskBackupBlockedPeriod"></select></label><p id="deskBackupBlockedIdentity"></p><p id="deskBackupBlockedReason"></p><blockquote id="deskBackupBlockedQuote"></blockquote><section id="deskBackupBlockedPayout" hidden aria-labelledby="deskBackupBlockedPayoutTitle"><h3 id="deskBackupBlockedPayoutTitle">Keep the recorded payout with this period</h3><p id="deskBackupBlockedPayoutState"></p><p id="deskBackupBlockedPayoutReference" style="overflow-wrap:anywhere"></p><button type="button" class="btn small" id="copyBlockedPayoutRequest">Copy request</button><p id="blockedPayoutCopyStatus" class="history-notice" role="status"></p><label id="blockedPayoutCopyFallback" class="field" hidden>Original payout request<textarea id="blockedPayoutCopyText" readonly rows="3"></textarea></label><p>A correction copy would leave this payment history behind. Open the original desk to review the recorded request before preparing an adjustment. The backup and original source downloads remain available.</p></section><p class="history-notice">Nothing was restored. Keep this complete backup, including its payout records.</p><button type="button" class="btn" id="prepareBlockedSourceCopy" hidden>Prepare correction copy</button><details><summary>Original agreement</summary><pre id="deskBackupBlockedAgreement"></pre><button type="button" class="btn small" id="downloadBlockedAgreement">Download original agreement</button></details><details><summary>Original sales export</summary><pre id="deskBackupBlockedSales"></pre><button type="button" class="btn small" id="downloadBlockedSales">Download original export</button></details><details id="deskBackupBlockedMapped" hidden><summary>Mapped sales rows used by the saved statement</summary><pre id="deskBackupBlockedMappedSales"></pre><button type="button" class="btn small" id="downloadBlockedMappedSales">Download mapped rows</button></details><button type="button" class="btn ghost small" id="dismissDeskBackupBlocked">Close source details</button></section><div id="deskBackupPreview" hidden><h3 id="deskBackupTitle"></h3><p id="deskBackupSummary"></p><p class="history-notice">Your current browser draft stays open. Saved payout records retain their historical status; check the provider before acting.</p><div class="actions"><button type="button" class="btn" id="restoreDeskBackup">Restore desk</button><button type="button" class="btn ghost" id="cancelDeskBackup">Cancel</button></div><ul id="deskBackupProjects" class="backup-statements" aria-label="Saved periods in this backup"></ul></div>';
 const style=document.createElement('style');style.textContent='.desk-backup{border-top:1px solid var(--line);margin-top:18px;padding-top:18px}.desk-backup>summary{font-weight:650;cursor:pointer;min-height:32px}.desk-backup .actions{align-items:end;gap:12px}.desk-backup .field{min-width:0;max-width:100%;font-size:13px}.desk-backup input[type=file]{max-width:100%;font-size:13px}.desk-backup ul{padding-left:20px;overflow-wrap:anywhere}.desk-backup h3{font-size:18px;margin-top:18px}.desk-backup p{line-height:1.55}.desk-backup pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:360px;overflow:auto;font-size:13px}.desk-backup blockquote{margin:12px 0;padding:12px;border-left:3px solid var(--line);overflow-wrap:anywhere}.desk-backup details{margin-block:12px}';style.textContent+='.desk-backup .backup-statements{list-style:none;padding:0;margin:16px 0}.backup-statement{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:12px 0;border-block-start:1px solid var(--line);align-items:start}.backup-statement .history-name{font-size:15px}.backup-statement-amount{display:flex;flex-direction:column;gap:3px;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}.backup-statement-amount strong{font-size:16px}@media(max-width:600px){.backup-statement{grid-template-columns:minmax(0,1fr);gap:6px}.backup-statement-amount{flex-direction:row;justify-content:space-between;gap:12px;text-align:left}.backup-statement-amount strong{font-size:15px}}';document.head.append(style);
 $('statementHistory').append(root);
 let pending=null,blockedRecord=null,blockedBackup=null,epoch=0,busy=false,payoutCopyRevision=0;
 const status=message=>{$('deskBackupStatus').textContent=message;};
 function resetPayoutCopy(){payoutCopyRevision++;$('copyBlockedPayoutRequest').disabled=false;$('blockedPayoutCopyStatus').textContent='';$('blockedPayoutCopyFallback').hidden=true;$('blockedPayoutCopyText').value='';}
 function clear(){epoch++;pending=null;blockedRecord=null;blockedBackup=null;resetPayoutCopy();$('deskBackupPreview').hidden=true;$('deskBackupBlocked').hidden=true;}
 $('dismissDeskBackupBlocked').addEventListener('click',clear);
 $('copyBlockedPayoutRequest').addEventListener('click',async()=>{
  const record=blockedRecord,request=record?.recorded_payout?.sender_batch_id;if(!request)return;
  const revision=++payoutCopyRevision,button=$('copyBlockedPayoutRequest');button.disabled=true;
  $('blockedPayoutCopyFallback').hidden=true;$('blockedPayoutCopyStatus').textContent='Copying original request…';$('blockedPayoutCopyText').value=request;
  const current=()=>record===blockedRecord&&revision===payoutCopyRevision;
  try{await navigator.clipboard.writeText(request);if(current())$('blockedPayoutCopyStatus').textContent='Original request copied.';}
  catch{if(current()){$('blockedPayoutCopyFallback').hidden=false;$('blockedPayoutCopyText').focus();$('blockedPayoutCopyText').select();$('blockedPayoutCopyStatus').textContent='Select and copy the original request.';}}
  finally{if(current())button.disabled=false;}
 });
 $('prepareBlockedSourceCopy').addEventListener('click',()=>{
  const record=blockedRecord;if(!record?.correction_source||!record.agreement_issue)return;
  try{window.previewStatementSourceCorrection(record.correction_source,record.period_label,record.agreement_issue,[record.project,record.period_label].filter(Boolean).join(' · '));}
  catch(error){status('Could not prepare source copy: '+error.message);}
 });
 function showBlocked(error,backup=blockedBackup){
  status(error.message);const record=error.backupStatement;if(!record)return;
  blockedRecord=record;blockedBackup=backup;resetPayoutCopy();
  const choices=Array.isArray(record.blocked_periods)?record.blocked_periods:[];
  const select=$('deskBackupBlockedPeriod');select.replaceChildren();select.disabled=false;
  for(const item of choices){
   const option=document.createElement('option');option.value=item.statement_hash;
   const dates=item.reporting_period;
   option.textContent=[item.project,item.period_label,dates?.start&&dates?.end?dates.start+' – '+dates.end:'','Ref. '+item.statement_hash.slice(0,12)].filter(Boolean).join(' · ');
   select.append(option);
  }
  select.value=record.statement_hash||'';
  $('deskBackupBlockedChoice').hidden=choices.length<2;
  $('deskBackupBlockedTitle').textContent=choices.length>1?choices.length+' saved periods need attention':'This saved period needs attention';
  $('prepareBlockedSourceCopy').disabled=false;
  $('prepareBlockedSourceCopy').hidden=!record.correction_source||!record.agreement_issue;
  for(const [id,key] of [['downloadBlockedAgreement','agreement'],['downloadBlockedSales','original_csv'],['downloadBlockedMappedSales','sales_csv']])$(id).disabled=typeof record[key]!=='string'||!record[key];
  const period=record.reporting_period;
  $('deskBackupBlockedIdentity').textContent=[record.project,record.period_label,period?.start&&period?.end?period.start+' – '+period.end:''].filter(Boolean).join(' · ');
  $('deskBackupBlockedReason').textContent=error.message;
  const payout=record.recorded_payout;
  $('deskBackupBlockedPayout').hidden=!payout;
  $('deskBackupBlockedPayoutState').textContent=payout?({intent:'A payout request was recorded. Its outcome is not confirmed.',uncertain:'The recorded payout outcome is unknown.',submitted:'This period has a submitted payout record. This backup does not establish its current outcome.'}[payout.state]||'This period has a recorded payout.') : '';
  $('deskBackupBlockedPayoutReference').textContent=payout?'Original request: '+payout.sender_batch_id:'';
  const quote=record.agreement_issue?.source_quote||'';
  $('deskBackupBlockedQuote').textContent=quote;$('deskBackupBlockedQuote').hidden=!quote;
  $('deskBackupBlockedAgreement').textContent=record.agreement||'No agreement text saved.';
  $('deskBackupBlockedSales').textContent=record.original_csv||'No sales export saved.';
  $('deskBackupBlockedMappedSales').textContent=record.sales_csv||'';
  $('deskBackupBlockedMapped').hidden=record.original_csv===record.sales_csv;
  $('deskBackupBlocked').hidden=false;$('deskBackupBlockedTitle').scrollIntoView({block:'start',behavior:'smooth'});
 }
 $('deskBackupBlockedPeriod').addEventListener('change',async()=>{
  if(!blockedBackup)return;
  const backup=blockedBackup,previous=blockedRecord,selected=$('deskBackupBlockedPeriod').value,version=++epoch;
  blockedRecord=null;resetPayoutCopy();
  $('deskBackupBlockedPeriod').disabled=true;
  for(const id of ['prepareBlockedSourceCopy','downloadBlockedAgreement','downloadBlockedSales','downloadBlockedMappedSales','copyBlockedPayoutRequest'])$(id).disabled=true;
  status('Opening the selected saved source…');
  try{
   await api('/api/desk/preview',{backup,statement_hash:selected});
   if(version===epoch)throw Error('This period no longer needs source review. Open the backup again.');
  }catch(error){
   if(version!==epoch)return;
   if(error.backupStatement){showBlocked(error,backup);return;}
   showBlocked({message:error.message,backupStatement:previous},backup);
  }
 });
 for(const [id,key,suffix,type] of [
  ['downloadBlockedAgreement','agreement','agreement.txt','text/plain;charset=utf-8'],
  ['downloadBlockedSales','original_csv','original-export.csv','text/csv;charset=utf-8'],
  ['downloadBlockedMappedSales','sales_csv','mapped-rows.csv','text/csv;charset=utf-8']
 ])$(id).addEventListener('click',()=>{
  if(!blockedRecord||typeof blockedRecord[key]!=='string')return;
  const slug=value=>String(value||'').normalize('NFKD').replace(/[^a-zA-Z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,70);
  const period=blockedRecord.reporting_period;
  const stem=[slug(blockedRecord.project)||'saved-period',slug(blockedRecord.period_label),slug(period?.start),slug(period?.end)].filter(Boolean).join('-');
  const url=URL.createObjectURL(new Blob([blockedRecord[key]],{type})),link=document.createElement('a');
  link.href=url;link.download=stem+'-'+suffix;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 });
 $('downloadCurrentDraft').addEventListener('click',()=>{
  downloadSavedDraftCopy({parsed:currentDraftSnapshot(),key:'current'});
  status('Current draft downloaded. On the other desk, choose Open a statement or draft file. Saved statements and payout records are separate.');
 });
 $('downloadDeskBackup').addEventListener('click',async()=>{
  const button=$('downloadDeskBackup');button.disabled=true;
  try{
   const data=await api('/api/desk/export',{});
   const blob=new Blob([JSON.stringify(data)],{type:'application/json'});
   const url=URL.createObjectURL(blob),link=document.createElement('a');
   link.href=url;link.download='royalty-loom-saved-desk-'+new Date(data.exported_at).toISOString().replace(/[:.]/g,'-')+'.json';link.click();
   setTimeout(()=>URL.revokeObjectURL(url),1000);
   status('Private backup downloaded: '+data.statements.length+' saved statements and '+data.batches.length+' recorded payout intents.');
  }catch(error){status(error.message);}finally{button.disabled=false;}
 });
 $('deskBackupFile').addEventListener('change',async()=>{
  clear();const file=$('deskBackupFile').files[0],version=epoch;
  if(!file)return;
  status('Checking saved sources and recorded payout identities…');
  let backup;
  try{
   if(file.size>32000000)throw Error('Choose a saved-desk backup up to 32 MB. Larger desks use the complete database importer.');
   backup=JSON.parse(await file.text());
   const result=await api('/api/desk/preview',{backup});
   if(version!==epoch)return;
   pending={backup,hash:result.backup_hash};
   $('deskBackupTitle').textContent='Saved '+new Date(result.exported_at).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'});
   $('deskBackupSummary').textContent=result.statement_count+' saved '+(result.statement_count===1?'statement':'statements')+' · '+result.payout_count+' recorded payout '+(result.payout_count===1?'intent':'intents')+' · '+result.projects.length+' '+(result.projects.length===1?'project':'projects');
   const list=$('deskBackupProjects');list.replaceChildren();
   for(const record of result.statement_previews){
    const item=document.createElement('li');item.className='backup-statement';item.dataset.statementHash=record.statement_hash;
    const identity=document.createElement('div');
    const name=document.createElement('div');name.className='history-name';name.textContent=record.project;
    const label=document.createElement('div');label.className='history-meta';label.textContent=record.period_label;label.hidden=!record.period_label;
    const dates=document.createElement('div');dates.className='history-meta';
    dates.textContent=record.reporting_period?.start&&record.reporting_period?.end?record.reporting_period.start+' – '+record.reporting_period.end:'No reporting dates saved';
    identity.append(name,label,dates);
    if(record.payout_recorded){const payout=document.createElement('div');payout.className='history-meta';payout.textContent='Recorded payout intent';identity.append(payout);}
    const amount=document.createElement('div');amount.className='backup-statement-amount';
    const amountLabel=document.createElement('span');amountLabel.className='history-meta';amountLabel.textContent='Net receipts';
    const value=document.createElement('strong');value.textContent=record.currency+' '+record.net;
    amount.append(amountLabel,value);item.append(identity,amount);list.append(item);
   }
   $('deskBackupPreview').hidden=false;status('Preview only. No saved work has been added.');$('deskBackupTitle').scrollIntoView({block:'start',behavior:'smooth'});
  }catch(error){if(version===epoch)showBlocked(error,backup);}finally{$('deskBackupFile').value='';}
 });
 $('cancelDeskBackup').addEventListener('click',()=>{if(busy)return;clear();status('Cancelled. No saved work was added.');});
 $('restoreDeskBackup').addEventListener('click',async()=>{
  if(!pending||busy)return;
  const selected=pending;busy=true;
  for(const id of ['restoreDeskBackup','cancelDeskBackup','deskBackupFile'])$(id).disabled=true;
  try{
   const result=await api('/api/desk/restore',{backup:selected.backup,backup_hash:selected.hash});
   clear();status('Restored '+result.statement_count+' saved statements and '+result.payout_count+' recorded payout intents. Open a saved statement to continue; your current draft was kept.');
   window.dispatchEvent(new Event('royalty-history-restored'));
  }catch(error){status(error.message);}finally{
   busy=false;for(const id of ['restoreDeskBackup','cancelDeskBackup','deskBackupFile'])$(id).disabled=false;
  }
 });
})();
