export let csrf = ''
export function setCsrf(value:string){csrf=value}
export async function api<T=any>(path:string,method='GET',body?:unknown):Promise<T>{
 const headers:Record<string,string>={}
 if(method!=='GET') headers['X-CSRF-Token']=csrf
 if(body && !(body instanceof FormData)) headers['Content-Type']='application/json'
 const response=await fetch('/api'+path,{method,headers,body:body instanceof FormData?body:body?JSON.stringify(body):undefined,credentials:'same-origin'})
 if(!response.ok){const error=await response.json().catch(()=>({detail:'Błąd połączenia'}));throw new Error(typeof error.detail==='string'?error.detail:JSON.stringify(error.detail))}
 return response.json()
}
export function upload(path:string,file:File){const data=new FormData();data.append('file',file);return api(path,'POST',data)}
export async function downloadBlob(path:string,body:unknown,name:string){const r=await fetch('/api'+path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});if(!r.ok)throw new Error((await r.json()).detail);const u=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=u;a.download=name;a.click();URL.revokeObjectURL(u)}
