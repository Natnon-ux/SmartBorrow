export default function ({data, parentElement, setTriggerValue}) {
  const root=parentElement.querySelector('.sb-photo-editor');
  const canvas=root.querySelector('.crop-canvas');
  const preview=root.querySelector('.crop-preview');
  const zoomInput=root.querySelector('.crop-zoom');
  const zoomValue=root.querySelector('.crop-zoom-value');
  const save=root.querySelector('.crop-save');
  const reset=root.querySelector('.crop-reset');
  const error=root.querySelector('.crop-error');
  const ctx=canvas.getContext('2d');
  const previewCtx=preview.getContext('2d');
  const picture=new Image();
  const controller=new AbortController();
  const options={signal:controller.signal};
  const size=512;
  let zoom=1, x=0, y=0, pointer=null, ready=false;
  const paint=()=>{
    if (!ready) return;
    const scale=Math.max(size/picture.width,size/picture.height)*zoom;
    const width=picture.width*scale, height=picture.height*scale;
    // Keep the crop fully covered, even when dragging to an edge or zooming out.
    x=Math.max(-(width-size)/2,Math.min((width-size)/2,x));
    y=Math.max(-(height-size)/2,Math.min((height-size)/2,y));
    ctx.clearRect(0,0,size,size);
    ctx.drawImage(picture,(size-width)/2+x,(size-height)/2+y,width,height);
    previewCtx.clearRect(0,0,128,128);
    previewCtx.drawImage(canvas,0,0,128,128);
    zoomValue.value=`${Math.round(zoom*100)}%`;
  };
  picture.onload=()=>{ready=true; save.disabled=false; paint();};
  picture.onerror=()=>{error.hidden=false; error.textContent='โหลดรูปไม่ได้ กรุณาเลือกไฟล์ใหม่';};
  picture.src=data.image;
  zoomInput.addEventListener('input',()=>{zoom=Number(zoomInput.value); paint();},options);
  reset.addEventListener('click',()=>{zoom=1;x=0;y=0;zoomInput.value='1';paint();},options);
  canvas.addEventListener('pointerdown',event=>{
    if (!ready) return;
    event.preventDefault();
    canvas.focus();
    canvas.setPointerCapture(event.pointerId);
    pointer={id:event.pointerId,x:event.clientX,y:event.clientY};
  },options);
  canvas.addEventListener('pointermove',event=>{
    if (!pointer || event.pointerId!==pointer.id) return;
    const ratio=size/canvas.getBoundingClientRect().width;
    x+=(event.clientX-pointer.x)*ratio;
    y+=(event.clientY-pointer.y)*ratio;
    pointer.x=event.clientX;pointer.y=event.clientY;
    paint();
  },options);
  const finish=event=>{
    if (pointer && event.pointerId===pointer.id) {
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
      pointer=null;
    }
  };
  canvas.addEventListener('pointerup',finish,options);
  canvas.addEventListener('pointercancel',finish,options);
  canvas.addEventListener('keydown',event=>{
    const step=event.shiftKey?32:8;
    const moves={ArrowLeft:[-step,0],ArrowRight:[step,0],ArrowUp:[0,-step],ArrowDown:[0,step]};
    if (!moves[event.key]) return;
    event.preventDefault();x+=moves[event.key][0];y+=moves[event.key][1];paint();
  },options);
  save.addEventListener('click',()=>{
    if (!ready || save.disabled) return;
    save.disabled=true;save.textContent='กำลังบันทึก…';
    setTriggerValue('save',{source_token:data.source_token,image:canvas.toDataURL('image/png')});
  },options);
  return ()=>{controller.abort();picture.onload=null;picture.onerror=null;};
}
