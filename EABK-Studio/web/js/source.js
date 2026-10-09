import {state} from "./store.js";
export function renderSource(view){const files=state.model?.files||[];view.innerHTML=`<h1>Source</h1><ul>${files.map(f=>`<li><span class="link" data-file="${f}">${f}</span></li>`).join("")}</ul>`;view.querySelectorAll("[data-file]").forEach(e=>e.onclick=()=>window.selectItem(e.dataset.file));}
