import os,json,re
from pathlib import Path
from .base import Check,inspect_path
class SavedModelsCheck(Check):
 id='saved_models';title='Saved sessions and custom models';area_number=4
 def category(self,p):
  name=p.name.lower()
  if name.endswith(('.safetensors','.gguf','.ggml','.pt','.pth','.bin')):return 'model_weight_candidate'
  if 'tokenizer' in name or name in ('config.json','special_tokens_map.json') or name.endswith('.safetensors.index.json'):return 'tokenizer_configuration_artifact'
  if name.startswith('modelfile') or p.suffix.lower() in ('.py','.ps1','.sh','.bat','.cmd'):return 'construction_source_candidate'
  return 'unknown_artifact'
 def inspect(self,c):
  r=self.result();roots=[]
  for a in c.accounts:
   roots.append((a.home/'.ollama/models',a.label+'_default'))
   if a.platform.startswith('linux'):roots.append((Path('/usr/share/ollama/.ollama/models'),'official_service_candidate'))
  roots.extend((Path(p),'explicit') for p in c.model_directories)
  for source,info in c.environment_sources.items():
   value=info.get('values',{}).get('OLLAMA_MODELS')
   if value:
    p=Path(os.path.expandvars(value))
    if p.is_absolute() and '%' not in str(p) and '$' not in str(p):roots.append((p,source+'_override_candidate'))
    else:r.locations.append(dict(path=value,context=source,kind='model_directory',status='not_inspected',details={'reason':'Override path unresolved.'}))
  seen=set();stores=[]
  for root,label in roots:
   if str(root) in seen:continue
   seen.add(str(root));counts={'path':str(root),'files_encountered':0,'successfully_parsed_manifests':0,'other_artifacts':0,'message_layer_candidates_detected':0,'enumeration_complete':True};stores.append(counts)
   rootitem=inspect_path(root,label,'directory');r.locations.append(rootitem)
   mi=inspect_path(root/'manifests',label,'directory');r.locations.append(mi);r.locations.append(inspect_path(root/'blobs',label,'directory'))
   if rootitem['status']=='not_inspected' or mi['status'] not in ('found','empty'):counts['enumeration_complete']=False;continue
   def walk_error(e):counts['enumeration_complete']=False
   stop=False
   for current,dirs,names in os.walk(root/'manifests',followlinks=False,onerror=walk_error):
    excluded=[n for n in dirs if (Path(current)/n).is_symlink()]
    if excluded:counts['enumeration_complete']=False
    dirs[:]=[n for n in dirs if n not in excluded]
    for name in names:
     if counts['files_encountered']>=c.max_entries:counts['enumeration_complete']=False;stop=True;break
     counts['files_encountered']+=1;p=Path(current)/name;category=self.category(p);item=inspect_path(p,label,category);r.locations.append(item);d=item['details'];d['category']=category
     valid=False
     if category=='unknown_artifact' and item['status'] in ('found','empty'):
      if item['size_bytes']>c.max_read_bytes:d['analysis']='Skipped oversized unknown artifact; not called a malformed manifest.'
      else:
       try:
        with p.open('rb') as f:raw=f.read(c.max_read_bytes+1)
        if len(raw)>c.max_read_bytes:raise ValueError()
        data=json.loads(raw)
        if isinstance(data,dict) and isinstance(data.get('layers'),list) and data.get('schemaVersion')==2:
         valid=True;item['kind']='valid_manifest';d['category']='valid_manifest';counts['successfully_parsed_manifests']+=1;layers=[]
         descriptors=list(data['layers'])+([data['config']] if isinstance(data.get('config'),dict) else [])
         for desc in descriptors[:c.max_entries]:
          if not isinstance(desc,dict):continue
          digest=desc.get('digest');media=desc.get('mediaType')
          if not isinstance(digest,str) or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}',digest):continue
          blob=root/'blobs'/digest.replace(':','-');message=media=='application/vnd.ollama.image.messages';counts['message_layer_candidates_detected']+=int(message)
          layers.append({'media_type':media,'digest':digest,'message_layer_candidate':message,'blob_path':str(blob),'blob_status':inspect_path(blob,label)['status']})
         d['layers']=layers;d['interaction_content']='not_examined';d['dates']='not_validated'
         if len(descriptors)>c.max_entries:item['status']='partial'
        else:d['analysis']='Not a recognized manifest; retained as unknown artifact.'
       except (ValueError,UnicodeError):d['analysis']='Not recognized as a JSON model manifest.'
       except OSError:item['status']='check_failed'
     elif category!='unknown_artifact':d['analysis']='Metadata only; not parsed as a manifest.'
     if not valid:counts['other_artifacts']+=1
    if stop:break
  for p in c.model_source_paths:r.locations.append(inspect_path(p,'explicit_model_source','directory' if Path(p).is_dir() else 'construction_source_candidate'))
  if not c.model_source_paths:r.locations.append(dict(path='Original Modelfiles and source scripts',context='no_locations_supplied',kind='model_sources',status='not_inspected',details={}))
  r.findings={'stores':stores}
  r.limitations=['Zero message-layer candidates does not prove no saved interaction content. System/template/parameter layer bodies are not examined.','Model weights and tokenizers are inventoried, not interpreted as malformed manifests. Categories are filename-based candidates.','Blob contents, unreferenced blobs, full shared-reference accounting and cleanup are not implemented.','Default/override paths are candidates, not a verified running path. Only supplied accounts and source locations are covered.']
  r.cleanup_available=any(store.get('message_layer_candidates_detected',0)>0 for store in stores)
  return r
 def plan(self,c):
  r=self.result();targets=[]
  for a in c.accounts:
   roots=[(a.home/'.ollama/models',a.label+'_default')]
   if a.platform.startswith('linux'):roots.append((Path('/usr/share/ollama/.ollama/models'),'official_service_candidate'))
   roots.extend((Path(p),'explicit') for p in c.model_directories)
   for source,info in c.environment_sources.items():
    value=info.get('values',{}).get('OLLAMA_MODELS')
    if value:
     p=Path(os.path.expandvars(value))
     if p.is_absolute() and '%' not in str(p) and '$' not in str(p):roots.append((p,source+'_override_candidate'))
   seen=set()
   for root,label in roots:
    if str(root) in seen:continue
    seen.add(str(root))
    manifests_dir=root/'manifests'
    if not manifests_dir.is_dir():continue
    try:
     for p in manifests_dir.rglob('*'):
      if p.is_symlink() or not p.is_file():continue
      if p.stat().st_size>c.max_read_bytes:continue
      try:
       with p.open('rb') as f:raw=f.read(c.max_read_bytes+1)
       if len(raw)>c.max_read_bytes:continue
       data=json.loads(raw)
       if isinstance(data,dict) and isinstance(data.get('layers'),list) and data.get('schemaVersion')==2:
        has_message=False
        message_blobs=[]
        for desc in data['layers']:
         if not isinstance(desc,dict):continue
         digest=desc.get('digest');media=desc.get('mediaType')
         if not isinstance(digest,str) or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}',digest):continue
         if media=='application/vnd.ollama.image.messages':
          has_message=True
          blob_path=root/'blobs'/digest.replace(':','-')
          message_blobs.append(str(blob_path))
        if has_message:
         targets.append({'manifest_path':str(p),'context':label,'message_blobs':message_blobs})
      except (ValueError,UnicodeError,OSError):pass
    except OSError:pass
  r.cleanup_available=len(targets)>0
  r.findings={'targets':targets,'requires_ollama_stop':False,'warning':'This deletes manifests containing message layers (saved sessions) and their associated message blobs. Model weights and other layers are never deleted.'}
  return r
 def execute(self,c,plan_result,confirmed=False):
  if not confirmed:raise ValueError('Confirmation required for cleanup.')
  results=[]
  for target in plan_result.findings['targets']:
   manifest_path=Path(target['manifest_path'])
   result={'manifest_path':target['manifest_path'],'context':target['context'],'status':'deleted','reason':None,'blobs_deleted':0}
   try:
    if manifest_path.is_symlink():result['status']='skipped';result['reason']='Symlink not followed.'
    elif not manifest_path.is_file():result['status']='skipped';result['reason']='Not a file or does not exist.'
    else:
     manifest_path.unlink()
     deleted_blobs=0
     for blob_path in target['message_blobs']:
      bp=Path(blob_path)
      try:
       if bp.is_file() and not bp.is_symlink():
        bp.unlink()
        deleted_blobs+=1
      except (OSError,PermissionError):pass
     result['blobs_deleted']=deleted_blobs
   except PermissionError:result['status']='access_denied';result['reason']='Permission denied.'
   except OSError as e:result['status']='failed';result['reason']=str(e)
   results.append(result)
  return {'results':results,'deleted':[r for r in results if r['status']=='deleted'],'failed':[r for r in results if r['status']=='failed'],'skipped':[r for r in results if r['status'] not in ('deleted','failed')]}
