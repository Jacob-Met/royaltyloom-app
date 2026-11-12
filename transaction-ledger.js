'use strict';
(() => {
 const $ = id => document.getElementById(id);
 const search = $('auditSearch'), type = $('auditType'), clear = $('auditClear');
 let entries = [], sourceIdentity = "";
 search.placeholder='Source ID, description or statement row';
 const money = cents => (cents < 0 ? '−' : '+') + '$' + Math.floor(Math.abs(cents)/100) + '.' + String(Math.abs(cents)%100).padStart(2,'0');
 function show() {
  const query = search.value.trim().toLocaleLowerCase();
  const rowReference=/^(?:statement\s+)?row\s*:?\s*([1-9]\d*)$/i.exec(query);
  const matches = entries.map((entry,index)=>({entry,index})).filter(({entry,index}) =>
   (!type.value || entry.type === type.value) &&
   (!query || (rowReference ? index+1===Number(rowReference[1]) : (entry.id+' '+entry.description+' '+(entry.date||'')).toLocaleLowerCase().includes(query))));
  const filtered = Boolean(query || type.value), list = $('auditRows');
  list.replaceChildren();
  let cents = 0;
  for (const {entry,index} of matches) {
   cents += entry.type === 'sale' ? entry.cents : -entry.cents;
   const row = document.createElement('li');row.className='audit-row'+(entry.type==='sale'?'':' deduction');
   const details=document.createElement('div'), id=document.createElement('span'), kind=document.createElement('span'), description=document.createElement('div'), amount=document.createElement('strong');
   id.className='audit-id';id.textContent='Statement row '+(index+1)+' · '+entry.id;row.dataset.sourceRow=String(index+1);
   kind.className='audit-kind';kind.textContent=entry.type+(entry.date?' · '+entry.date:'');
   description.className='audit-description';description.textContent=entry.description||'No description supplied';
   amount.className='audit-value';amount.textContent=money(entry.type==='sale'?entry.cents:-entry.cents);
   details.append(id,kind,description);row.append(details,amount);list.append(row);
  }
  $('auditCount').textContent=entries.length+' '+(entries.length===1?'transaction':'transactions');
  $('auditMatches').textContent=matches.length+' of '+entries.length+' entries shown · '+(filtered?'Matching rows':'All rows')+' '+money(cents);
  $('auditEmpty').hidden=matches.length>0;
  clear.disabled=!filtered;
 }
 window.renderTransactionLedger = data => {
  const identity=JSON.stringify(data.map(row=>[row.id,row.type,row.cents,row.description,row.date||'']));
  if(identity!==sourceIdentity){search.value='';type.value='';}
  sourceIdentity=identity;entries=data;
  show();
 };
 search.addEventListener('input',show);
 type.addEventListener('change',show);
 clear.addEventListener('click',()=>{search.value='';type.value='';show();search.focus();});
})();
