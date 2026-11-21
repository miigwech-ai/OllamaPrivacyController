/* Dedicated test runner UI. All commands are selected by the backend. */
'use strict';
document.addEventListener('DOMContentLoaded',()=>{
 const $=id=>document.getElementById(id);
 const nav=document.querySelector('[data-page="tests"]');
 nav.addEventListener('click',e=>{
  e.stopPropagation();
  document.querySelectorAll('.page').forEach(p=>p.hidden=p.id!=='tests');
  document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b===nav));
  $('title').textContent='Tests';
 });
 const make=(tag,text)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=String(text);return el;};
 let busy=false;
 function render(suite,data){
  const root=$('tests-'+suite+'-result');root.replaceChildren();
  root.append(make('h3',data.status==='passed'?'All tests passed':data.status==='completed_with_skips'?'Completed with skipped tests':data.status==='failed'?'Tests need attention':'Test run could not complete'));
  root.append(make('p',data.message));
  if(data.counts){
   const cards=make('div');cards.className='cards';
   for(const [label,key] of [['Passed','passed'],['Failed','failed'],['Errors','errors'],['Skipped','skipped']]){
    const card=make('article');card.append(make('h3',label));const number=make('div',data.counts[key]);number.className='value';card.append(number);cards.append(card);
   }root.append(cards);
  }
  root.append(make('p','Finished '+new Date(data.finished_at).toLocaleString()+' · '+data.duration_seconds+' seconds'));
  if(data.cases?.length){
   const details=make('details');details.open=data.status==='failed';details.append(make('summary','Individual results ('+data.cases.length+')'));
   const wrap=make('div');wrap.className='table-wrap';const table=make('table'),head=make('thead'),tr=make('tr'),body=make('tbody');
   ['Test','Group','Result','Seconds'].forEach(t=>tr.append(make('th',t)));head.append(tr);table.append(head);
   for(const item of data.cases){
    const row=make('tr'),name=make('td',item.name);
    if(item.detail){const more=make('details');more.append(make('summary','Details'),make('pre',item.detail));name.append(more);}
    row.append(name,make('td',item.group),make('td',item.status),make('td',item.time));body.append(row);
   }table.append(body);wrap.append(table);details.append(wrap);root.append(details);
  }
  if(data.output){const details=make('details');details.append(make('summary','Runner output'),make('pre',data.output));root.append(details);}
 }
 async function run(suite){
  if(busy)return;busy=true;
  for(const s of ['python','js'])$('tests-'+s+'-run').disabled=true;
  $('tests-status').textContent='Running '+(suite==='python'?'Python':'JavaScript')+' tests… This may take up to two minutes.';
  $('tests-'+suite+'-result').replaceChildren(make('p','Running…'));
  try{
   const session=await fetch('/api/tests/session',{cache:'no-store'});
   const auth=await session.json();if(!session.ok)throw Error(auth.error||'Cannot initialize test runner.');
   const response=await fetch('/api/tests/run',{method:'POST',cache:'no-store',headers:{'Content-Type':'application/json','X-OPC-CSRF':auth.csrf_token},body:JSON.stringify({suite})});
   const data=await response.json();if(!response.ok)throw Error(data.error||'Test runner request failed.');
   render(suite,data);$('tests-status').textContent='Finished. Review the results below.';
  }catch(error){$('tests-'+suite+'-result').replaceChildren(make('p',error.message));$('tests-status').textContent='Could not retrieve results. If the connection was interrupted, the server may still be running the suite.';}
  finally{busy=false;for(const s of ['python','js'])$('tests-'+s+'-run').disabled=false;}
 }
 $('tests-python-run').onclick=()=>run('python');$('tests-js-run').onclick=()=>run('js');
});
