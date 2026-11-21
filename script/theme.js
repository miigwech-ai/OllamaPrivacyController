/* UI theme only. No network requests or Ollama changes. */
'use strict';
(()=>{
 const themes={
 copper:{bg:'#f6f3ef',paper:'#fffdfb',side:'#fffaf5',text:'#352d28',muted:'#71665e',border:'#e6ddd5',accent:'#a34e23',accentHover:'#813b19',accentText:'#ffffff',strong:'#813b19',soft:'#faeee5',softBorder:'#e9c8b2',head:'#f7f0e8',hover:'#fff8f1',code:'#f5f0e9',error:'#a22d21',errorBg:'#fff0ec',focus:'#a34e23'},
 light:{bg:'#f3f4f6',paper:'#ffffff',side:'#fafafa',text:'#252b34',muted:'#626c79',border:'#dce1e7',accent:'#405675',accentHover:'#2c405e',accentText:'#ffffff',strong:'#2c405e',soft:'#eaf0f7',softBorder:'#c7d3e3',head:'#edf1f5',hover:'#f5f8fc',code:'#f0f3f6',error:'#a22d21',errorBg:'#fff0ec',focus:'#405675'},
 slate:{bg:'#e9eef3',paper:'#f8fafc',side:'#e1e8f0',text:'#263648',muted:'#53677c',border:'#cbd5e1',accent:'#3c607e',accentHover:'#29475f',accentText:'#ffffff',strong:'#29475f',soft:'#dce9f2',softBorder:'#abc1d2',head:'#e2eaf2',hover:'#edf4f9',code:'#e7eef5',error:'#a22d21',errorBg:'#fff0ec',focus:'#3c607e'},
 dark:{bg:'#191b1f',paper:'#24272c',side:'#202227',text:'#eee7df',muted:'#b9afa5',border:'#45464b',accent:'#a34e23',accentHover:'#813b19',accentText:'#ffffff',strong:'#f0b48a',soft:'#3c2c23',softBorder:'#82593e',head:'#302d2b',hover:'#302c29',code:'#1c1e22',error:'#ffb4a7',errorBg:'#402824',focus:'#f0b48a'}
 };
 const key='opc-ui-theme';let current='copper';
 function valid(name){return Object.prototype.hasOwnProperty.call(themes,name);}
 try{const saved=localStorage.getItem(key);if(valid(saved))current=saved;}catch{}
 function apply(name,persist){
  if(!valid(name))return;
  current=name;const root=document.documentElement,p=themes[name],dark=name==='dark';
  root.dataset.uiTheme=name;root.dataset.theme=dark?'dark':'light';
  root.classList.toggle('theme-dark',dark);root.classList.toggle('theme-light',!dark);
  root.style.colorScheme=dark?'dark':'light';
  for(const [token,value] of Object.entries(p))root.style.setProperty('--ui-'+token,value);
  const bulma={'body-background-color':p.bg,'body-color':p.text,'scheme-main':p.paper,'text':p.text,'text-strong':p.text,'border':p.border,'link-text':p.strong};
  for(const [token,value] of Object.entries(bulma))root.style.setProperty('--bulma-'+token,value);
  const select=document.getElementById('opc-theme-select');if(select)select.value=name;
  if(persist)try{localStorage.setItem(key,name);}catch{}
 }
 apply(current,false);
 function mount(){const select=document.getElementById('opc-theme-select');if(!select)return;select.value=current;select.addEventListener('change',()=>apply(select.value,true));}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
 window.addEventListener('storage',event=>{if(event.key===key)apply(valid(event.newValue)?event.newValue:'copper',false);});
})();
