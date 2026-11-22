/* Only populates the added Current Ollama Settings card. */
'use strict';
document.addEventListener('DOMContentLoaded',()=>{
 const $=id=>document.getElementById(id),button=$('desktop-settings-refresh');if(!button)return;
 const labels=['Sign in','Cloud','Auto-download','Expose Ollama to the network','Model location','Context length'];
 function row(cells){const tr=document.createElement('tr');for(const text of cells){const td=document.createElement('td');td.textContent=text;tr.append(td);}return tr;}
 function render(rows,data){const body=$('desktop-settings-rows');body.replaceChildren();for(const label of labels){const item=rows.find(r=>r.label===label);body.append(row([label,item?.status==='read'?item.value:'Could not read',item?.status==='read'?(item.source||'Local desktop app'):(item?.reason||'Not read yet')]));}
  if(data&&data.version){const v=data.version;body.append(row(['Ollama version',v.version||'Unknown',v.version?(v.source||''):'Could not determine version from local sources']));}
  if(data&&data.updater){const u=data.updater;const value={in_confirmed_affected_range:'Inside confirmed-affected range',outside_confirmed_affected_range:'Outside confirmed-affected range',unknown:'Unassessed',not_assessed:'Not assessed',not_applicable:'Not applicable'}[u.status]||u.status;const label=u.platform==='macos'?'macOS auto-update assessment':u.platform==='windows'?'Windows auto-update risk':'Auto-update assessment';body.append(row([label,value,u.message||'']));}}
 render([]);let loaded=false,busy=false;
 async function load(){if(busy)return;busy=true;button.disabled=true;$('desktop-settings-status').textContent='Reading local Ollama settings…';const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);try{const response=await fetch('/api/desktop-settings',{cache:'no-store',signal:controller.signal});if(!response.ok)throw new Error(response.status===404?'Start server_with_settings.py; the original helper has no desktop-settings route.':'Helper returned HTTP '+response.status);const data=await response.json();if(!Array.isArray(data.settings))throw new Error('Unexpected helper response.');render(data.settings,data);loaded=true;$('desktop-settings-status').textContent=(data.connected?'Desktop settings read at '+new Date().toLocaleTimeString()+'. ':'Could not read desktop settings. ')+(data.note||data.error||'');}catch(e){render(labels.map(label=>({label,status:'could_not_read',reason:e.name==='AbortError'?'Request timed out.':e.message})));$('desktop-settings-status').textContent='Read failed; no settings were changed.';}finally{clearTimeout(timer);busy=false;button.disabled=false;}}
 button.onclick=load;
 // The existing configuration handler stays intact; observer only reads the new card.
 const section=$('configuration');if(section)new MutationObserver(()=>{if(!section.hidden&&!loaded)load();}).observe(section,{attributes:true,attributeFilter:['hidden']});
 if(section&&!section.hidden)load();
});
