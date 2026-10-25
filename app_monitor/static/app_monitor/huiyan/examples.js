/* Example photos use the same upload and inference path as the user's files. */
(() => {
  const grid=document.getElementById('exampleGrid');
  let busy=false;
  fetch('/static/app_monitor/huiyan/examples/manifest.json')
    .then(response=>{if(!response.ok)throw new Error('例图清单加载失败');return response.json();})
    .then(examples=>examples.forEach(example=>{
      const button=document.createElement('button');
      button.type='button';button.className='example-card';button.dataset.example=example.id;
      button.title='载入例图与推荐词表，并开始识别';
      const image=document.createElement('img');image.src=example.url;image.alt=example.title;image.loading='lazy';
      const title=document.createElement('strong');title.textContent=example.title;
      button.append(image,title);grid.append(button);
      button.onclick=async()=>{
        if(busy)return;
        if(!SP.length){toast('模型正在准备，请稍后点击例图');return;}
        busy=true;
        grid.querySelectorAll('button').forEach(b=>b.disabled=true);
        try{
          const response=await fetch(example.original||example.url);
          if(!response.ok)throw new Error('例图读取失败');
          const blob=await response.blob();
          sel.clear();example.targets.forEach(name=>{if(SP.some(s=>s.en.toLowerCase()===name))sel.add(name);});
          curCat='';curPhrase='';cats();chips();list('');
          document.querySelector('.tab[data-t="single"]').click();
          curFile=example.title+(example.original?'.TIF':'.jpg');
          imgFit=true;applyZoom();
          if(example.original)await sendToServer(new File([blob],curFile,{type:'image/tiff'}));
          else show(await toURL(blob));
          $('#conf').value=.05;$('#confN').value='0.05';
          toast('已载入例图与推荐词表，正在识别…');
          await run();
        }catch(error){toast('例图体验失败：'+error.message);}
        finally{busy=false;grid.querySelectorAll('button').forEach(b=>b.disabled=false);}
      };
    }))
    .catch(error=>{grid.textContent=error.message;});
})();
