// Phone ride readout: cadence plus one rotating figure in frosted glass, bottom left. Tap for everything; easy to
// dismiss. Reads the ride's status only; it never changes the ride.
const $=id=>document.getElementById(id);
const box=$('ride-readout'),sheet=$('ride-info'),grid=$('ride-info-grid');
let status={},turn=0;
const fmt=(v,d=0)=>v==null||Number.isNaN(+v)?'—':(+v).toLocaleString(undefined,{maximumFractionDigits:d,minimumFractionDigits:d});
const ROTATE=[
  ['kcal/min',s=>fmt(s.kcal_min,1)],
  ['watts',s=>fmt(s.power)],
  ['km',s=>fmt(s.distance,2)],
  ['time',s=>s.elapsed||'—'],
];
function draw(){
  const s=status,[label,value]=ROTATE[turn%ROTATE.length];
  $('ride-readout-rpm').textContent=s.bike?fmt(s.cadence):'—';
  $('ride-readout-value').textContent=value(s);$('ride-readout-label').textContent=label;
  box.classList.toggle('asleep',!s.bike);
  if(sheet.open)fill();
}
function fill(){
  const s=status,work=s.test||s.workout,target=s.erg;
  const rows=[['Cadence',fmt(s.cadence),'rpm'],['Power',fmt(s.power),'W'],['Calories',fmt(s.kcal_min,1),'kcal/min'],['Speed',fmt(s.speed,1),'km/h'],
    ['Distance',fmt(s.distance,2),'km'],['Ride time',s.elapsed||'—',''],['Energy',fmt(s.kcal),'kcal'],['Work',fmt(s.kj),'kJ'],
    ['Grade',s.grade==null?'—':(s.grade>0?'+':'')+fmt(s.grade,1),'%'],['Gear',s.gear==null?'—':(s.gear>0?'+':'')+s.gear,''],
    ...(target?[['Target',fmt(target),'W']]:[]),...(work?[[s.test?'Test':'Workout',work.name||work.phase||'',(work.step!==undefined?'step '+work.step+(work.steps?'/'+work.steps:''):''),'wide']]:[]),
    ['Bike',s.bike?'Connected':'Asleep · pedal to wake','','wide']];
  grid.replaceChildren(...rows.map(([k,v,u,wide])=>{const d=document.createElement('div');if(wide)d.className='wide';d.innerHTML=`<small></small><b></b>`;d.querySelector('small').textContent=k;d.querySelector('b').textContent=v+(u?' ':'');if(u){const x=document.createElement('span');x.textContent=u;d.querySelector('b').append(x);}return d;}));
}
window.addEventListener('hub-ride-status',e=>{status=e.detail||{};draw();});
setInterval(()=>{if(document.hidden||sheet.open)return;turn++;box.classList.add('turn');draw();setTimeout(()=>box.classList.remove('turn'),350);},4000);
box.onclick=()=>{fill();sheet.showModal();};
$('ride-info-close').onclick=()=>sheet.close();
sheet.addEventListener('click',e=>{if(e.target===sheet)sheet.close();});   // tap outside the card to dismiss
let startY=null;sheet.addEventListener('touchstart',e=>{startY=e.touches[0].clientY;},{passive:true});
sheet.addEventListener('touchend',e=>{if(startY!=null&&e.changedTouches[0].clientY-startY>70)sheet.close();startY=null;});   // swipe down to dismiss
draw();
