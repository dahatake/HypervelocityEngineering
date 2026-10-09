/* FR-001 AC-001; FR-010 AC-010; FR-012 AC-012; FR-013 AC-013; NFR-SEC-002 AC-024 */
"use strict";
let model=null, fingerprint="", selected="";
const $=id=>document.getElementById(id);
async function api(path, options){const r=await fetch(path,options);const body=await r.json();if(!r.ok)throw Error(body.error||"data error");return body}
function detail(req){selected=req.id;$("drawer").hidden=false;const feature=model.catalog.find(x=>x.requirement_id===req.id);const tests=model.tests.filter(x=>x.requirement_ids.includes(req.id));$("drawer").textContent=`${req.id} ${req.title}\ncatalog: ${feature?.title||"none"}\nfile: ${feature?.files||"none"}\ntest: ${tests.map(x=>x.id).join(", ")||feature?.tests||"none"}`}
function render(){
 const route=(location.hash.match(/^#\/([^?]+)/)||[])[1]||"tables", q=new URLSearchParams((location.hash.split("?")[1]||"")).get("q")||$("q").value;
 $("q").value=q; const rows=model.reqs.filter(x=>!q||(`${x.id} ${x.title}`).toLowerCase().includes(q.toLowerCase()));
 $("view").replaceChildren(Object.assign(document.createElement("h1"),{textContent:route==="tables"?"管理データ":route}));
 for(const req of rows){const b=Object.assign(document.createElement("button"),{className:"item"});b.append(Object.assign(document.createElement("span"),{textContent:req.id}),` — ${req.title}`);b.onclick=()=>detail(req);$("view").append(b)}
 if(selected){const req=model.reqs.find(x=>x.id===selected);if(req)detail(req)}
}
async function load(){model=await api("/api/model");const repo=await api("/api/repo");$("repoBtn").textContent=repo.name;fingerprint=(await api("/api/fingerprint")).fingerprint;render()}
$("repoBtn").onclick=()=>{$("repoPath").value="";$("repoDialog").showModal()};
$("repoOk").onclick=async e=>{e.preventDefault();try{model=await api("/api/repo",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({repo:$("repoPath").value})});$("repoBtn").textContent=model.meta.name;$("repoDialog").close();render()}catch(err){$("toast").textContent=`data error: ${err.message}`}};
$("q").oninput=render;window.onhashchange=render;
setInterval(async()=>{try{const next=(await api("/api/fingerprint")).fingerprint;if(next!==fingerprint){fingerprint=next;model=await api("/api/model");$("toast").textContent="Management data updated";render()}}catch(err){$("toast").textContent=err.message}},1000);
load().catch(err=>$("toast").textContent=`data error: ${err.message}`);
