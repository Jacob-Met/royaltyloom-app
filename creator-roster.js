/* Recipient editing stays connected to the existing draft and calculator. */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const people = $('people');
if (!people || $('creatorRosterTools')) return;
const style = document.createElement('style');
style.textContent = "\n#creatorRosterTools{margin:0}\n.roster-balance{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;border-bottom:1px solid var(--line);padding:8px 0 10px}\n.roster-balance strong{font-size:20px;font-variant-numeric:tabular-nums;color:var(--accent)}\n.roster-balance span{font-size:13px;color:var(--muted)}\n.roster-balance[data-state=\"over\"] strong,.roster-balance[data-state=\"invalid\"] strong{color:var(--red)}\n.roster-toolbar{display:flex;align-items:end;gap:14px;margin:10px 0}\n.roster-toolbar>label:first-child{flex:1;max-width:430px;font-size:12px;font-weight:650}\n.roster-toolbar input[type=\"search\"]{display:block;box-sizing:border-box;width:100%;min-width:0;min-height:42px;padding:9px 11px;border:1px solid var(--line);background:var(--bg);color:var(--ink);font:inherit;border-radius:3px;margin-top:0}\n.roster-attention{display:flex;align-items:center;gap:7px;font-size:12px;padding-bottom:9px}\n.roster-attention input{width:17px;height:17px;accent-color:var(--accent)}\n.roster-balance .roster-count{margin:0 0 0 auto;font-size:12px;color:var(--muted)}\n.roster-search-label{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}\n.roster-head{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.35fr) 90px 69px;gap:10px;padding:8px 0;font-size:12px;font-weight:650;color:var(--muted);border-bottom:2px solid var(--line)}\n#people{border-bottom:1px solid var(--line)}\n#people .person{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.35fr) 90px 69px;gap:0 10px;background:transparent;border:0;border-bottom:1px solid var(--line);border-radius:0;padding:12px 0;margin:0;min-width:0}\n#people .person:last-child{border-bottom:0}#people .person[hidden]{display:none}\n#people .person .grid2{display:contents}\n#people .person .field{margin:0;min-width:0}\n#people .person input{min-width:0;padding:9px 10px;min-height:42px}\n#people .person .person-header{grid-column:4;grid-row:1;justify-content:end;align-items:start}\n#people .person .person-header strong{display:none}\n#people .person .person-header button{font-size:11px;padding:9px 7px;min-height:42px;color:var(--muted);border-color:var(--line);background:transparent}\n#people .person .person-header button:hover{color:var(--red);border-color:var(--red)}\n#people .roster-name{grid-column:1;grid-row:1}#people .roster-email{grid-column:2;grid-row:1}#people .roster-share{grid-column:3;grid-row:1}\n#people .roster-share input{text-align:right;font-variant-numeric:tabular-nums}\n#people .person .grid2 label{font-size:0;margin:0}#people .person .grid2 input{font-size:14px}\n#people .person .roster-source{grid-column:1/-1;margin-top:8px;min-width:0}\n.roster-source summary{font-size:12px;color:var(--muted);cursor:pointer;padding:3px 0;overflow-wrap:anywhere}\n.roster-source summary[data-issue=\"true\"]{color:var(--red)}\n.roster-source .field{padding:10px 0 4px}.roster-source .hint{margin:5px 0}.roster-source input{font-size:13px}\n.roster-source summary:focus-visible,.roster-toolbar :focus-visible{outline:3px solid var(--accent);outline-offset:3px}\n.roster-empty{font-size:14px;padding:20px 0;margin:0}\n@media(max-width:600px){\n.roster-toolbar{flex-wrap:wrap;gap:10px}.roster-toolbar>label:first-child{flex-basis:100%;max-width:none}.roster-attention{padding:0}.roster-head{display:none}\n#people .person{grid-template-columns:minmax(0,1fr) 77px 55px;padding:14px 0;gap:8px}\n#people .person .person-header{grid-column:3;grid-row:1;align-self:end}\n#people .roster-name{grid-column:1;grid-row:1}#people .roster-share{grid-column:2;grid-row:1}#people .roster-email{grid-column:1/-1;grid-row:2}\n#people .person .grid2 label{font-size:11px}#people .person .grid2 input{margin-top:4px;font-size:14px}\n#people .person .person-header button{font-size:10px;padding:9px 4px}\n#people .person .roster-source{margin-top:0}.roster-balance{gap:4px 9px}.roster-balance strong{font-size:19px}\n}";
document.head.append(style);
const tools = document.createElement('div');
tools.id = 'creatorRosterTools';
tools.innerHTML = '<div class="roster-balance" id="rosterBalance" aria-live="polite"><strong id="rosterAssigned"></strong><span id="rosterBalanceHint"></span><p class="roster-count" id="rosterCount" role="status"></p></div><div class="roster-toolbar"><label for="rosterSearch"><span class="roster-search-label">Find a collaborator</span><input type="search" id="rosterSearch" placeholder="Find name or recipient email" autocomplete="off"></label><label class="roster-attention"><input type="checkbox" id="rosterAttention">Show entries to finish</label><button class="btn small ghost" type="button" id="rosterClear">Show everyone</button></div><div class="roster-head" aria-hidden="true"><span>Creator</span><span>Recipient email</span><span>Net share</span><span></span></div>';
people.before(tools);
const contactButton=document.createElement('button');
contactButton.id='reviewSavedContacts';contactButton.type='button';contactButton.className='btn small ghost';
contactButton.textContent='Saved contacts';
tools.querySelector('.roster-toolbar').append(contactButton);
const contactPanel=document.createElement('section');
contactPanel.id='savedContactReview';contactPanel.hidden=true;contactPanel.className='saved-contact-review';
contactPanel.setAttribute('aria-label','Review saved contacts');tools.querySelector('.roster-toolbar').after(contactPanel);
style.textContent+='\n.saved-contact-review{border:1px solid var(--line);padding:16px;margin:14px 0}.saved-contact-review h3{font-size:16px;margin:0 0 12px}.saved-contact-review p{font-size:12px;color:var(--muted);overflow-wrap:anywhere}.saved-contact-selection{display:flex;gap:10px;margin:0 0 10px}.saved-contact-selection .btn{min-height:36px;padding:6px 10px;font-size:12px}.saved-contact-list{display:grid;gap:8px;margin-bottom:14px;max-height:min(340px,45vh);overflow:auto;scrollbar-gutter:stable;padding-right:6px}.saved-contact-list label{display:grid;grid-template-columns:20px minmax(0,1fr);gap:10px;align-items:start;padding:10px 0;border-bottom:1px solid var(--line)}.saved-contact-list input{width:17px;height:17px;accent-color:var(--accent);margin:2px 0}.saved-contact-list strong,.saved-contact-list span{display:block;font-size:13px;overflow-wrap:anywhere}.saved-contact-list small{color:var(--muted);font-size:11px}.roster-toolbar{flex-wrap:wrap}';
style.textContent+='\n@media(min-width:761px){.saved-contact-list label>div{display:grid;grid-template-columns:minmax(100px,1fr) minmax(180px,1.3fr) minmax(140px,1fr);gap:16px;align-items:baseline}.saved-contact-list label{align-items:center}}';
style.textContent+='\n.saved-contact-manual summary{cursor:pointer;font-size:13px;padding:10px 0;min-height:40px;box-sizing:border-box}.saved-contact-manual p{line-height:1.6}.saved-contact-manual summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}';
let contactPreview=null,contactLoading=false;
function contactDraft(){
 return JSON.stringify([...people.querySelectorAll('.person')].map(row=>{const f=fields(row);return [f.name.value.trim(),f.email.value.trim()];}));
}
function clearContactPreview(){contactPreview=null;contactPanel.replaceChildren();contactPanel.hidden=true;}
contactButton.addEventListener('click',async()=>{
 if(contactLoading)return;
 const submitted=contactDraft();
 const current=[...people.querySelectorAll('.person')].map(fields);
 const emptyNames=new Set(current.filter(f=>f.name.value.trim()&&!f.email.value.trim()).map(f=>f.name.value.trim()));
 const names=current.map(f=>f.name.value.trim()).filter(Boolean);
 if(!emptyNames.size)return;
 clearContactPreview();contactLoading=true;contactButton.disabled=true;contactButton.textContent='Finding contacts…';
 try{
  const result=await api('/api/contacts/preview',{names});
  for(const key of ['contacts','ambiguous_names','missing_names'])result[key]=result[key].filter(value=>emptyNames.has(key==='contacts'?value.name:value));
  const enteredEmails=new Set(current.map(f=>f.email.value.trim().toLocaleLowerCase()).filter(Boolean));
  result.ambiguous_names.push(...result.contacts.filter(person=>enteredEmails.has(person.email.toLocaleLowerCase())).map(person=>person.name));
  result.contacts=result.contacts.filter(person=>!enteredEmails.has(person.email.toLocaleLowerCase()));
  if(contactDraft()!==submitted){setStatus('Your collaborators changed while saved contacts were loading. Review contacts again for the current roster.');return;}
  contactPreview={submitted,contacts:result.contacts};
  const title=document.createElement('h3');title.textContent=result.contacts.length?'Review '+result.contacts.length+' saved '+(result.contacts.length===1?'contact':'contacts'):'No matching saved contacts';
  contactPanel.append(title);
  const largeReview=names.length>8;
  const list=document.createElement('div');list.className='saved-contact-list';list.tabIndex=0;list.setAttribute('role','group');list.setAttribute('aria-label','Saved contact choices');
  for(const [index,person]of result.contacts.entries()){
   const label=document.createElement('label'),box=document.createElement('input'),text=document.createElement('div');
   box.type='checkbox';box.checked=true;box.dataset.contactIndex=String(index);
   box.setAttribute('aria-label','Use saved contact for '+person.name);
   const name=document.createElement('strong'),email=document.createElement('span'),source=document.createElement('small');
   name.textContent=person.name;email.textContent=person.email;
   source.textContent='Saved in '+person.source_project+(person.source_period?' · '+person.source_period:'');
   text.append(name,email,source);label.append(box,text);list.append(label);
  }
  contactPanel.append(list);
  const unresolved=[...result.ambiguous_names,...result.missing_names];
  if(unresolved.length){
   const note=document.createElement('p');note.textContent=unresolved.join(', ')+'.';
   const manual=document.createElement('details'),summary=document.createElement('summary');
   summary.textContent=unresolved.length+' '+(unresolved.length===1?'contact':'contacts')+' to enter manually';
   manual.className='saved-contact-manual';manual.append(summary,note);list.prepend(manual);
  }
  const actions=document.createElement('div');actions.className='actions';
  if(result.contacts.length){
   const apply=document.createElement('button');apply.type='button';apply.className='btn primary';apply.id='useSavedContacts';apply.textContent='Use selected contacts';
   apply.addEventListener('click',()=>{
    const preview=contactPreview;
    if(!preview||contactDraft()!==preview.submitted){clearContactPreview();setStatus('Your collaborators changed. Review saved contacts again.');return;}
    const selected=[...contactPanel.querySelectorAll('input:checked')].map(box=>preview.contacts[Number(box.dataset.contactIndex)]);
    clearContactPreview();let filled=0;
    for(const row of people.querySelectorAll('.person')){
     const f=fields(row),match=selected.find(person=>person.name===f.name.value.trim());
     if(match&&!f.email.value.trim()){f.email.value=match.email;f.email.dispatchEvent(new Event('input',{bubbles:true}));filled++;}
    }
    setStatus(filled+' saved '+(filled===1?'contact added':'contacts added')+'. Review recipient emails, then update the statement.');
   });
   const selectionCount=()=>{const count=list.querySelectorAll('input:checked').length;apply.textContent='Use '+count+' '+(count===1?'contact':'contacts');apply.disabled=count===0;};
   list.addEventListener('change',selectionCount);selectionCount();
   if(result.contacts.length>2){
    const selectionTools=document.createElement('div');selectionTools.className='saved-contact-selection';
    for(const [id,label,checked]of [['selectAllSavedContacts','Select all',true],['clearSavedContacts','Clear selection',false]]){
     const button=document.createElement('button');button.type='button';button.className='btn small ghost';button.id=id;button.textContent=label;
     button.addEventListener('click',()=>{list.querySelectorAll('input').forEach(box=>box.checked=checked);selectionCount();});selectionTools.append(button);
    }
    list.before(selectionTools);
   }
   actions.append(apply);
  }
  const cancel=document.createElement('button');cancel.type='button';cancel.className='btn ghost';cancel.id='cancelSavedContacts';cancel.textContent='Cancel';cancel.addEventListener('click',clearContactPreview);
  actions.append(cancel);contactPanel.append(actions);contactPanel.hidden=false;
  if(largeReview){contactPanel.tabIndex=-1;contactPanel.focus({preventScroll:true});contactPanel.scrollIntoView({block:'center',behavior:'instant'});}
 }catch(error){if(contactDraft()===submitted)setStatus(error.message,true);}
 finally{contactLoading=false;contactButton.disabled=false;contactButton.textContent='Saved contacts';}
});

const empty = document.createElement('p');
empty.id = 'rosterEmpty'; empty.className = 'roster-empty'; empty.hidden = true;
empty.textContent = 'No collaborators match. Show everyone or change the search.';
people.after(empty);
function bps(value) {
 const text = value.trim();
 if (!/^(?:0|[1-9]\d{0,2})(?:\.\d{1,2})?$/.test(text)) return null;
 const [whole,fraction=''] = text.split('.');
 const n = Number(whole)*100 + Number(fraction.padEnd(2,'0'));
 return n > 0 && n <= 10000 ? n : null;
}
function percent(n) { return Math.floor(n/100)+'.'+String(n%100).padStart(2,'0')+'%'; }
function fields(row) { return Object.fromEntries([...row.querySelectorAll('[data-role]')].map(input => [input.dataset.role,input])); }
// Suggestions may replace shares and quotes, but never invent recipient contacts.
window.preserveRosterContacts = suggestions => {
 const existing = new Map(), incoming = new Map(), rowIds = new Map();
 for(const row of people.querySelectorAll('.person')){
  const f=fields(row),name=f.name.value.trim(),draft_row_id=row.dataset.draftRowId;
  if(draft_row_id)rowIds.set(draft_row_id,(rowIds.get(draft_row_id)||0)+1);
  if(!name)continue;
  const key=name.toLocaleLowerCase(),entry=existing.get(key);
  existing.set(key,{count:(entry?.count||0)+1,name,email:f.email.value.trim(),draft_row_id});
 }
 for(const person of suggestions){
  const name=typeof person.name==='string'?person.name.trim():'';
  const key=name.toLocaleLowerCase();incoming.set(key,(incoming.get(key)||0)+1);
 }
 return suggestions.map(person=>{
  const name=typeof person.name==='string'?person.name.trim():'',key=name.toLocaleLowerCase(),entry=existing.get(key);
  const matched=name&&entry?.count===1&&entry.name===name&&incoming.get(key)===1;
  return {...person,email:matched?entry.email:'',draft_row_id:matched&&entry.draft_row_id&&rowIds.get(entry.draft_row_id)===1?entry.draft_row_id:undefined};
 });
};
function enhance(row) {
 if(row.dataset.rosterReady) return;
 row.dataset.rosterReady='true';
 const f = fields(row);
 for(const role of ['name','email','share']) f[role].closest('.field').classList.add('roster-'+role);
 f.email.type='email';f.email.autocomplete='off';f.share.inputMode='decimal';
 const details=document.createElement('details');details.className='roster-source';
 const summary=document.createElement('summary');details.append(summary);
 const quote=f.evidence.closest('.field');
 const hint=document.createElement('p');hint.className='hint';hint.textContent='The quote must be exact. Calculate to check the named source and supported net basis.';
 const original=document.createElement('button');original.type='button';original.className='btn small ghost roster-original';original.textContent='View in agreement';
 original.addEventListener('click',()=>reviewAgreementQuote(f.evidence.value.trim(),original,'Return to '+(f.name.value.trim()||'creator')+' quote'));
 details.append(quote,hint,original);row.append(details);
 details.open=!f.evidence.value.trim();
}
function refresh() {
 const rows=[...people.querySelectorAll('.person')];
 const emptyRoster=rows.every(row=>Object.values(fields(row)).every(input=>!input.value.trim()));
 tools.querySelector('.roster-toolbar').hidden=emptyRoster;
 if(contactPreview&&contactDraft()!==contactPreview.submitted)clearContactPreview();
 contactButton.hidden=!rows.some(row=>{const f=fields(row);return f.name.value.trim()&&!f.email.value.trim();});
 rows.forEach(enhance);
 const query=$('rosterSearch').value.trim().toLocaleLowerCase(), onlyIssues=$('rosterAttention').checked;
 $('rosterClear').hidden=!query&&!onlyIssues;
 const agreement=$('agreement').value;
 const names=new Map(),emails=new Map();
 for(const row of rows){const f=fields(row);for(const [map,value]of[[names,f.name.value.trim().toLocaleLowerCase()],[emails,f.email.value.trim().toLocaleLowerCase()]]) if(value)map.set(value,(map.get(value)||0)+1);}
 const equalCount=rows.filter(row=>fields(row).share.value.trim().toLowerCase()==='equal').length;
 const allEqual=rows.length>0&&equalCount===rows.length;
 let assigned=0,invalid=0,incomplete=0,visible=0;
 for(const row of rows){
  const f=fields(row),name=f.name.value.trim(),email=f.email.value.trim(),quote=f.evidence.value.trim(),share=bps(f.share.value);
  const issues=[];
  if(!name)issues.push('Name missing');else if(names.get(name.toLocaleLowerCase())>1)issues.push('Name used twice');
  if(!email)issues.push('Payout email not added');else if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))issues.push('Check email');else if(emails.get(email.toLocaleLowerCase())>1)issues.push('Email used twice');
  if(allEqual){}else if(share===null){invalid++;issues.push(equalCount?'Use equal for every creator':'Enter 0.01–100% or equal');}else assigned+=share;
  if(!quote)issues.push('Quote missing');else if(!agreement.includes(quote))issues.push('Quote not in agreement');
  const source=row.querySelector('.roster-source summary');
  source.textContent=!emptyRoster&&issues.length?issues.join(' · '):'Agreement quote';
  source.dataset.issue=String(!emptyRoster&&issues.length>0);
  row.dataset.rosterIssues=String(issues.length>0);
  if(issues.length)incomplete++;
  const remove=row.querySelector('.person-header button');remove.setAttribute('aria-label','Remove '+(name||'unnamed collaborator'));
  for(const role of ['name','email','share','evidence'])f[role].setAttribute('aria-label',(name||'Collaborator')+' — '+({name:'name',email:'Recipient email',share:'share percent',evidence:'exact agreement quote'}[role]));
  const match=(!query||(name+' '+email).toLocaleLowerCase().includes(query))&&(!onlyIssues||issues.length>0)||row.contains(document.activeElement);
  row.hidden=!match;if(match)visible++;
 }
 if(allEqual)assigned=10000;
 $('rosterAssigned').textContent=emptyRoster?'No shares entered':allEqual?'Equal shares · 1/'+rows.length+' each':percent(assigned)+' entered';
 $('rosterBalance').dataset.state=emptyRoster?'empty':invalid?'invalid':assigned>10000?'over':assigned===10000?'complete':'under';
 $('rosterBalanceHint').textContent=emptyRoster?'':invalid?invalid+' '+(invalid===1?'share needs':'shares need')+' an exact percentage.':assigned===10000?'':assigned<10000?percent(10000-assigned)+' left to assign.':percent(assigned-10000)+' over 100.00%. Review the entered shares.';
 $('rosterCount').textContent=emptyRoster?'':(visible===rows.length?rows.length+' '+(rows.length===1?'collaborator':'collaborators'):'Showing '+visible+' of '+rows.length)+(incomplete?' · '+incomplete+' to finish':'');
 empty.hidden=visible>0||rows.length===0;
}
let queued=false;
function schedule(){if(queued)return;queued=true;queueMicrotask(()=>{queued=false;refresh();});}
people.addEventListener('input',schedule);
people.addEventListener('focusout',schedule);
$('agreement').addEventListener('input',schedule);
$('rosterSearch').addEventListener('input',refresh);
$('rosterAttention').addEventListener('change',refresh);
function showEveryone(){ $('rosterSearch').value='';$('rosterAttention').checked=false;refresh(); }
$('rosterClear').addEventListener('click',()=>{showEveryone();$('rosterSearch').focus();});
window.resetRosterFilters=showEveryone;
window.reviewSuggestedRoster=()=>{
 showEveryone();$('rosterSearch').focus({preventScroll:true});tools.scrollIntoView({block:'start',behavior:'instant'});
};
$('addPerson').addEventListener('click',()=>{$('rosterSearch').value='';$('rosterAttention').checked=false;refresh();const last=people.lastElementChild;if(last)fields(last).name.focus();});
window.addEventListener('royalty-draft-saved',schedule);
new MutationObserver(schedule).observe(people,{childList:true});
refresh();
})();
