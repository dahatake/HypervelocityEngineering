import {state,items} from "./store.js";
export function renderTables(view){
 const rows=items().filter(x=>!state.query||JSON.stringify(x).toLowerCase().includes(state.query.toLowerCase()));
 view.innerHTML=`<div class="toolbar"><h1>Tables</h1><button id="csv">CSV</button></div><table><thead><tr><th>ID</th><th>Title</th><th>Requirement</th><th>AC</th></tr></thead><tbody>${rows.map(x=>`<tr><td><span class="link" data-id="${x.id}">${x.id}</span></td><td>${x.title}</td><td>${x.text}</td><td>${x.acs.map(a=>a.id).join(", ")}</td></tr>`).join("")}</tbody></table>`;
 view.querySelectorAll("[data-id]").forEach(e=>e.onclick=()=>window.selectItem(e.dataset.id));
 view.querySelector("#csv").onclick=()=>{const csv=["id,title,text",...rows.map(x=>[x.id,x.title,x.text].map(v=>`"${String(v).replaceAll('"','""')}"`).join(","))].join("\n");const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));a.download="eabk-studio.csv";a.click();URL.revokeObjectURL(a.href);};
}
