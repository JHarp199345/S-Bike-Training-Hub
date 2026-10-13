/* Local-only invitation policy. No training records or readings are persisted. */
(function(root){'use strict';
function fresh(){return {modules:{},shown:{},never:false,supported:false,current:null};}
function observe(state,status,now){
 const mode=status.mode, key=mode&&Number.isFinite(mode.since)?mode.id+':'+mode.since:null;
 let current=state.current;
 if(current&&current.key!==key){
  if(current.seconds>=60){state.modules[current.id]=(state.modules[current.id]||0)+1;}
  state.current=null;
 }
 if(key){
  current=state.current;
  if(!current||current.key!==key)current=state.current={key,id:mode.id,name:mode.name||'this module',seconds:0,last:now};
  const delta=Math.max(0,Math.min(10,now-current.last));
  if(status.bike&&!status.no_bike&&status.cadence>0&&status.power>0)current.seconds+=delta;
  current.last=now;
 }
}
function pending(state){if(state.current||state.never||state.supported)return null;
 return Object.keys(state.modules).find(id=>state.modules[id]>=3&&!state.shown[id])||null;}
const api={fresh,observe,pending};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.HubSupportPolicy=api;
})(typeof window==='undefined'?globalThis:window);
