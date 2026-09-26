import { mkdir } from 'node:fs/promises'
import { createServer } from 'node:http'
import { resolve } from 'node:path'
import { expect, test, type Page } from '@playwright/test'

const folder = { id:'qa-folder', parentId:null, name:'Synthetic specimens', description:'Synthetic UI fixtures only', sortOrder:0, itemCount:2, childCount:0, hasChildren:false, trashedAt:null, updatedAt:'2026-09-27T00:00:00Z' }
const sample = { id:'qa-a', publicId:'qa-public-a', displayName:'Synthetic A', description:'Synthetic specimen', folderId:folder.id, caseId:'SYNTHETIC-1', organSite:'Kidney', stain:'H&E', diagnosis:'Synthetic teaching fixture', course:'', tags:['Synthetic'], teachingNote:'', sourceBytes:1024, derivativeBytes:512, state:'ready_private', errorCode:null, createdAt:'2026-09-27T00:00:00Z', updatedAt:'2026-09-27T00:00:00Z', trashedAt:null, thumbnailUrl:null }
const slides = [sample, {...sample,id:'qa-b',publicId:'qa-public-b',displayName:'Synthetic B',caseId:'SYNTHETIC-2'}]
const privateSlide = (item: typeof sample) => ({...item,filename:'synthetic.ome.tiff',metadata:{width:256,height:256,physicalSizeX:0.5},annotationsEnabled:false,tileSource:'/qa/synthetic.dzi'})

async function fixture(page: Page) {
  const tile = Buffer.from(await page.evaluate(() => { const canvas=document.createElement('canvas');canvas.width=256;canvas.height=256;const context=canvas.getContext('2d')!;context.fillStyle='#f4ddc4';context.fillRect(0,0,256,256);context.fillStyle='#b45e4b';context.fillRect(32,32,192,192);context.fillStyle='#f4ddc4';context.font='22px sans-serif';context.fillText('SYNTHETIC',58,135);return canvas.toDataURL('image/png').split(',')[1] }), 'base64')
  const control = { tileRequests:0, reserved:0, renewed:0, resourceCreates:0, patches:0, offset:0, size:0, phase:'uploading', holdPatch:true, discardHeldPatch:false, releasePatch:()=>{}, privateFailures:0 }
  const tusServer=createServer(async(request,response)=>{
    response.setHeader('Access-Control-Allow-Origin','*')
    response.setHeader('Access-Control-Allow-Methods','OPTIONS, POST, HEAD, PATCH')
    response.setHeader('Access-Control-Allow-Headers','Authorization, Content-Type, Tus-Resumable, Upload-Length, Upload-Metadata, Upload-Offset')
    response.setHeader('Access-Control-Expose-Headers','Location, Upload-Offset, Upload-Length, Tus-Resumable')
    response.setHeader('Tus-Resumable','1.0.0')
    response.setHeader('Tus-Version','1.0.0')
    response.setHeader('Tus-Extension','creation')
    if(request.method==='OPTIONS') { response.writeHead(204);response.end();return }
    if(request.method==='POST') { control.resourceCreates++;response.setHeader('Location',`http://${request.headers.host}/uploads/qa-upload`);response.writeHead(201);response.end();return }
    if(request.method==='HEAD') { response.setHeader('Upload-Offset',String(control.offset));response.setHeader('Upload-Length',String(control.size));response.writeHead(200);response.end();return }
    if(request.method==='PATCH') {
      let bytes=0
      try { for await (const chunk of request) bytes+=Buffer.byteLength(chunk) } catch { response.destroy();return }
      control.patches++
      const held=control.patches===2 && control.holdPatch
      if(held) await new Promise<void>(release=>{control.releasePatch=release})
      else await new Promise<void>(release=>setTimeout(release,400))
      if(!(held && control.discardHeldPatch)) control.offset+=bytes
      if(control.offset>=control.size) control.phase='converting'
      response.setHeader('Upload-Offset',String(control.offset));response.writeHead(204);response.end();return
    }
    response.writeHead(404);response.end()
  })
  await new Promise<void>(ready=>tusServer.listen(0,'127.0.0.1',ready))
  const address=tusServer.address()
  if(!address || typeof address==='string') throw new Error('Synthetic TUS server did not bind')
  const uploadUrl=`http://127.0.0.1:${address.port}/uploads/`
  page.on('close',()=>{control.releasePatch();tusServer.closeAllConnections();tusServer.close()})
  await page.route('**/qa/**',route => route.request().url().endsWith('.dzi') ? route.fulfill({contentType:'application/xml',body:'<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" TileSize="256" Overlap="0" Format="png"><Size Width="256" Height="256"/></Image>'}) : (control.tileRequests++, route.fulfill({contentType:'image/png',body:tile})))
  await page.route('**/api/**',async route => {
    const request=route.request(); const url=new URL(request.url()); const path=url.pathname
    if(path==='/api/v2/admin/library/navigation') return route.fulfill({json:{counts:{all:2,unfiled:0,shared:0,processing:0,failed:0,trash:0},folders:[folder],folderPath:[folder],collections:[],savedViews:[],capabilities:{classroom:false,study:false}}})
    if(path==='/api/v2/admin/library/items') return route.fulfill({json:{items:slides,nextCursor:null,total:2}})
    if(path==='/api/v2/admin/slides/status') return route.fulfill({json:{items:slides.map(item=>({id:item.id,state:item.state,errorCode:null}))}})
    if(path.includes('/children')) return route.fulfill({json:[]})
    if(path==='/api/v1/auth/session') return route.fulfill({json:{csrfToken:'synthetic-csrf'}})
    if(path==='/api/v1/admin/slides' && request.method()==='POST') {
      control.reserved++; control.size=request.postDataJSON().length
      return route.fulfill({status:201,json:{slide:{...privateSlide(sample),id:'qa-upload',displayName:'Synthetic upload',state:'uploading',sourceBytes:control.size},uploadUrl,uploadToken:'synthetic-original-grant',expiresIn:3600}})
    }
    if(path==='/api/v1/admin/slides/qa-upload/upload-token') { control.renewed++; return route.fulfill({json:{slide:{...privateSlide(sample),id:'qa-upload',displayName:'Synthetic upload',state:'uploading',sourceBytes:control.size},uploadUrl,uploadToken:'synthetic-renewed-grant',expiresIn:3600}}) }
    if(path==='/api/v1/admin/slides/qa-upload') return route.fulfill({json:{...privateSlide(sample),id:'qa-upload',displayName:'Synthetic upload',state:control.phase,sourceBytes:control.size}})
    const found=slides.find(item=>path.endsWith(`/${item.id}`))
    if(found) {
      if(path.startsWith('/api/v1/') && control.privateFailures-- > 0) return route.fulfill({status:503,json:{detail:{code:'SYNTHETIC_FAILURE'}}})
      return route.fulfill({json:{...privateSlide(found),adminNotes:'Synthetic private note'}})
    }
    return route.fulfill({status:404,json:{detail:{code:'SYNTHETIC_UNMOCKED_ROUTE'}}})
  })
  return control
}
const card = (page:Page,name:string) => page.locator('.library-slide-card').filter({has:page.getByRole('heading',{name,exact:true})})
async function screenshot(page:Page,project:string,name:string) {
  const directory=resolve('../../var/evidence/library-upload-remediation',project)
  await mkdir(directory,{recursive:true})
  await page.evaluate(()=>new Promise<void>(release=>requestAnimationFrame(()=>requestAnimationFrame(()=>release()))))
  await page.screenshot({path:resolve(directory,`${name}.png`),fullPage:false,animations:'disabled'})
}
async function noOverflow(page:Page) { await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true) }
async function touchTargets(page:Page,selector:string) {
  const boxes=await page.locator(selector).evaluateAll(elements=>elements.filter(element=>element.getBoundingClientRect().width>0 && getComputedStyle(element).visibility!=='hidden').map(element=>{const box=element.getBoundingClientRect();return {width:box.width,height:box.height}}))
  expect(boxes.length).toBeGreaterThan(0)
  for(const box of boxes) { expect(box.width).toBeGreaterThanOrEqual(44);expect(box.height).toBeGreaterThanOrEqual(44) }
}

test('library commands, QuickLook, direct preview and adjacent return remain accessible across layouts',async({page},testInfo)=>{
  const control=await fixture(page)
  await page.emulateMedia({reducedMotion:'reduce'})
  await page.goto('/admin?location=folder%3Aqa-folder&q=Synthetic')
  await expect(card(page,'Synthetic A')).toBeVisible()
  for(const viewport of [{width:320,height:740},{width:768,height:1024},{width:900,height:420}]) {
    await page.setViewportSize(viewport)
    for(const theme of ['Light','Dark']) {
      await page.getByRole('radio',{name:theme,exact:true}).check()
      await noOverflow(page)
      await touchTargets(page,'.library-journey-tools button')
      await page.keyboard.press('Tab')
      await card(page,'Synthetic A').focus()
      await expect(card(page,'Synthetic A')).toBeFocused()
      expect(await card(page,'Synthetic A').evaluate(element=>getComputedStyle(element).outlineStyle)).not.toBe('none')
      await screenshot(page,testInfo.project.name,`library-${viewport.width}x${viewport.height}-${theme.toLowerCase()}`)
    }
  }
  await page.keyboard.press('ControlOrMeta+k')
  const command=page.getByRole('dialog',{name:'Search library commands'})
  await expect(command).toBeVisible()
  await expect(page.getByLabel('Slide name, organ, stain, case, or action')).toBeFocused()
  await expect(command.getByRole('button',{name:/Open Classroom|Teach this folder|Open Study Coach/})).toHaveCount(0)
  await page.getByLabel('Slide name, organ, stain, case, or action').fill('SYNTHETIC-2')
  await expect(command.getByRole('button',{name:/Synthetic A/})).toHaveCount(0)
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/admin\/preview\/qa-b$/)
  await page.getByRole('link',{name:'Library',exact:true}).click()
  await expect(card(page,'Synthetic A')).toBeVisible()
  await card(page,'Synthetic A').focus();control.privateFailures=1
  await page.keyboard.press('Space')
  const peek=page.getByRole('dialog',{name:'Quick look: Synthetic A'})
  await expect(peek.getByText(/Preview could not load/)).toBeVisible()
  await peek.getByRole('button',{name:'Retry preview'}).click()
  await expect(peek.locator('.openseadragon-container').first()).toBeVisible()
  await expect.poll(()=>control.tileRequests).toBeGreaterThan(0)
  await noOverflow(page);await screenshot(page,testInfo.project.name,'quicklook-short-landscape')
  await page.keyboard.press('Escape')
  await card(page,'Synthetic A').focus();await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/admin\/preview\/qa-a$/)
  await expect(page.getByRole('button',{name:'Next slide',exact:true})).toBeEnabled()
  await touchTargets(page,'.viewer-adjacent button, .viewer-library-return')
  await noOverflow(page);await screenshot(page,testInfo.project.name,'viewer-short-landscape')
  await page.getByRole('button',{name:'Next slide',exact:true}).click()
  await expect(page).toHaveURL(/\/admin\/preview\/qa-b$/)
  await page.getByRole('link',{name:'Library',exact:true}).click()
  await expect(page).toHaveURL(/location=folder%3Aqa-folder.*q=Synthetic/)
  await expect(page.getByRole('searchbox',{name:'Search slides'})).toHaveValue('Synthetic')
})

test('pending search debounce cannot undo delayed lazy viewer navigation',async({page})=>{
  await fixture(page)
  await page.route('**/src/pages/ViewerPage.tsx*',async route=>{await new Promise<void>(release=>setTimeout(release,850));await route.continue()})
  await page.goto('/admin?location=folder%3Aqa-folder')
  await expect(card(page,'Synthetic A')).toBeVisible()
  await page.getByRole('searchbox',{name:'Search slides'}).fill('pending synthetic query')
  // Dispatch native events together so the navigation begins before the 250 ms timer.
  await card(page,'Synthetic A').evaluate(element=>{element.focus();element.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}))})
  await expect(page).toHaveURL(/\/admin\/preview\/qa-a$/)
  await expect(page.locator('.viewer-title strong')).toHaveText('Synthetic A')
  await expect(page).toHaveURL(/\/admin\/preview\/qa-a$/)
})

test('background transfer survives SPA navigation, pauses and renews its same reservation, then opens only when ready',async({page},testInfo)=>{
  test.setTimeout(100_000)
  const control=await fixture(page)
  await page.goto('/admin?location=folder%3Aqa-folder')
  await expect(card(page,'Synthetic A')).toBeVisible()
  await page.getByRole('navigation',{name:'Library destinations'}).getByRole('button',{name:'Upload',exact:true}).click()
  const upload=page.getByRole('dialog',{name:'Upload OME-TIFF'})
  await upload.getByLabel('Choose OME-TIFF files').setInputFiles({name:'Synthetic upload.ome.tiff',mimeType:'image/tiff',buffer:Buffer.alloc(21*1024*1024,0x53)})
  await upload.getByRole('button',{name:'Upload 1 file',exact:true}).click()
  await expect.poll(()=>control.patches,{timeout:25_000}).toBeGreaterThanOrEqual(2)
  await upload.getByRole('button',{name:'Close Upload OME-TIFF'}).click()
  const dock=page.getByRole('complementary',{name:'Background uploads'})
  await expect(dock).toBeVisible()
  await expect(dock.getByText(/sent.*\/s/)).toBeVisible()
  await card(page,'Synthetic A').getByRole('button',{name:'Open viewer',exact:true}).click()
  await expect(page).toHaveURL(/\/admin\/preview\/qa-a$/)
  await expect(dock).toBeVisible()
  await dock.getByRole('button',{name:'Minimize uploads'}).click()
  await expect(dock.getByText('Synthetic upload',{exact:true})).toHaveCount(0)
  await dock.getByRole('button',{name:'Expand uploads'}).click()
  await dock.getByRole('button',{name:'Pause Synthetic upload'}).click()
  await expect(dock.getByText(/Any upload reservation remains allocated/)).toBeVisible()
  control.discardHeldPatch=true;control.releasePatch()
  await dock.getByRole('button',{name:'Resume transfer'}).click()
  await expect.poll(()=>control.renewed).toBe(1)
  await expect.poll(()=>control.offset,{timeout:25_000}).toBe(control.size)
  await expect(dock.getByText(/Processing: converting/)).toBeVisible()
  await expect(dock.getByRole('link',{name:'Open viewer'})).toHaveCount(0)
  expect(control.reserved).toBe(1);expect(control.resourceCreates).toBe(1)
  control.phase='ready_private'
  await expect(dock.getByRole('link',{name:'Open viewer'})).toBeVisible({timeout:12_000})
  await page.emulateMedia({reducedMotion:'reduce'})
  for(const viewport of [{width:320,height:740},{width:768,height:1024},{width:900,height:420}]) {
    await page.setViewportSize(viewport)
    for(const theme of ['Light','Dark']) {
      await page.getByRole('radio',{name:theme,exact:true}).check()
      await noOverflow(page);await touchTargets(page,'.upload-dock button, .upload-dock a')
      const header=await page.locator('.viewer-header').boundingBox();const stage=await page.locator('.viewer-stage').boundingBox()
      expect(header!.y+header!.height).toBeLessThanOrEqual(stage!.y+1)
      await screenshot(page,testInfo.project.name,`dock-${viewport.width}x${viewport.height}-${theme.toLowerCase()}`)
    }
  }
  await dock.getByRole('link',{name:'Open viewer'}).click()
  await expect(page).toHaveURL(/\/admin\/preview\/qa-upload$/)
  await expect(page.locator('.viewer-title strong')).toHaveText('Synthetic upload')
})


test('residual library controls preserve card targets and real navigation boundaries',async({page},testInfo)=>{
  await fixture(page)
  await page.emulateMedia({reducedMotion:'reduce'})
  const mutations:Array<{path:string,body:Record<string,unknown>}> = []
  await page.route('**/api/v2/admin/slides/batch-metadata',async route=>{
    mutations.push({path:new URL(route.request().url()).pathname,body:route.request().postDataJSON()})
    await route.fulfill({json:{items:[sample]}})
  })
  await page.route('**/api/v2/admin/slides/qa-a/trash',async route=>{
    mutations.push({path:new URL(route.request().url()).pathname,body:{}})
    await route.fulfill({json:{...sample,trashedAt:'2026-09-27T00:00:00Z'}})
  })
  await page.setViewportSize({width:760,height:740})
  await page.goto('/admin')
  await expect(card(page,'Synthetic A')).toBeVisible()
  await expect(page.getByRole('button',{name:'Back',exact:true})).toBeDisabled()
  await expect(page.getByRole('button',{name:'Forward',exact:true})).toBeDisabled()
  await expect(page.getByRole('button',{name:'Up one level'})).toBeDisabled()
  await page.getByRole('button',{name:'Slide library',exact:true}).click()
  await page.getByRole('treeitem',{name:'Synthetic specimens',exact:true}).click()
  await expect(page.getByRole('button',{name:'Back',exact:true})).toBeEnabled()
  await expect(page.getByRole('button',{name:'Forward',exact:true})).toBeDisabled()
  await expect(page.getByRole('button',{name:'Up one level'})).toBeEnabled()
  await page.getByRole('button',{name:'Back',exact:true}).click()
  await expect(page.getByRole('button',{name:'Forward',exact:true})).toBeEnabled()
  await page.getByRole('button',{name:'Forward',exact:true}).click()
  await expect(page).toHaveURL(/location=folder%3Aqa-folder/)
  await page.getByRole('button',{name:'Up one level'}).click()
  await expect(page.getByRole('button',{name:'Up one level'})).toBeDisabled()
  await page.setViewportSize({width:320,height:740})
  await page.getByRole('checkbox',{name:'Select Synthetic B'}).check()
  const closeInspector=async()=>{if(await page.getByRole('button',{name:'Close slide details'}).isVisible())await page.getByRole('button',{name:'Close slide details'}).click()}
  const edit=async()=>{
    await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))))
    await closeInspector()
    await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))))
    await page.getByRole('button',{name:'More actions for Synthetic A'}).click()
    await page.getByRole('menuitem',{name:'Edit details',exact:true}).click()
    return page.getByRole('dialog',{name:'Edit slide details'})
  }
  let dialog=await edit()
  await dialog.getByRole('button',{name:'Close Edit slide details'}).click()
  await expect(page.getByRole('checkbox',{name:'Select Synthetic B'})).toBeChecked()
  await expect(page.getByRole('checkbox',{name:'Select Synthetic A'})).not.toBeChecked()
  dialog=await edit()
  for(const [label,maximum] of [['Display name',200],['Description',4000],['Case ID',120],['Organ / site',120],['Stain',80],['Diagnosis',300],['Course',160],['Teaching note',8000],['Administrator note',16000]] as const){
    const input=dialog.getByRole('textbox',{name:label,exact:true})
    await expect(input).toHaveAttribute('maxlength',String(maximum))
    await input.fill('X'.repeat(maximum+1))
    await expect(input).toHaveValue('X'.repeat(maximum))
  }
  await dialog.getByRole('button',{name:'Save details'}).click()
  await expect.poll(()=>mutations.length).toBe(1)
  expect(mutations[0].body.slideIds).toEqual(['qa-a'])
  expect(mutations[0].body.displayName).toBe('X'.repeat(200))
  await expect(page.getByRole('checkbox',{name:'Select Synthetic B'})).toBeChecked()
  await closeInspector()
  await page.getByRole('button',{name:'More actions for Synthetic A'}).click()
  await page.getByRole('menuitem',{name:/^Move to trash$/i}).click()
  await expect.poll(()=>mutations.length).toBe(2)
  expect(mutations[1].path).toBe('/api/v2/admin/slides/qa-a/trash')
  await expect(page.getByRole('checkbox',{name:'Select Synthetic B'})).toBeChecked()
  await noOverflow(page)
  await screenshot(page,testInfo.project.name,'residual-library-controls')
})
