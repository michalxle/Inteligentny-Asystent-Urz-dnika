export type Question={id:string;text:string;status:string}
export type Case={id:string;reference:string;title:string;applicant:string;received:string;deadline:string;original_deadline:string;answered:string|null;owner:string;status:string;questions:Question[];units:string[];warnings:string[];version:number;delivery:string;days:number|null;state:string;on_time:boolean|null;extension_days:number}
export type Doc={id:string;case_id:string|null;name:string;kind:string;text:string;state:string;active:boolean;version:number;pages:number;has_pdf:boolean;metadata:Record<string,any>;unit_id:string|null}
export type Redaction={start:number;end:number;state:'proposed'|'accepted'|'rejected';category:string;reason:string}
export type Draft={id:string;case_id:string;text:string;coverage:any[];evidence:any[];redactions:Redaction[];version:number;approved_version:number|null;model:string}
export type Unit={id:string;name:string;description:string}
export type Job={id:string;kind:string;target:string;status:string;progress:string;result:any}
export const labels:Record<string,string>={do_weryfikacji:'Do weryfikacji',zarejestrowany:'Brak działań',oczekuje_na_materialy:'Zapytania wysłane do wydziałów',kwerenda:'Kwerenda',projekt_odpowiedzi:'Odpowiedź w przygotowaniu',do_akceptacji:'Do akceptacji',gotowy_do_eksportu:'Odpowiedź przygotowana',zakonczony:'Odpowiedź wysłana'}
/** Etap z liczbą dni przedłużenia przy kwerendzie (art. 13 ust. 2 UDIP). */
export function statusLabel(c:{status:string;extension_days?:number}):string{const base=labels[c.status]||c.status;return c.status==='kwerenda'&&c.extension_days?`${base} +${c.extension_days} dni`:base}
/** Inicjały prowadzącego, np. „Jan Kowalski” → „JK”. */
export function initials(name:string):string{const parts=name.trim().split(/\s+/).filter(Boolean);if(!parts.length)return '—';return parts.length===1?parts[0].slice(0,2).toUpperCase():(parts[0][0]+parts[parts.length-1][0]).toUpperCase()}
