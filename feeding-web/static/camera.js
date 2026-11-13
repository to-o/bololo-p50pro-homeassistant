'use strict';
const $=id=>document.getElementById(id);
let client=null,generation=0,request=null,watch=null,deadline=null;
let theme;try{theme=localStorage.getItem('feeding-theme');}catch{}
document.documentElement.dataset.theme=theme||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
$('theme').onclick=()=>{const t=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=t;try{localStorage.setItem('feeding-theme',t);}catch{}};
const hevc=globalThis.RTCRtpReceiver?.getCapabilities?.('video')?.codecs.some(c=>c.mimeType.toLowerCase()==='video/h265')||false;
$('capabilities').textContent=hevc?'浏览器声明支持 H.265 视频；实际播放仍需连接验证。':'浏览器未声明 H.265 支持，可能无法播放此摄像头的原始视频。';
function error(message=''){$('error').textContent=message;$('error').hidden=!message;}
function clearVideo(){for(const e of [...$('video').children])if(e.id!=='placeholder')e.remove();$('placeholder').hidden=false;}
async function stop(message='已停止'){
 ++generation;request?.abort();request=null;clearInterval(watch);clearTimeout(deadline);watch=deadline=null;
 const previous=client;client=null;try{await previous?.leave();}catch{}
 clearVideo();$('start').disabled=false;$('stop').disabled=true;$('state').textContent=message;
}
function failure(code){if(['WEB_SECURITY_RESTRICT','WEBRTC_NOT_SUPPORTED'].includes(code))return '当前浏览器无法在此连接环境播放，请使用 Safari；如需安全连接，请先配置 HTTPS。';if(code==='MEDIA_DECRYPTION_FAILED')return '视频解密失败，请停止后重新连接。';return '画面连接失败，请停止后重试。';}
async function connect(){
 if($('start').disabled)return;
 const attempt=++generation;$('start').disabled=true;$('stop').disabled=false;$('state').textContent='正在连接摄像头…';error();
 let rtc;
 try{
  if(!globalThis.AgoraRTC)throw Error('PLAYER_MISSING');
  AgoraRTC.setLogLevel(4);AgoraRTC.disableLogUpload?.();
  request=new AbortController();const timeout=setTimeout(()=>request?.abort(),25000);
  let response,session;try{response=await fetch('/api/camera/session',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:request.signal,cache:'no-store'});session=await response.json();}finally{clearTimeout(timeout);}
  if(attempt!==generation)return;
  if(!response.ok){await stop('暂时无法连接');error(session.error||'摄像头暂时不可用');return;}
  rtc=AgoraRTC.createClient({mode:'live',codec:hevc?'h265':'h264'});client=rtc;
  if(session.mediaKey&&session.mediaSalt){const salt=Uint8Array.from(atob(session.mediaSalt),c=>c.charCodeAt(0));rtc.setEncryptionConfig('aes-128-gcm2',session.mediaKey,salt);}
  rtc.on('crypt-error',()=>{if(attempt===generation)error('视频解密失败，请停止后重试。');});
  let subscribing=false;
  async function subscribe(user){if(attempt!==generation||subscribing||String(user.uid)!==String(session.deviceRtcUid))return;subscribing=true;try{await rtc.subscribe(user,'video');if(attempt!==generation)return;user.videoTrack.play($('video'));$('state').textContent='已连接，等待画面…';}catch(e){if(attempt===generation)error(failure(e.code));}finally{subscribing=false;}}
  rtc.on('user-published',(user,kind)=>{if(kind==='video')void subscribe(user);});
  rtc.on('user-unpublished',(user,kind)=>{if(attempt===generation&&kind==='video'&&String(user.uid)===String(session.deviceRtcUid)){clearVideo();$('state').textContent='摄像头暂停画面，等待恢复…';}});
  rtc.on('connection-state-change',state=>{if(attempt===generation&&state==='DISCONNECTED'){void stop('连接已断开，可重新打开');}});
  watch=setInterval(()=>{if(attempt!==generation)return;const v=$('video').querySelector('video');if(v){v.muted=true;v.setAttribute('playsinline','');if(v.readyState>=2&&v.videoWidth>2&&v.videoHeight>2){$('placeholder').hidden=true;$('state').textContent='实时画面 · 静音';error();clearTimeout(deadline);}}},500);
  await rtc.setClientRole('host');await rtc.join(session.appId,session.channelName,session.rtcToken,session.userRtcUid);
  if(attempt!==generation){await rtc.leave();return;}
  $('state').textContent='已连接，等待摄像头画面…';
  for(const user of rtc.remoteUsers)if(user.hasVideo)void subscribe(user);
  deadline=setTimeout(()=>{if(attempt===generation&&!$('placeholder').hidden)error('暂未收到可播放画面，可能与编码兼容性有关。请停止后重试。');},30000);
 }catch(e){if(attempt!==generation)return;await stop('暂时无法播放');error(e.name==='AbortError'?'连接超时，请重试。':e.message==='PLAYER_MISSING'?'播放器组件未加载，请刷新后重试。':failure(e.code));}
}
$('start').onclick=connect;$('stop').onclick=()=>stop();
document.addEventListener('visibilitychange',()=>{if(document.hidden)void stop('已暂停，点打开画面继续');});
window.addEventListener('pagehide',()=>{void stop();});
