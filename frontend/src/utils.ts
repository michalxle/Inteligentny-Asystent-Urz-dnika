/** Python stores text spans as Unicode code points, JavaScript string offsets use UTF-16. */
export function textRange(text:string,phrase:string):{start:number;end:number}|null{
 if(!phrase)return null
 const index=text.indexOf(phrase)
 if(index<0)return null
 const start=Array.from(text.slice(0,index)).length
 return {start,end:start+Array.from(phrase).length}
}

/** Registry years follow the receipt date, independently of the reference format. */
export function caseYear(c:{received:string}):string{return c.received.slice(0,4)}
