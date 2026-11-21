const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const labels=['Sign in','Cloud','Auto-download','Expose Ollama to the network','Model location','Context length'];
const tick=()=>new Promise(resolve=>setTimeout(resolve,20));
async function boot(files,reply){
 const dom=new JSDOM(html,{url:'http://127.0.0.1:8765/',runScripts:'outside-only'});
 const w=dom.window,calls=[];
 w.HTMLElement.prototype.scrollIntoView=function(){};
 w.fetch=async(url,options)=>{calls.push({url,options});return reply(url,options);};
 // Wait for jsdom's own DOMContentLoaded before evaluating handlers.
 if(w.document.readyState==='loading')await new Promise(r=>w.document.addEventListener('DOMContentLoaded',r,{once:true}));
 for(const file of files)w.eval(fs.readFileSync(path.join(root,'script',file),'utf8'));
 w.document.dispatchEvent(new w.Event('DOMContentLoaded'));
 return {dom,w,calls,$:id=>w.document.getElementById(id)};
}
const ok=data=>({ok:true,status:200,json:async()=>data});
test('all UI scripts exist and are referenced once',()=>{
 for(const name of ['theme.js','app.js','configuration.js','desktop_settings.js','tests.js','cleanup.js','model_cleanup.js']){
  assert.ok(fs.existsSync(path.join(root,'script',name)));
  assert.equal((html.match(new RegExp('src="./script/'+name.replace('.','\\.')+'"','g'))||[]).length,1);
 }
});
test('desktop settings renders six rows without treating values as HTML',async()=>{
 const x=await boot(['desktop_settings.js'],()=>ok({connected:true,settings:labels.map(label=>({label,status:'read',value:'<img src=x onerror=alert(1)>',source:'fixture'}))}));
 try{
  x.$('desktop-settings-refresh').click();await tick();
  assert.equal(x.$('desktop-settings-rows').children.length,6);
  assert.equal(x.$('desktop-settings-rows').querySelectorAll('img').length,0);
  assert.equal(x.calls[0].url,'/api/desktop-settings');
  assert.equal(x.$('desktop-settings-refresh').disabled,false);
 }finally{x.dom.window.close();}
});
test('desktop failed request reports failure and reenables refresh',async()=>{
 const x=await boot(['desktop_settings.js'],()=>{throw Error('fixture failure');});
 try{x.$('desktop-settings-refresh').click();await tick();assert.match(x.$('desktop-settings-status').textContent,/Read failed/);assert.equal(x.$('desktop-settings-refresh').disabled,false);}
 finally{x.dom.window.close();}
});
test('app scan renders response and never calls a write endpoint',async()=>{
 const x=await boot(['app.js'],()=>ok({checks:[],connection:{connected:true,version:'fixture'},inspected_at:new Date().toISOString()}));
 try{x.$('scan').click();await tick();assert.equal(x.$('version').textContent,'fixture');assert.equal(x.calls.length,1);assert.equal(x.calls[0].url,'/api/scan');assert.notEqual(x.calls[0].options.method,'POST');}
 finally{x.dom.window.close();}
});
test('app failure restores button and labels previous results',async()=>{
 const x=await boot(['app.js'],()=>{throw Error('fixture');});
 try{x.$('scan').click();await tick();assert.equal(x.$('scan').disabled,false);assert.match(x.$('message').textContent,/previous scan/);}
 finally{x.dom.window.close();}
});
test('configuration stages, reviews, requires consent, then dispatches token',async()=>{
 const state={supported:true,csrf_token:'csrf-fixture',restore_available:false,settings:[{name:'OLLAMA_NO_CLOUD',label:'Cloud',impact:'fixture',user:{value:'false'},choices:['true','false'],target:'true'}]};
 const x=await boot(['app.js','configuration.js','desktop_settings.js'],url=>{
  if(url==='/api/configuration')return ok(state);
  if(url==='/api/desktop-settings')return ok({connected:true,settings:[]});
  if(url==='/api/configuration/plan')return ok({plan_token:'plan-fixture',changes:[{name:'OLLAMA_NO_CLOUD',before:{value:'false'},after:{value:'true'}}]});
  if(url==='/api/configuration/apply')return ok({message:'fixture applied'});
  throw Error('Unexpected URL '+url);
 });
 try{
  x.w.document.querySelector('[data-page="configuration"]').click();await tick();
  assert.equal(x.$('title').textContent,'Configuration');
  x.$('cfg-preset').click();
  assert.equal(x.calls.filter(c=>c.url.endsWith('/apply')).length,0);
  x.$('cfg-review').click();await tick();
  assert.equal(x.$('cfg-confirm').disabled,true);
  x.$('cfg-consent').checked=true;x.$('cfg-consent').dispatchEvent(new x.w.Event('change'));
  assert.equal(x.$('cfg-confirm').disabled,false);
  x.$('cfg-confirm').click();await tick();
  const call=x.calls.find(c=>c.url.endsWith('/apply'));
  assert.ok(call);assert.equal(call.options.headers['X-OPC-CSRF'],'csrf-fixture');
  assert.deepEqual(JSON.parse(call.options.body),{plan_token:'plan-fixture',confirmed:true});
 }finally{x.dom.window.close();}
});
test('cleanup plan renders targets without treating values as HTML',async()=>{
 const payload='<img src=x onerror=alert(1)>';
 const x=await boot(['cleanup.js'],url=>{
  if(url==='/api/cleanup/plan')return ok({plans:[{id:'cli_history',title:'CLI prompt history',cleanup_available:true,findings:{warning:payload,requires_ollama_stop:true,targets:[{path:payload,context:'test',size_bytes:3,modified_at:'now'}]}}],csrf_token:'csrf-fixture',plan_token:'plan-fixture'});
  throw Error('Unexpected URL '+url);
 });
 try{
  x.$('cleanup-plan').click();await tick();await tick();
  const body=x.$('cleanup-plan-body');
  assert.equal(body.querySelectorAll('img').length,0);
  assert.match(body.textContent,/<img src=x onerror=alert\(1\)>/);
  assert.equal(body.querySelector('button[data-checker-id="cli_history"]').textContent,'Delete selected targets');
 }finally{x.dom.window.close();}
});
test('cleanup results render without treating values as HTML',async()=>{
 const payload='<svg onload=alert(1)>';
 const x=await boot(['cleanup.js'],url=>{
  if(url==='/api/cleanup/plan')return ok({plans:[{id:'logs',title:'Logs',cleanup_available:true,findings:{targets:[{path:'C:/logs/a.log',context:'test',size_bytes:1,modified_at:'now'}]}}],csrf_token:'csrf-fixture',plan_token:'plan-fixture'});
  if(url==='/api/cleanup/execute')return ok({result:{results:[{path:payload,status:'deleted',reason:payload}],note:payload},verification:{findings:{logs:0}}});
  throw Error('Unexpected URL '+url);
 });
 try{
  x.$('cleanup-plan').click();await tick();await tick();
  const consent=x.$('cleanup-plan-body').querySelector('input.cleanup-consent');consent.checked=true;
  x.$('cleanup-plan-body').querySelector('button[data-checker-id="logs"]').click();await tick();await tick();
  const body=x.$('cleanup-results-panel');assert.equal(body.hidden,false);
  assert.equal(body.querySelectorAll('svg').length,0);
  assert.match(body.textContent,/<svg onload=alert\(1\)>/);
 }finally{x.dom.window.close();}
});
