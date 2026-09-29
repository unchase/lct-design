export type Template={id:string;filename:string;slides:number;patterns:number;colors:string[];fonts:string[]};
export type Finding={id:string;rule:string;message:string;severity:string;status:string;kind:string;slide:number|null;object_id:string|null;box:{x:number;y:number;w:number;h:number}|null;repair:string|null};
export type Slide={number:number;title:string;speaker_notes?:string;source_ids:string[];pattern_id:string;source_slide:number;objects:{id:string;box:{x:number;y:number;w:number;h:number};text:string;role:string}[]};
export type Variant={name:string;width:number;height:number;slides:Slide[];findings:Finding[];warnings:string[];render:{status:string;images:string[];error?:string};seconds:number;files:string[]};
export type Job={id:string;status:string;stage:string;created:number;updated:number;error:string|null;cancelled:boolean;payload:{request:{content:{title:string};template_id:string};parent_id?:string};result:null|{variants:Variant[];mode:string;seconds:number;warnings:string[];template_name:string;inference?:Inference;usage?:Record<string,number>;parent_id?:string;timing?:{preparation_seconds:number;generation_seconds:number;budget_status:string}}};
export async function api<T>(path:string,options?:RequestInit):Promise<T>{
 const r=await fetch('/api'+path,options);if(!r.ok){let message='Не удалось выполнить запрос';try{const d=await r.json();message=typeof d.detail==='string'?d.detail:JSON.stringify(d.detail)}catch{message=r.statusText}throw new Error(message)}return r.json();
}
export function jsonPost<T>(path:string,data:unknown){return api<T>(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})}
export function artifact(job:string,variant:string,file:string){return `/api/jobs/${job}/artifacts/${variant}/${encodeURIComponent(file)}`}

export type ProviderConfig={provider:'custom'|'openrouter';base_url:string;model:string;vision_enabled:boolean;vision_model:string;json_mode:boolean;disable_reasoning:boolean;competition_mode:boolean;model_license:string;model_parameters_b:number;model_card:string;vision_license:string;vision_parameters_b:number;vision_card:string};
export type ProviderState=ProviderConfig&{revision:string;has_key:boolean;ready:boolean;issues:string[]};
export type ProviderBalance={available:boolean;reason?:string;balance?:number|null;total_credits?:number|null;key_limit_remaining?:number|null;key_usage_daily?:number|null};
export type ProviderTest={ok:boolean;message:string;model?:string;vision?:'disabled'|'passed';seconds?:number;usage?:Record<string,unknown>};

export type Inference={calls:{stage:string;model?:string;status:string;usage:Record<string,number>|null}[];audit:{status:string;coverage:{variant:string;slide:number}[];total_slides?:number;error?:string};repair:{status:string;changed_slides?:{variant:string;slide:number}[]};provider:string|null;competition_mode:boolean|null};
