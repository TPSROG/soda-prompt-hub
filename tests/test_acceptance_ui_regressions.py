from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from prompt_hub.remote_web import REMOTE_SCRIPT
from prompt_hub.workspace_web import WORKSPACE_SCRIPT


def run_js(script: str) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js required for UI behavior tests")
    subprocess.run([node, "-e", script], check=True)  # noqa: S603 - repository script and fixed harness


def test_approve_unchanged_captions_and_do_not_approve_on_failed_save() -> None:
    script = WORKSPACE_SCRIPT[
        WORKSPACE_SCRIPT.index("  async function saveDetail(") : WORKSPACE_SCRIPT.index(
            "  async function saveKrea2Draft("
        )
    ]
    run_js(
        script
        + r"""
const assert=require('node:assert/strict');
let calls=[],fail=false;
const item={relative_path:'a.png',curation:{captions:{
 anima:{current:'1girl',status:'draft'},krea2:{current:'An adult explorer.',status:'draft'}
}}};
const state={active:{workspace_id:'qa'},selected:new Set(),pageItems:[item]};
const values={'#datasetDetailStatus':'approved','#datasetDetailAnima':'1girl',
 '#datasetDetailKrea2':'An adult explorer.'};
const $=id=>({value:values[id]});
const detailItem=()=>item, jsonOptions=body=>({body});
const loadReport=async()=>{},renderDetail=()=>{};
const api=async(url,options)=>{calls.push({url,...options.body});
 if(fail && url.endsWith('/caption'))throw Error('write failed');};
(async()=>{
 await saveDetail();
 assert.equal(calls.filter(c=>c.url.endsWith('/caption')).length,2);
 assert.ok(calls.filter(c=>c.url.endsWith('/caption')).every(c=>c.caption_status==='reviewed'));
 assert.ok(calls.at(-1).url.endsWith('/review'));
 calls=[];fail=true;
 await assert.rejects(saveDetail(),/write failed/);
 assert.equal(calls.filter(c=>c.url.endsWith('/review')).length,0);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    )


def test_live_offline_status_replaces_old_ready_badge() -> None:
    script = REMOTE_SCRIPT[
        REMOTE_SCRIPT.index("  function renderLiveConnection(") : REMOTE_SCRIPT.index(
            "  let liveConnectionBusy="
        )
    ]
    run_js(
        script
        + r"""
const assert=require('node:assert/strict');
const badge={textContent:'Windows 已就绪'},message={textContent:'自检通过'};
const card={querySelector:key=>key==='[data-remote-state]'?badge:message};
renderLiveConnection(card,{label:'Worker 连接中断',detail:'心跳已过期',
 can_compute:false,heartbeat_age_seconds:60});
assert.equal(badge.textContent,'Worker 连接中断');assert.match(badge.className,/failed/);
assert.match(message.textContent,/60 秒/);
renderLiveConnection(card,{label:'已连接',detail:'实时正常',can_compute:true,heartbeat_age_seconds:0});
assert.equal(badge.textContent,'已连接');assert.match(badge.className,/ready/);
"""
    )


def test_result_refresh_preserves_unsaved_prompt_and_asset_draft_and_project_switch() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "src/prompt_hub/web_assets/creative.js"
    ).read_text()
    script = source[
        source.index("  async function refreshImportedResults(") : source.index(
            "  window.addEventListener('prompt-hub-results-imported'"
        )
    ]
    run_js(
        script
        + r"""
const assert=require('node:assert/strict');
let resolve;
const creativeJson=()=>new Promise(r=>resolve=r);
const creativeState={projects:[{project_id:'a'}],project:{project_id:'a',brief_zh:'unsaved',
 generation:{seed:'42',result_assets:[{asset_id:'old',wd14_tagging:{draft_tags:'editing'}}]}}};
const renderResultGallery=()=>{},refreshProjectJourney=async()=>{};
(async()=>{
 const pending=refreshImportedResults('a');
 resolve({project_id:'a',brief_zh:'server',generation:{seed:'1',result_assets:[{asset_id:'old'},{asset_id:'new'}]}});
 await pending;
 assert.equal(creativeState.project.brief_zh,'unsaved');assert.equal(creativeState.project.generation.seed,'42');
 assert.equal(creativeState.project.generation.result_assets.length,2);
 assert.equal(creativeState.project.generation.result_assets[0].wd14_tagging.draft_tags,'editing');
 const late=refreshImportedResults('a');creativeState.project={project_id:'b',brief_zh:'other'};
 resolve({project_id:'a',generation:{result_assets:[]}});await late;
 assert.deepEqual(creativeState.project,{project_id:'b',brief_zh:'other'});
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    )
