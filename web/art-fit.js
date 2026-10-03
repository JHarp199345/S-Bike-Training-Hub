/* Local layout-fit assessment. A heuristic, not semantic recognition or an accuracy percentage. */
window.ArtFit=(()=>{
 const images=new Map();
 function image(a){if(!images.has(a.file))images.set(a.file,new Promise(resolve=>{const im=new Image();im.onload=()=>resolve(im);im.onerror=()=>resolve(null);im.src=a.file;}));return images.get(a.file);}
 function assess(a,im,w,h){
  if(!im||!w||!h)return {score:0,eligible:false};
  const scale=Math.max(w/im.naturalWidth,h/im.naturalHeight),vw=w/scale,vh=h/scale;
  const f=a.focal||[65,50],x=(im.naturalWidth-vw)*f[0]/100,y=(im.naturalHeight-vh)*f[1]/100;
  const box=a.subject_box||[Math.max(0,f[0]/100-.08),Math.max(0,f[1]/100-.15),Math.min(1,f[0]/100+.08),Math.min(1,f[1]/100+.15)];
  const bx=box[0]*im.naturalWidth,by=box[1]*im.naturalHeight,bw=(box[2]-box[0])*im.naturalWidth,bh=(box[3]-box[1])*im.naturalHeight;
  const kept=Math.max(0,Math.min(x+vw,bx+bw)-Math.max(x,bx))*Math.max(0,Math.min(y+vh,by+bh)-Math.max(y,by))/(bw*bh||1);
  const area=vw*vh/(im.naturalWidth*im.naturalHeight),resolution=Math.min(1,1/scale);
  const score=Math.round(45*area+40*kept+15*resolution);
  return {score,eligible:score>=70&&kept>=.9,subjectKept:Math.round(100*kept),width:im.naturalWidth,height:im.naturalHeight};
 }
 async function choose(assets,w,h,preferred){const scored=await Promise.all(assets.map(async a=>({asset:a,...assess(a,await image(a),w,h)})));const valid=scored.filter(x=>x.eligible).sort((a,b)=>b.score-a.score);const best=valid[0];if(!best)return null;const near=valid.filter(x=>x.score>=best.score-5);return near.find(x=>x.asset.id===preferred)||near[Math.floor(Math.random()*near.length)];}
 return {assess,choose,image};
})();
