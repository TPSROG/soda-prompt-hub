from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from prompt_hub.remote_web import REMOTE_SCRIPT


def test_catalog_renders_without_waiting_for_labels_and_can_retry() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js required")
    start = REMOTE_SCRIPT.index("  async function loadLoras(")
    end = REMOTE_SCRIPT.index("  const modelTypeLabels=", start)
    harness = r"""
const assert=require('node:assert/strict');
const elements=new Map();
const $=key=>{
 if(!elements.has(key))elements.set(key,{
  textContent:'',disabled:false,hidden:false,setAttribute(){},removeAttribute(){}
 });return elements.get(key);
};
const state={catalog:[],loraQuery:'',collapsedLoraRoots:new Set(),loraLoaded:false};
let rendered=0,fail=false,requests=0;
const api=async url=>{
 requests++;if(fail)throw new Error('offline');
 return url.endsWith('/status')?{available:true,count:1}:{results:[{tags:['test']}]};
};
const setRemoteTabCount=()=>{};
const loraTreeData=()=>[];
const renderLoras=()=>{rendered++;};
let resolveLabels;
const window={ensureTagLabels:(tags,options)=>{
 assert.equal(options.allowModel,false);
 return new Promise(resolve=>{resolveLabels=resolve;});
}};
(async()=>{
  fail=true;await loadLoras();assert.equal(state.loraLoaded,false);
  assert.match($('#remoteLoraResultStatus').textContent,/清单未能加载/);
  fail=false;
  await Promise.race([loadLoras(),new Promise((_,reject)=>setTimeout(
   ()=>reject(new Error('catalog blocked by translation')),100))]);
  assert.equal(rendered,1);assert.equal(state.loraLoaded,true);
  state.loraLabelEpoch++;
  $('#remoteLoraTranslationStatus').textContent='AI stopped';
  resolveLabels(true);await new Promise(setImmediate);
  assert.equal($('#remoteLoraTranslationStatus').textContent,'AI stopped');
  fail=true;await loadLoras().catch(()=>{});
  assert.match($('#remoteLoraStatus').textContent,/offline/);
  assert.equal($('#remoteLoraReload').disabled,false);
  fail=false;const before=requests;await Promise.all([loadLoras(),loadLoras()]);
  assert.equal(requests-before,2);assert.equal(rendered,3);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    subprocess.run([node, "-e", REMOTE_SCRIPT[start:end] + harness], check=True)  # noqa: S603


def test_tag_label_retry_progress_abort_and_cache_race() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js required")
    base = (Path(__file__).resolve().parents[1] / "src/prompt_hub/web_assets/base.js").read_text()
    script = base[
        base.index("    async function ensureTagLabels(") : base.index(
            "    function tagValuesFromItem("
        )
    ]
    harness = r"""
const assert=require('node:assert/strict');
const tagLabelCache=new Map([['known',{en:'known',zh:'已知'}],['unknown',{en:'unknown',zh:''}]]);
let calls=[],progress=[],controller,race=false;
const fetchJsonWithTimeout=async(url,options)=>{
 const body=JSON.parse(options.body);calls.push(body);
 if(race) {
  tagLabelCache.set('race',{en:'race',zh:'已完成的中文'});
  return {items:[{en:'race',zh:''}]};
 }
 if(controller)controller.abort(new Error('stop'));
 return {items:body.tags.map(en=>({en,zh:en==='untranslated'?'':'译文'}))};
};
(async()=>{
 await ensureTagLabels(['known','unknown','untranslated','UNKNOWN'],{
  allowModel:true,retryUnknown:true,batchSize:1,onProgress:p=>progress.push(p)
 });
 assert.equal(calls.length,2);assert.equal(calls[0].allow_model,true);
 assert.equal(progress.at(-1).processed,2);assert.equal(progress.at(-1).translated,1);assert.equal(progress.at(-1).untranslated,1);
 calls=[];controller=new AbortController();
 await assert.rejects(ensureTagLabels(['a','b'],{batchSize:1,signal:controller.signal}),/stop/);
 assert.equal(calls.length,1);
 controller=null;calls=[];
 await ensureTagLabels(['readonly'],{allowModel:false});assert.equal(calls[0].allow_model,false);
 race=true;await ensureTagLabels(['race'],{allowModel:false});
 assert.equal(tagLabelCache.get('race').zh,'已完成的中文');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    subprocess.run([node, "-e", script + harness], check=True)  # noqa: S603


def test_json_requests_have_timeout_abort_and_http_errors() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js required")
    base = (Path(__file__).resolve().parents[1] / "src/prompt_hub/web_assets/base.js").read_text()
    script = base[
        base.index("    async function fetchJsonWithTimeout(") : base.index(
            "    window.fetchJsonWithTimeout"
        )
    ]
    harness = r"""
const assert=require('node:assert/strict');
let mode='wait';
const fetch=async(url,options)=>{
 if(mode==='error')return {ok:false,status:503,json:async()=>({detail:'offline'})};
 if(mode==='success')return {ok:true,json:async()=>({ok:true})};
 return new Promise((resolve,reject)=>{
  if(options.signal.aborted)reject(options.signal.reason);
  else options.signal.addEventListener('abort',()=>reject(options.signal.reason),{once:true});
 });
};
(async()=>{
 await assert.rejects(fetchJsonWithTimeout('/test',{},5),/请求超时/);
 const controller=new AbortController();controller.abort(new Error('stop'));
 await assert.rejects(fetchJsonWithTimeout('/test',{signal:controller.signal},1000),/stop/);
 mode='error';await assert.rejects(fetchJsonWithTimeout('/test'),/offline/);
 mode='success';assert.deepEqual(await fetchJsonWithTimeout('/test'),{ok:true});
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    subprocess.run([node, "-e", script + harness], check=True)  # noqa: S603
