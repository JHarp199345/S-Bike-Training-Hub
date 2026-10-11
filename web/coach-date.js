/* Local calendar dates: an open Hub must advance after midnight, including DST. */
(function(root){
  const localDate=(date=new Date())=>[date.getFullYear(),String(date.getMonth()+1).padStart(2,'0'),String(date.getDate()).padStart(2,'0')].join('-');
  function phaseState(phase,today=localDate()){
    if(phase.end&&phase.end<=today)return 'past';
    if(phase.start&&phase.start<=today&&phase.end&&today<phase.end)return 'current';
    return 'upcoming';
  }
  function createController({loadedDate,refresh,busy=()=>false,pending=()=>{},failed=()=>{},now=()=>new Date()}){
    let inFlight=null;
    function check(){
      const target=localDate(now()),loaded=loadedDate();
      if(!loaded||target===loaded)return Promise.resolve(false);
      if(inFlight)return inFlight;
      if(busy()){pending(target,loaded);return Promise.resolve(false);}
      inFlight=Promise.resolve().then(()=>refresh(target)).catch(error=>{failed(error);return false;}).finally(()=>{inFlight=null;});
      return inFlight;
    }
    return {check};
  }
  const api={localDate,phaseState,createController};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.CoachDate=api;
})(typeof window!=='undefined'?window:globalThis);
