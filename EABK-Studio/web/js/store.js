export const state={model:null,lang:"ja",selected:null,tab:"reqs",query:"",fingerprint:null};
export function setModel(model){state.model=model;state.fingerprint=null;window.dispatchEvent(new Event("modelchange"));}
export function items(){return state.model?.requirements||[];}
