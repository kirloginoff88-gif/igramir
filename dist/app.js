'use strict';

const byId = id => document.getElementById(id);
const canvas = byId('canvas');
const ctx = canvas.getContext('2d');
const source = document.createElement('canvas');
source.width = canvas.width;
source.height = canvas.height;
const sketch = source.getContext('2d', {willReadFrequently: true});
const upload = byId('file');
const fabric = byId('fabric');
const size = byId('size');
const status = byId('status');
const dialog = byId('dialog');
const telegram = window.Telegram?.WebApp;
const inTelegram = Boolean(telegram?.initData);
let image = null;
let originalFile = null;
let conceptFile = null;
let filename = 'Лисёнок — пример';
let loadVersion = 0;
let concept;

function ellipse(x, y, rx, ry, color) {
  const fill = sketch.createRadialGradient(x-rx*.25,y-ry*.35,2,x,y,Math.max(rx,ry));
  fill.addColorStop(0,color);
  fill.addColorStop(1,color+'bb');
  sketch.fillStyle = fill;
  sketch.beginPath();
  sketch.ellipse(x,y,rx,ry,0,0,Math.PI*2);
  sketch.fill();
}

function ear(x, y, direction, color, scale) {
  sketch.fillStyle = color;
  sketch.beginPath();
  sketch.moveTo(x,y);
  sketch.quadraticCurveTo(x+direction*70*scale,y-140*scale,x+direction*92*scale,y-112*scale);
  sketch.quadraticCurveTo(x+direction*118*scale,y-103*scale,x+direction*108*scale,y+22*scale);
  sketch.closePath();
  sketch.fill();
}

function drawFox() {
  ellipse(420,350,95,56,'#df7135');
  ellipse(468,340,44,40,'#ffdfb2');
  ellipse(339,352,104,116,'#e97e47');
  ellipse(339,370,62,74,'#ffe3bf');
  ellipse(272,433,55,40,'#9b4f39');
  ellipse(404,433,55,40,'#9b4f39');
  ear(307,203,-1,'#eb824c',1);
  ear(373,203,1,'#eb824c',1);
  ear(291,198,-1,'#a85357',.62);
  ear(389,198,1,'#a85357',.62);
  ellipse(340,230,131,105,'#ee854a');
  ellipse(286,266,76,44,'#ffe8cb');
  ellipse(394,266,76,44,'#ffe8cb');
  ellipse(286,226,10,15,'#322935');
  ellipse(394,226,10,15,'#322935');
  ellipse(283,222,3,4,'#ffffff');
  ellipse(391,222,3,4,'#ffffff');
  ellipse(340,254,16,10,'#423141');
  sketch.strokeStyle='#634250';
  sketch.lineWidth=3;
  sketch.beginPath();
  sketch.moveTo(340,263);
  sketch.quadraticCurveTo(341,280,359,270);
  sketch.moveTo(340,263);
  sketch.quadraticCurveTo(340,280,321,270);
  sketch.stroke();
}

function drawConcept() {
  if (!size.reportValidity() || !size.value) return;
  const {width,height} = canvas;
  sketch.clearRect(0,0,width,height);
  if (image) {
    const scale = Math.min(490/image.width,380/image.height);
    const w = image.width * scale;
    const h = image.height * scale;
    sketch.drawImage(image,(width-w)/2,(height-h)/2,w,h);
  } else {
    drawFox();
  }

  const pixels = sketch.getImageData(0,0,width,height);
  const rgba = pixels.data;
  const texture = {soft: 22, long: 36, smooth: 9}[fabric.value];
  for (let y=0; y<height; y++) {
    for (let x=0; x<width; x++) {
      const index = (y*width+x)*4;
      if (!rgba[index+3]) continue;
      const grain = Math.sin(x*127.1+y*311.7)*43758.5453;
      const fibers = Math.sin(x*2.7 + y*(fabric.value === 'long' ? .24 : 1.2));
      const light = (grain-Math.floor(grain)-.5)*texture + fibers*texture*.18 + 9 - y*.027;
      for (let channel=0; channel<3; channel++) rgba[index+channel] += light;
    }
  }
  sketch.putImageData(pixels,0,0);
  const background = ctx.createRadialGradient(315,170,20,340,250,455);
  background.addColorStop(0,'#fff8f2');
  background.addColorStop(1,'#e2d0f7');
  ctx.fillStyle=background;
  ctx.fillRect(0,0,width,height);
  ctx.save();
  ctx.filter='blur(13px)';
  ctx.fillStyle='#4a246747';
  ctx.beginPath();
  ctx.ellipse(340,469,144,16,0,0,Math.PI*2);
  ctx.fill();
  ctx.restore();
  ctx.save();
  ctx.shadowColor='#54264d50';
  ctx.shadowBlur=22;
  ctx.shadowOffsetY=9;
  ctx.drawImage(source,0,0);
  ctx.restore();

  concept = {filename, size:Number(size.value), fabric:fabric.selectedOptions[0].textContent};
  conceptFile = originalFile;
  status.textContent = concept.filename + ' · ' + concept.size + ' см';
}

async function readImage(file) {
  if (!file) return;
  const version = ++loadVersion;
  if (!['image/png','image/jpeg','image/webp'].includes(file.type) || file.size > 10*1024*1024) {
    status.textContent = 'Выберите PNG, JPEG или WebP размером до 10 МБ.';
    return;
  }
  const url = URL.createObjectURL(file);
  try {
    const next = new Image();
    next.src = url;
    await next.decode();
    if (version !== loadVersion) return;
    image = next;
    originalFile = file;
    filename = file.name;
    drawConcept();
  } catch {
    if (version === loadVersion) status.textContent = 'Не удалось открыть изображение. Попробуйте другой файл.';
  } finally {
    URL.revokeObjectURL(url);
  }
}

upload.addEventListener('change', () => {
  readImage(upload.files[0]);
  upload.value = '';
});
const drop = byId('drop');
drop.addEventListener('dragover', event => {
  event.preventDefault();
  drop.classList.add('over');
});
drop.addEventListener('dragleave', () => drop.classList.remove('over'));
drop.addEventListener('drop', event => {
  event.preventDefault();
  drop.classList.remove('over');
  readImage(event.dataTransfer.files[0]);
});
byId('example').addEventListener('click', () => {
  loadVersion++;
  image = null;
  originalFile = null;
  filename = 'Лисёнок — пример';
  drawConcept();
});
byId('render').addEventListener('click', drawConcept);
byId('download').addEventListener('click', () => {
  const link = document.createElement('a');
  link.download = 'igramir-concept.png';
  link.href = canvas.toDataURL();
  link.click();
});

let mode = 'site';
const buttons = document.querySelectorAll('[data-mode]');
function switchMode(selected) {
  mode = selected;
  document.body.classList.toggle('phone', mode !== 'site');
  byId('channel').textContent = mode === 'max' ? 'MAX · Превью мини-приложения' : 'Telegram · Превью мини-приложения';
  buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.mode === mode)));
}
buttons.forEach(button => button.addEventListener('click', () => switchMode(button.dataset.mode)));
const requestedMode = new URLSearchParams(location.search).get('mode');
if (inTelegram) {
  switchMode('telegram');
  document.querySelector('nav').hidden = true;
  byId('channel').textContent = 'Играмир · Telegram';
  byId('request-note').textContent = 'Эскиз, концепт и контакты получит менеджер фабрики.';
  byId('submit-request').textContent = 'Отправить заявку';
  telegram.ready();
  telegram.expand();
} else if (['telegram','max'].includes(requestedMode)) {
  switchMode(requestedMode);
}

byId('quote').addEventListener('click', () => {
  byId('summary').textContent = concept.filename + ' · ' + concept.fabric + ' · ' + concept.size + ' см';
  byId('confirmation').textContent = '';
  dialog.showModal();
});
byId('close').addEventListener('click', () => dialog.close());
byId('request').addEventListener('submit', async event => {
  event.preventDefault();
  const details = Object.fromEntries(new FormData(event.target));
  const submit = byId('submit-request');
  if (submit.disabled) return;
  if (inTelegram) {
    submit.disabled = true;
    byId('confirmation').textContent = 'Отправляем заявку…';
    try {
      const body = new FormData();
      body.set('details', JSON.stringify({details, concept}));
      if (conceptFile) body.set('original', conceptFile);
      const png = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
      if (png) body.set('preview', png, 'concept.png');
      const response = await fetch((window.igramirApiOrigin || '') + '/api/telegram/requests', {
        method: 'POST',
        headers: {'X-Telegram-Init-Data': telegram.initData},
        body
      });
      if (!response.ok) throw new Error('Request failed');
      byId('confirmation').textContent = 'Заявка отправлена. Менеджер свяжется с вами.';
      event.target.reset();
    } catch {
      byId('confirmation').textContent = 'Не удалось отправить заявку. Попробуйте ещё раз.';
    } finally {
      submit.disabled = false;
    }
    return;
  }
  try {
    localStorage.setItem('igramir-demo-request',JSON.stringify({details,concept,mode}));
    byId('confirmation').textContent = 'Демозаявка сохранена на этом устройстве.';
    event.target.reset();
  } catch {
    byId('confirmation').textContent = 'Хранилище браузера недоступно.';
  }
});
drawConcept();
