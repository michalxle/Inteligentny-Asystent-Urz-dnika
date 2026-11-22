export type Question={id:string;text:string;status:string}
export type Case={id:string;reference:string;title:string;applicant:string;received:string;deadline:string;original_deadline:string;answered:string|null;owner:string;status:string;questions:Question[];units:string[];warnings:string[];version:number;delivery:string;days:number|null;state:string;on_time:boolean|null}
export type Doc={id:string;case_id:string|null;name:string;kind:string;text:string;state:string;active:boolean;version:number;pages:number;has_pdf:boolean;metadata:Record<string,any>;unit_id:string|null}
export type Redaction={start:number;end:number;state:'proposed'|'accepted'|'rejected';category:string;reason:string}
export type Draft={id:string;case_id:string;text:string;coverage:any[];evidence:any[];redactions:Redaction[];version:number;approved_version:number|null;model:string}
export type Unit={id:string;name:string;description:string}
export type Job={id:string;kind:string;target:string;status:string;progress:string;result:any}
export const labels:Record<string,string>={do_weryfikacji:'Do weryfikacji',zarejestrowany:'Zarejestrowany',oczekuje_na_materialy:'Oczekuje na materiały',projekt_odpowiedzi:'Projekt odpowiedzi',do_akceptacji:'Do akceptacji',gotowy_do_eksportu:'Pismo zatwierdzone',zakonczony:'Zakończony'}
