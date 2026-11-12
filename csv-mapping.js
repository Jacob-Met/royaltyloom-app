/* Deliberate mapping of the current source; adoption always needs a second action. */
(()=>{
const root=document.getElementById('csvMapping'), source=document.getElementById('sales');
const status=root.querySelector('[role=status]'), fields=root.querySelector('.mapping-fields'), types=root.querySelector('.mapping-types');
const preview=root.querySelector('.mapping-preview'), adopt=root.querySelector('.mapping-adopt');
let snapshot='',candidate=null,columns={},restoringMapping=false,sourceHeaders=[],candidateFormat=null,formatSnapshot='';
let previewVersion=0,readVersion=0,typeVersion=0,mappingRestoreVersion=0,restoreFailed=false;
function cancelMappingRestore(){mappingRestoreVersion++;restoringMapping=false;restoreFailed=false;}
const MAPPING_DRAFT_KEY='royalty-loom-mapping-draft-v1';
function forgetMapping(){draftMapping=null;try{localStorage.removeItem(MAPPING_DRAFT_KEY);}catch{}}
function saveMapping(){
 if(source.value!==snapshot)return;
 const draft={version:1,source:snapshot,format:format.value,amount_mode:amountMode.value,headers:[...sourceHeaders],columns:Object.fromEntries(Object.entries(columns).map(([name,select])=>[name,select.value])),types:restoringMapping&&!types.querySelector('select')?{...(draftMapping?.types||{})}:Object.fromEntries([...types.querySelectorAll('select')].map(s=>[s.dataset.sourceType,s.value]))};
 draftMapping=draft;
 saveDraft();
 try{localStorage.setItem(MAPPING_DRAFT_KEY,JSON.stringify(draft));}catch{say('Mapping choices could not be saved in this browser. Keep this tab open until you finish.');}
}
const format=root.querySelector('.mapping-format');
format.addEventListener('change',()=>{cancelMappingRestore();sourceHeaders=[];renderSavedFormats();readVersion++;typeVersion++;root.querySelector('.mapping-gumroad-help').hidden=format.value!=='gumroad';reset();choices.hidden=true;fields.replaceChildren();types.replaceChildren();root.querySelector('.mapping-build').hidden=true;forgetMapping();saveDraft();});
const say=message=>status.textContent=message;
const reset=()=>{previewVersion++;candidate=null;candidateFormat=null;formatSnapshot='';saveFormatPanel.hidden=true;document.getElementById('sourceLedger').hidden=false;adopt.hidden=true;preview.replaceChildren();const shared=document.getElementById('status');if(shared?.textContent.startsWith('Mapped preview ready.'))shared.hidden=true;};
const request=async obj=>{const response=await fetch('/api/csv-map',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)});const data=await response.json();if(!response.ok)throw Error(data.error);return data;};
const choose=(label,choices,initial)=>{const wrap=document.createElement('label');wrap.textContent=label;const select=document.createElement('select');for(const [value,text] of choices){const option=document.createElement('option');option.value=value;option.textContent=text;select.append(option);}select.value=initial;wrap.append(select);return {wrap,select};};
// Saved formats contain headings and explicitly chosen meanings, never source rows.
const FORMATS_KEY='royalty-loom-csv-formats-v1';
// Keep raw source editing separate from the file-mapping workflow.
document.getElementById('csvEditor').after(root);
const choices=document.createElement('details');choices.className='mapping-choices';choices.open=true;choices.hidden=true;
const choicesTitle=document.createElement('summary');choicesTitle.textContent='Columns & transaction types';choices.append(choicesTitle);fields.before(choices);const amountChoice=choose('Amount signs',[['positive','All amounts are positive'],['signed','Sales +; refunds & fees −']],'positive');
const amountMode=amountChoice.select;amountMode.id='mappingAmountMode';
amountMode.addEventListener('change',()=>{cancelMappingRestore();reset();saveMapping();});
choices.append(fields,amountChoice.wrap,types);
const savedFormats=document.createElement('div');savedFormats.className='mapping-saved-formats';savedFormats.hidden=true;
const savedLabel=document.createElement('label');savedLabel.textContent='Saved format';
const savedSelect=document.createElement('select');savedSelect.id='savedCsvFormat';savedLabel.append(savedSelect);
const applyFormat=document.createElement('button');applyFormat.id='applyCsvFormat';applyFormat.type='button';applyFormat.className='btn small';applyFormat.textContent='Use format';
const removeFormat=document.createElement('button');removeFormat.id='removeCsvFormat';removeFormat.type='button';removeFormat.className='btn small ghost';removeFormat.textContent='Remove';
savedFormats.append(savedLabel,applyFormat,removeFormat);root.querySelector('.mapping-start').after(savedFormats);
const saveFormatPanel=document.createElement('details');saveFormatPanel.className='mapping-format-save';saveFormatPanel.hidden=true;
const saveLabel=document.createElement('label');saveLabel.textContent='Format name';
const formatName=document.createElement('input');formatName.id='csvFormatName';formatName.type='text';formatName.maxLength=60;formatName.placeholder='e.g. Studio sales';saveLabel.append(formatName);
const saveFormatButton=document.createElement('button');saveFormatButton.id='saveCsvFormat';saveFormatButton.type='button';saveFormatButton.className='btn small ghost';saveFormatButton.textContent='Save format';
const saveFormatTitle=document.createElement('summary');saveFormatTitle.textContent='Save this format';saveFormatPanel.append(saveFormatTitle,saveLabel,saveFormatButton);adopt.after(saveFormatPanel);
const formatStyle=document.createElement('style');
formatStyle.textContent='.mapping-choices{margin:16px 0}.mapping-choices>summary,.mapping-format-save>summary{cursor:pointer;font-size:13px}.mapping-format-save{display:block!important}.mapping-format-save[hidden]{display:none!important}.mapping-format-save>summary{margin-bottom:10px}.mapping-format-save:not([open])>summary{margin-bottom:0}.mapping-format-save input{max-width:480px}.mapping-format-save button{margin-top:10px}.mapping-totals{display:flex;flex-wrap:wrap;align-items:end;gap:12px 28px;margin:16px 0}.mapping-totals .mapping-net{margin-left:auto;font-size:26px;color:var(--ink);font-weight:650}.mapping-totals span{font-size:13px;color:var(--muted)}.mapping-totals b{display:block;font-size:16px;color:var(--ink);margin-top:5px;font-variant-numeric:tabular-nums}.mapping-count{font-size:12px!important;color:var(--muted)}.mapping-preview:focus{outline:none}@media(max-width:760px){.mapping-totals{gap:12px 20px}.mapping-totals .mapping-net{font-size:22px}.mapping-totals span{font-size:12px}.mapping-totals b{font-size:14px}}.mapping-saved-formats,.mapping-format-save{display:flex;align-items:end;gap:10px;margin:16px 0;flex-wrap:wrap}.mapping-saved-formats[hidden],.mapping-format-save[hidden]{display:none}.mapping-saved-formats label,.mapping-format-save label{flex:1;min-width:180px;font-size:13px}.mapping-saved-formats select,.mapping-format-save input{display:block;margin-top:6px;width:100%}.mapping-ledger{list-style:none;margin:14px 0;padding:0;max-height:320px;overflow:auto;border-top:1px solid var(--line);border-bottom:1px solid var(--line);scrollbar-gutter:stable}.mapping-ledger:focus-visible{outline:2px solid var(--accent);outline-offset:3px}.mapping-preview>p{font-size:14px;line-height:1.6}.mapping-format-save .btn{white-space:nowrap}@media(max-width:760px){.mapping-saved-formats label,.mapping-format-save label{flex-basis:100%;min-width:0}.mapping-ledger{max-height:280px}}';
document.head.append(formatStyle);
function readFormats(){
 try{
  const data=JSON.parse(localStorage.getItem(FORMATS_KEY)||'null');
  if(data?.version!==1||!Array.isArray(data.formats))return [];
  return data.formats.filter(item=>item&&typeof item.id==='string'&&typeof item.name==='string'&&item.name.trim()&&item.name.length<=60&&Array.isArray(item.headers)&&item.headers.length&&item.headers.every(h=>typeof h==='string')&&new Set(item.headers).size===item.headers.length&&item.columns&&['id','type','amount'].every(k=>typeof item.columns[k]==='string'&&item.headers.includes(item.columns[k]))&&['description','currency','date'].every(k=>item.columns[k]===null||typeof item.columns[k]==='string'&&item.headers.includes(item.columns[k]))&&(item.amount_mode===undefined||['positive','signed'].includes(item.amount_mode))&&item.types&&typeof item.types==='object'&&!Array.isArray(item.types)&&Object.values(item.types).every(v=>['sale','refund','fee'].includes(v))).slice(0,30);
 }catch{return [];}
}
function compatible(item){
 return sourceHeaders.length===item.headers.length&&sourceHeaders.every(header=>item.headers.includes(header));
}
function renderSavedFormats(selected=savedSelect.value){
 const items=readFormats();
 savedFormats.hidden=format.value!=='custom'||!sourceHeaders.length||!items.length;
 savedSelect.replaceChildren(new Option('Choose a saved format',''));
 for(const item of items)savedSelect.add(new Option(item.name+(compatible(item)?'':' — different columns'),item.id));
 if(items.some(item=>item.id===selected))savedSelect.value=selected;
 else{const matching=items.filter(compatible);if(matching.length===1)savedSelect.value=matching[0].id;}
 const item=items.find(item=>item.id===savedSelect.value);
 applyFormat.disabled=!item||!compatible(item);removeFormat.disabled=!item;
}
savedSelect.addEventListener('change',()=>renderSavedFormats());
window.addEventListener('storage',event=>{if(event.key===FORMATS_KEY)renderSavedFormats();});
saveFormatButton.addEventListener('click',()=>{
 if(!candidateFormat||source.value!==formatSnapshot||format.value!=='custom')return;
 const name=formatName.value.trim();
 if(!name){formatName.focus();say('Name this format to save it.');return;}
 const items=readFormats(),existing=items.find(item=>item.name.toLocaleLowerCase()===name.toLocaleLowerCase());
 if(existing&&!confirm('Replace the saved format “'+existing.name+'”?'))return;
 if(!existing&&items.length>=30){say('Remove an old saved format before adding another.');return;}
 const item={...candidateFormat,id:existing?.id||crypto.randomUUID(),name};
 const next=items.filter(entry=>entry.id!==item.id);next.push(item);
 try{localStorage.setItem(FORMATS_KEY,JSON.stringify({version:1,formats:next}));}
 catch{say('This browser could not save the format. Your preview is still ready.');return;}
 renderSavedFormats(item.id);say('Saved “'+name+'” for the next export.');saveFormatButton.textContent='Saved';
});
formatName.addEventListener('input',()=>{saveFormatButton.textContent='Save format';});
removeFormat.addEventListener('click',()=>{
 const items=readFormats(),item=items.find(entry=>entry.id===savedSelect.value);if(!item)return;
 try{localStorage.setItem(FORMATS_KEY,JSON.stringify({version:1,formats:items.filter(entry=>entry.id!==item.id)}));}
 catch{say('This browser could not remove the format.');return;}
 renderSavedFormats();say('Removed “'+item.name+'”. Current column choices are unchanged.');
});
applyFormat.addEventListener('click',async()=>{
 cancelMappingRestore();
 const item=readFormats().find(entry=>entry.id===savedSelect.value);
 if(!item||!compatible(item)||source.value!==snapshot||format.value!=='custom')return;
 const currentSource=snapshot,currentHeaders=JSON.stringify(sourceHeaders);
 amountMode.value=item.amount_mode||'positive';
 applyFormat.disabled=true;
 for(const [name,select] of Object.entries(columns)){
  const heading=item.columns[name];select.value=heading===null?'':String(sourceHeaders.indexOf(heading));
 }
 const pending=showTypes(),version=previewVersion;
 try{
  await pending;
  if(version!==previewVersion||source.value!==currentSource||snapshot!==currentSource||JSON.stringify(sourceHeaders)!==currentHeaders||format.value!=='custom')return;
  let unknown=0;
  for(const select of types.querySelectorAll('select')){
   const meaning=Object.hasOwn(item.types,select.dataset.sourceType)?item.types[select.dataset.sourceType]:'';
   select.value=meaning;if(!meaning)unknown++;
  }
  formatName.value=item.name;saveFormatButton.textContent='Save format';saveMapping();
  say('“'+item.name+'” applied. '+(unknown?'Classify '+unknown+' new transaction '+(unknown===1?'type':'types')+'. ':'')+(columns.currency.value===''?'Choose the currency for this file. ':'')+'Preview the new rows.');
  if(!unknown&&columns.currency.value!==''){choices.open=false;root.querySelector('.mapping-build').click();}else choices.open=true;
 }finally{renderSavedFormats(item.id);}
});

async function showTypes(savedTypes=null){
 const version=++typeVersion,currentFormat=format.value;
 reset();types.replaceChildren();
 if(columns.type.value==='')return;
 try{
 const currentSource=snapshot,typeIndex=columns.type.value;
 const data=await request({source:currentSource,type_column:Number(typeIndex)});
 if(version!==typeVersion||format.value!==currentFormat||source.value!==currentSource||snapshot!==currentSource||columns.type?.value!==typeIndex)return;
 const heading=document.createElement('p');heading.textContent='Classify every source type. Refunds and fees are deducted once using the selected amount signs.';types.append(heading);
 for(const value of data.type_values){
 const control=choose(value||'(blank type)',[['','Choose meaning'],['sale','Sale: adds revenue'],['refund','Refund: deduction'],['fee','Fee: deduction']],savedTypes&&['','sale','refund','fee'].includes(savedTypes[value])?savedTypes[value]:['sale','refund','fee'].includes(value)?value:'');
 control.select.dataset.sourceType=value;control.select.addEventListener('change',()=>{cancelMappingRestore();reset();saveMapping();});types.append(control.wrap);
 }
 }catch(error){if(version===typeVersion&&format.value===currentFormat){root.querySelector('.mapping-build').hidden=true;say(error.message);if(savedTypes)throw error;}}
}
async function readColumns(savedDraft=null){
 const version=++readVersion,currentFormat=format.value;typeVersion++;
 reset();choices.open=true;choices.hidden=true;fields.replaceChildren();types.replaceChildren();snapshot=source.value;sourceHeaders=[];renderSavedFormats();
 try{
 const currentSource=snapshot;
 const data=await request({source:currentSource});
 if(version!==readVersion||format.value!==currentFormat||source.value!==currentSource||snapshot!==currentSource)return;
 sourceHeaders=data.headers;choices.hidden=currentFormat!=='custom';renderSavedFormats();
 if(format.value==='gumroad'){
 root.querySelector('.mapping-build').hidden=false;
 say('Read '+data.row_count+' rows. Preview will expand each completed digital sale and its fee, and require Sale Price − Fees = Net Total. Refunds, disputes, tax, shipping, affiliate and Connect fees need separate reconciliation.');saveMapping();return;
 }
 amountMode.value=['positive','signed'].includes(savedDraft?.amount_mode)?savedDraft.amount_mode:'positive';
 columns={};
 for(const name of ['id','type','amount','description','currency','date']){
 const optional=['description','currency','date'].includes(name);
 const options=[['',name==='currency'?'Choose currency column or confirm USD':(optional?'No '+name:'Choose column')],...(name==='currency'?[['usd','I confirm every amount is USD']]:[]),...data.headers.map((header,index)=>[String(index),header])];
 const found=data.headers.indexOf(name);
 const control=choose(name==='id'?'Transaction ID':name==='date'?'Date (YYYY-MM-DD)':name[0].toUpperCase()+name.slice(1),options,found<0?'':String(found));
 if(typeof savedDraft?.columns?.[name]==='string'&&options.some(([value])=>value===savedDraft.columns[name]))control.select.value=savedDraft.columns[name];
 columns[name]=control.select;control.select.dataset.mapField=name;
 control.select.addEventListener('change',async()=>{if(name==='type')cancelMappingRestore();reset();if(name==='type'){const pending=showTypes();saveMapping();await pending;}saveMapping();});
 fields.append(control.wrap);
 }
 root.querySelector('.mapping-build').hidden=false;
 say(data.row_count+' source rows. Match columns and every transaction type, then preview. Unmapped columns are omitted from the normalized source.');
 await showTypes(savedDraft?.types);saveMapping();
 }catch(error){if(version===readVersion&&format.value===currentFormat){say(error.message);if(savedDraft)throw error;}}
}
root.querySelector('.mapping-start').addEventListener('click',()=>{const retry=restoreFailed?currentDraftMapping():null;restoreFailed=false;if(retry){restoreMapping(retry);return;}cancelMappingRestore();readColumns();});
root.querySelector('.mapping-build').addEventListener('click',async()=>{
 reset();
 const version=previewVersion,currentSource=snapshot,currentFormat=format.value;
 try{
 if(source.value!==snapshot)throw Error('Source text changed. Read its columns again before mapping.');
 const mapping=Object.fromEntries(Object.entries(columns).map(([name,select])=>[name,select.value===''||select.value==='usd'?null:Number(select.value)]));
 const typeMap=Object.fromEntries([...types.querySelectorAll('select')].map(select=>[select.dataset.sourceType,select.value]));
 const data=await request({source:currentSource,action:'normalize',format:currentFormat,mapping,types:typeMap,amount_mode:amountMode.value,currency_confirmed:columns.currency?.value==='usd'});
 if(version!==previewVersion||source.value!==currentSource||snapshot!==currentSource||format.value!==currentFormat)return;
 candidate=data.normalized;
 if(currentFormat==='custom'){
  candidateFormat={amount_mode:amountMode.value,headers:[...sourceHeaders],columns:Object.fromEntries(Object.entries(columns).map(([name,select])=>[name,select.value===''||select.value==='usd'?null:sourceHeaders[Number(select.value)]])),types:{...typeMap}};
  formatSnapshot=currentSource;saveFormatPanel.hidden=false;saveFormatPanel.open=!readFormats().length;saveFormatButton.textContent='Save format';
 }
 if(typeof setStatus==='function')setStatus('Mapped preview ready. Review its signed entries, then use mapped rows and calculate a fresh statement.');
 const summary=document.createElement('p');const usd=n=>(n<0?'−':'')+'$'+(Math.abs(n)/100).toFixed(2);
 summary.className='mapping-count';summary.textContent=data.preview_rows.length+' transactions · '+data.row_count+' source rows';
 const totals=document.createElement('div');totals.className='mapping-totals';
 for(const [label,value] of [['Sales',data.totals.sale],['Refunds',data.totals.refund],['Fees',data.totals.fee],['Net',data.net_cents]]){
  const item=document.createElement('span');item.append(label+' ');
  const amount=document.createElement('b');amount.textContent=usd(value);if(label==='Net')amount.className='mapping-net';item.append(amount);totals.append(item);
 }
 document.getElementById('sourceLedger').hidden=true;
 const ledger=document.createElement('ol');ledger.className='mapping-ledger';ledger.setAttribute('aria-label','Mapped transaction preview');ledger.tabIndex=0;
 for(const entry of data.preview_rows){
  const row=document.createElement('li');row.className='audit-row'+(entry.type==='sale'?'':' deduction');
  const details=document.createElement('div');
  const id=document.createElement('span');id.className='audit-id';id.textContent=entry.id;
  const kind=document.createElement('span');kind.className='audit-kind';kind.textContent=entry.type+(entry.date?' · '+entry.date:'');
  const description=document.createElement('div');description.className='audit-description';description.textContent=entry.description||'No description supplied';
  details.append(id,kind,description);
  const amount=document.createElement('strong');amount.className='audit-value';amount.textContent=(entry.type==='sale'?'+':'−')+'$'+Math.floor(entry.cents/100)+'.'+String(entry.cents%100).padStart(2,'0');
  row.append(details,amount);ledger.append(row);
 }
 const csv=document.createElement('details');csv.className='mapping-csv';const heading=document.createElement('summary');heading.textContent='View normalized CSV';csv.append(heading);
 const text=document.createElement('textarea');text.readOnly=true;text.rows=8;text.value=candidate;text.setAttribute('aria-label','Normalized CSV preview');
 csv.append(text);preview.append(summary,totals);if(data.source_note){const note=document.createElement('p');note.textContent=data.source_note;preview.append(note);}preview.append(ledger,csv);adopt.hidden=false;preview.tabIndex=-1;preview.focus({preventScroll:true});preview.scrollIntoView({behavior:'smooth',block:'start'});say('Review the transactions below.');
 }catch(error){if(version===previewVersion&&source.value===currentSource)say(error.message);}
});
adopt.addEventListener('click',()=>{
 if(!candidate||source.value!==snapshot){reset();say('Source changed. Read columns and preview again.');return;}
 const reviewedFormat=candidateFormat;
 restoreSourceProvenance({version:1,format:format.value,original_csv:snapshot,mapped_csv:candidate});
 source.value=candidate;source.dispatchEvent(new Event('input',{bubbles:true}));reset();renderProvenance();
 snapshot=source.value;
 if(reviewedFormat){candidateFormat=reviewedFormat;formatSnapshot=snapshot;saveFormatPanel.hidden=false;saveFormatPanel.open=!readFormats().length;}
 document.getElementById('salesImportState').textContent='Mapped rows ready. Update the statement to use these transactions.';
 say(reviewedFormat?'Mapped rows ready. Save this format for another export.':'Mapped rows ready.');
});
function sourceChanged(force=false){
 if(force!==true&&source.value===snapshot)return;
 mappingRestoreVersion++;restoringMapping=false;restoreFailed=false;
 readVersion++;typeVersion++;
 reset();choices.hidden=true;fields.replaceChildren();types.replaceChildren();columns={};sourceHeaders=[];renderSavedFormats();
 root.querySelector('.mapping-build').hidden=true;forgetMapping();
 say('Source changed. Read its columns to map this file. Earlier mapping choices were cleared.');
}
source.addEventListener('input',sourceChanged);
window.addEventListener('royalty-mapping-restored',()=>{const desired=currentDraftMapping();sourceChanged(true);if(desired){draftMapping=desired;restoreMapping(desired);}});
window.addEventListener('royalty-draft-saved',sourceChanged);
document.getElementById('clearDraft').addEventListener('click',()=>{if(!source.value){forgetMapping();sourceChanged();}});
async function restoreMapping(draft=currentDraftMapping()){
 const version=++mappingRestoreVersion;
 if(!draft||draft.version!==1||draft.source!==source.value||!source.value||!['custom','gumroad'].includes(draft.format)){forgetMapping();return;}
 restoringMapping=true;
 try{
  format.value=draft.format;root.querySelector('.mapping-gumroad-help').hidden=format.value!=='gumroad';
  await readColumns(draft);
  if(version!==mappingRestoreVersion||source.value!==draft.source)return;
  reset();root.open=true;restoreFailed=false;
  say('Unfinished mapping restored for this exact source. Check the choices, then create a fresh preview before adopting any rows.');
 }catch(error){
  if(version===mappingRestoreVersion&&source.value===draft.source){
   restoreFailed=true;root.open=true;root.querySelector('.mapping-build').hidden=true;
   say('Mapping could not be restored. Read columns to retry saved choices. '+error.message);
  }
 }
 finally{if(version===mappingRestoreVersion)restoringMapping=false;}
}

const archive=document.createElement('details');archive.id='originalMappedExport';archive.className='statement-history';archive.hidden=true;
const title=document.createElement('summary');title.textContent='Original mapped export';
const archiveNote=document.createElement('p');archiveNote.className='hint';archiveNote.id='originalMappedExportState';
const privacy=document.createElement('p');privacy.className='hint';privacy.textContent='Kept locally with this draft and saved statements. Original columns may contain customer details. They are excluded from review JSON, printable statements and creator copies.';
const downloads=document.createElement('div');downloads.className='actions';
function exportFilename(kind){
 const clean=value=>String(value||'').normalize('NFKC').replace(/[^\p{L}\p{N}._-]+/gu,'-').replace(/^[._-]+|[._-]+$/g,'').slice(0,70);
 const project=clean(document.getElementById('project').value)||'royalty';
 const period=clean(document.getElementById('statementPeriod')?.value)||clean([document.getElementById('periodStart')?.value,document.getElementById('periodEnd')?.value].filter(Boolean).join('-to-'));
 return [project,period,kind].filter(Boolean).join('-')+'.csv';
}
for(const [label,key,kind] of [['Download original export','original_csv','original-source'],['Download mapped snapshot','mapped_csv','mapped-snapshot']]){
 const button=document.createElement('button');button.type='button';button.className='btn small ghost';button.textContent=label;button.dataset.provenanceDownload=key;
 button.addEventListener('click',()=>{if(!sourceProvenance)return;const url=URL.createObjectURL(new Blob([sourceProvenance[key]],{type:'text/csv;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=exportFilename(kind);link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
 downloads.append(button);
}
const forget=document.createElement('button');forget.type='button';forget.className='btn small ghost';forget.textContent='Forget original in this draft';forget.id='forgetOriginalExport';
forget.addEventListener('click',()=>{if(!confirm('Remove the original export from this draft? Previously saved statements keep their own copy.'))return;restoreSourceProvenance(null);invalidate();});
downloads.append(forget);archive.append(title,archiveNote,privacy,downloads);root.after(archive);
function renderProvenance(){
 archive.hidden=!sourceProvenance;if(!sourceProvenance)return;
 archiveNote.textContent=(sourceProvenance.format==='gumroad'?'Gumroad export':'Custom export')+' retained. '+(source.value===sourceProvenance.mapped_csv?'Current transaction text matches the adopted mapped snapshot.':'Current transaction text differs from the mapped snapshot. Review your edits against the original export.')+' Calculations use the editable transaction text, never this retained copy.';
}
window.addEventListener('royalty-provenance-changed',renderProvenance);
window.addEventListener('royalty-draft-saved',renderProvenance);
source.addEventListener('input',renderProvenance);
renderProvenance();


const importNext=document.createElement('div');importNext.id='sourceMappingNext';importNext.className='actions';importNext.hidden=true;
const importAction=document.createElement('button');importAction.id='sourceMappingAction';importAction.type='button';importAction.className='btn';importAction.setAttribute('aria-controls','csvMapping');
importNext.append(importAction);document.getElementById('salesImportState').after(importNext);
let suggestedSource='',suggestedFormat='custom',suggestionEpoch=0,suggestionInput=null;
function resetImportSuggestion(){
 if(source.value===suggestionInput)return;
 suggestionInput=source.value;suggestionEpoch++;suggestedSource=source.value;suggestedFormat='custom';
 importAction.textContent='Map this CSV';importNext.hidden=!source.value.trim();
}
source.addEventListener('input',resetImportSuggestion);
window.addEventListener('royalty-draft-saved',resetImportSuggestion);
resetImportSuggestion();
window.addEventListener('royalty-source-invalid',async event=>{
 const next=event.detail?.source;if(!next||next!==source.value)return;
 const version=++suggestionEpoch;
 try{
  const data=await request({source:next});
  if(version!==suggestionEpoch||source.value!==next)return;
  if(['id','type','amount'].every(name=>data.headers.includes(name)))return;
  const gumroad=['Purchase ID','Sale Price ($)','Fees ($)','Net Total ($)'].every(name=>data.headers.includes(name));
  suggestedSource=next;suggestedFormat=gumroad?'gumroad':'custom';
  importAction.textContent=gumroad?'Preview Gumroad import':'Map this CSV';importNext.hidden=false;
  document.getElementById('salesImportState').textContent=gumroad?'Gumroad export detected. Preview its sales and fees.':'Match this file’s columns before updating the statement.';
  const feedback=document.getElementById('sourcePreviewStatus');
  feedback.className='smallprint';feedback.hidden=false;
  feedback.textContent=gumroad?'Preview the Gumroad sales and fees before using them.':'Match the columns and preview the mapped transactions before using them.';
  document.getElementById('sourceLedger').dataset.sourceState='mapping';
 }catch{ /* Keep the original CSV error when the source itself cannot be read. */ }
});
importAction.addEventListener('click',async()=>{
 const next=suggestedSource,chosenFormat=suggestedFormat;if(!next||source.value!==next)return;
 importAction.disabled=true;
 try{
  format.value=chosenFormat;format.dispatchEvent(new Event('change',{bubbles:true}));
  for(let parent=root;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;
  await readColumns();if(source.value!==next)return;
  const build=root.querySelector('.mapping-build');
  if(chosenFormat==='gumroad'&&!build.hidden)build.click();
  else {root.scrollIntoView({block:'start',behavior:'instant'});format.focus({preventScroll:true});}
 }finally{importAction.disabled=false;}
});

restoreMapping();
})();

// Keep Sales useful before creators and their agreement are ready to calculate.
(()=>{
const source=document.getElementById('sales'),ledger=document.getElementById('sourceLedger');
if(!source||!ledger||!window.renderTransactionLedger)return;
const feedback=document.createElement('p');feedback.id='sourcePreviewStatus';feedback.className='smallprint';feedback.setAttribute('role','status');feedback.hidden=true;
ledger.querySelector('.audit-head').after(feedback);
let raw=null,cached=null,controller=null,timer=null,epoch=0,queued=false;
const dollars=value=>typeof displayMoney==='function'?displayMoney(value):'$'+value;
function paint(data){
 window.renderTransactionLedger(data?data.transactions:[]);
 document.getElementById('net2').textContent=data?dollars(data.net):'$—';
 document.getElementById('auditNet').textContent=data?dollars(data.net):'$—';
}
function sync(){
 const next=source.value;
 if(next===raw){if(cached)paint(cached);return;}
 raw=next;cached=null;const version=++epoch;
 clearTimeout(timer);controller?.abort();controller=null;
 paint(null);feedback.className='smallprint';
 if(!raw.trim()){ledger.dataset.sourceState='empty';feedback.hidden=true;return;}
 ledger.dataset.sourceState='loading';feedback.hidden=false;feedback.textContent='Reading transactions…';
 timer=setTimeout(async()=>{
  controller=new AbortController();const signal=controller.signal;
  try{
   const response=await fetch('/api/source-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sales_csv:next}),signal});
   const result=await response.json();
   if(version!==epoch||source.value!==next)return;
   if(!response.ok)throw Error(result.error||'Could not read these transactions.');
   cached=result;paint(result);ledger.dataset.sourceState='ready';feedback.hidden=true;feedback.textContent='';
  }catch(error){
   if(version!==epoch||source.value!==next||error.name==='AbortError')return;
   paint(null);ledger.dataset.sourceState='error';feedback.hidden=false;feedback.className='status error';feedback.textContent=error.message;
   window.dispatchEvent(new CustomEvent('royalty-source-invalid',{detail:{source:next}}));
  }
 },180);
}
function schedule(){if(queued)return;queued=true;queueMicrotask(()=>{queued=false;sync();});}
source.addEventListener('input',schedule);
window.addEventListener('royalty-draft-saved',schedule);
schedule();
})();

// Explicit period selection retains the complete adopted source for another period.
(()=>{
 const source=$('sales'),start=$('periodStart'),end=$('periodEnd');
 const panel=document.createElement('section');panel.id='sourcePeriodReview';panel.className='source-review';panel.hidden=true;
 panel.innerHTML='<h3>Select source dates</h3><div class="actions"><button type="button" class="btn small" id="previewSourcePeriod">Preview this period</button><button type="button" class="btn small ghost" id="restorePeriodSource" hidden>Use all imported rows</button><button type="button" class="btn small ghost" id="sourceDatesAsLabels" hidden>Use dates as labels</button></div><p id="sourcePeriodStatus" role="status"></p><div id="sourcePeriodCandidate" hidden><p id="sourcePeriodTotals"></p><button type="button" class="btn small" id="adoptSourcePeriod">Use these transactions</button></div>';
 document.querySelector('.import-row').after(panel);
 let pending=null,epoch=0;
 const fingerprint=()=>JSON.stringify([source.value,start.value,end.value]);
 const hasDates=()=>/(?:^|,)"?date"?(?:,|$)/.test(source.value.split(/\r?\n/,1)[0]);
 function reset(){epoch++;pending=null;$('sourcePeriodCandidate').hidden=true;panel.hidden=!hasDates()&&!sourceDateReview;$('sourceDatesAsLabels').hidden=!sourceDateReview;$('restorePeriodSource').hidden=!sourceProvenance||sourceProvenance.mapped_csv===source.value;if(!panel.hidden)$('sourcePeriodStatus').textContent=sourceDateReview?'Source dates must remain inside the reporting period. Preview again after changing rows or dates.':'Dates use the calendar days in your source.';}
 for(const input of [source,start,end])input.addEventListener('input',reset);
 window.addEventListener('royalty-draft-saved',()=>{panel.hidden=!hasDates()&&!sourceDateReview;$('sourceDatesAsLabels').hidden=!sourceDateReview;$('restorePeriodSource').hidden=!sourceProvenance||sourceProvenance.mapped_csv===source.value;});
 $('previewSourcePeriod').addEventListener('click',async()=>{
  const version=++epoch,before=fingerprint(),button=$('previewSourcePeriod');pending=null;$('sourcePeriodCandidate').hidden=true;button.disabled=true;
  try{
   const result=await api('/api/source-period',{sales_csv:source.value,reporting_period:{start:start.value,end:end.value}});
   if(version!==epoch||before!==fingerprint())return;
   pending={before,source:source.value,csv:result.sales_csv,reviewed:sourceDateReview};
   const money=cents=>(cents<0?'−':'')+'$'+(Math.abs(cents)/100).toFixed(2);
   $('sourcePeriodTotals').textContent=result.included_count+(result.included_count===1?' transaction · ':' transactions · ')+money(result.included_net_cents)+' net in this period. '+result.excluded_count+' outside · '+money(result.excluded_net_cents)+' net left out.';
   $('sourcePeriodStatus').textContent=result.first_date+' – '+result.last_date+' in the source being reviewed.';
   $('sourcePeriodCandidate').hidden=false;
  }catch(error){if(version===epoch)$('sourcePeriodStatus').textContent=error.message;}finally{button.disabled=false;}
 });
 $('adoptSourcePeriod').addEventListener('click',()=>{
  if(!pending||pending.before!==fingerprint())return reset();
  const {csv,source:original,reviewed}=pending;
  if(!sourceProvenance||(!reviewed&&sourceProvenance.mapped_csv!==original))restoreSourceProvenance({version:1,format:'custom',original_csv:original,mapped_csv:original});
  source.value=csv;source.dispatchEvent(new Event('input',{bubbles:true}));sourceDateReview=true;saveDraft();
  $('sourcePeriodStatus').textContent='Selected transactions are ready. Update the statement.';
 });
 $('sourceDatesAsLabels').addEventListener('click',()=>{
  if(!confirm('Stop checking source dates against this period? Reporting dates will be labels, and every current transaction will be included.'))return;
  sourceDateReview=false;invalidate();reset();
  $('sourcePeriodStatus').textContent='Reporting dates are labels. Every current transaction will be included.';
 });
 $('restorePeriodSource').addEventListener('click',()=>{
  if(!sourceProvenance||!confirm('Replace the current transaction text with all rows from the retained mapped source?'))return;
  source.value=sourceProvenance.mapped_csv;source.dispatchEvent(new Event('input',{bubbles:true}));
  $('sourcePeriodStatus').textContent='All imported rows restored. Choose dates and preview the next period.';
 });
 reset();
})();
