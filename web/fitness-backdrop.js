/* Slow scenery movement; cards keep ordinary document scrolling. */
(()=>{
 if(document.documentElement.dataset.embedded==='true')return;
 const surfaces=[...document.querySelectorAll('.fitness-dashboard-surface,body.fitness-landscape')];
 if(!surfaces.length)return;
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');let scheduled=false;
 const paint=()=>{scheduled=false;const movement=reduced.matches?0:Math.min(12,Math.max(0,window.scrollY)*.003);surfaces.forEach(el=>el.style.setProperty('--fitness-pan',movement+'%'));};
 addEventListener('scroll',()=>{if(!scheduled){scheduled=true;requestAnimationFrame(paint)}},{passive:true});
 reduced.addEventListener('change',paint);paint();
})();
