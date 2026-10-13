/* Activation input is data, never code; no URL is fetched or evaluated. */
(function(root){'use strict';
function parse(text){
 if(typeof text!=='string'||text.length>4096)throw Error('Choose a small activation file or paste only the key.');
 text=text.trim();let id=null,key=text;
 if(text.startsWith('{')){let value;try{value=JSON.parse(text);}catch(e){throw Error('This activation file is not valid JSON.');}
 if(!value||value.format!=='s-bike-game-license-1'||Object.keys(value).some(k=>!['format','id','license_key'].includes(k))||!/^[a-z0-9-]{1,60}$/.test(value.id||''))throw Error('This is not a Hub activation file.');
 id=value.id;key=value.license_key;
 }
 if(typeof key!=='string'||!key.trim()||key.trim().length>1024||/\s|[\x00-\x20\x7f]/.test(key.trim())||/^(https?:|javascript:|data:|<)/i.test(key.trim()))throw Error('Paste only the activation key from your purchase page.');
 return {id,license_key:key.trim()};
}
if(typeof module!=='undefined'&&module.exports)module.exports={parse};else root.SBikeLicenseInput={parse};
})(typeof window==='undefined'?this:window);
