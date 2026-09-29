"""Assemble local review materials; never upload or change remote access."""
import hashlib,json,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    repo=Path(__file__).resolve().parents[1]
    output=repo/'output'
    folder=output/('submission-draft-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))
    folder.mkdir(parents=True)
    def copy(source,dest):
        target=folder/dest;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    for name in ('README.md','QUICKSTART.md','ARCHITECTURE.md','MODELS.md','AUDIT.md','LICENSE'):
        copy(repo/name,Path('documentation')/name)
    for name in ('verification.md','submission.md','openapi.json'):
        copy(repo/'docs'/name,Path('documentation')/'docs'/name)
    matrix=json.loads((output/'acceptance/matrix-final.json').read_text(encoding='utf-8'))
    copy(output/'acceptance/matrix-final.json',Path('evidence/matrix.json'))
    for i,run in enumerate(matrix['runs'],1):
        for variant in run['variants']:
            source=output/'acceptance/jobs'/run['job']/variant['name']
            for name in ('presentation.pptx','source.pdf','presentation.html','speech.md','manifest.json','audit.json'):
                copy(source/name,Path('presentations')/str(i)/variant['name']/name)
    for name in ('solution-draft.pptx','source.pdf','README.md','template-preservation.json'):
        copy(output/'pitch'/name,Path('pitch')/name)
    for name in ('demo.mp4','provenance.json','LICENSE.txt','browser-run.json'):
        copy(output/'unseen'/name,Path('demo')/name)
    version=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).strip())
    if dirty:raise SystemExit('Commit reviewed changes before creating a source snapshot; material copies are local drafts.')
    subprocess.run(['git','archive','--format=zip','--output',str(folder/'source.zip'),'HEAD'],cwd=repo,check=True)
    (folder/'README.md').write_text('''# Форма — локальный пакет для проверки

Статус: ЧЕРНОВИК. Ничего не опубликовано и не отправлено организатору.

- source.zip — код и воспроизводимый запуск (README внутри).
- presentations/ — 9 презентаций: 3 шаблона × 3 варианта, PPTX/PDF/HTML + текст.
- demo/demo.mp4 — реальный end-to-end прогон на публичной PPTX вне dataset.
- pitch/ — 15 слайдов по шаблону ЛЦТ, обязательные исходные 7–11 сохранены.
- documentation/ — архитектура, модели, аудит, API и честный отчёт ограничений.
- evidence/matrix.json — замеры всех трёх вариантов после подготовки.

Режим демонстрации без модели; исходные числа синтетические. Live LLM/VLM,
целевая браузерная матрица и ручное редактирование SmartArt не проверены.
Командные поля питча не заполнены: данные не предоставлены. Официальный
контент-пакет отсутствует. Не выдавать этот пакет за полную конкурсную приёмку.
Правила стоп-кода и доступности ссылок — documentation/docs/submission.md.
''',encoding='utf-8')
    checks={str(p.relative_to(folder)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob('*')) if p.is_file() and p!=folder/'manifest.json'}
    (folder/'manifest.json').write_text(json.dumps({'version':version,'created_utc':datetime.now(timezone.utc).isoformat(),
        'status':'draft','files':checks},ensure_ascii=False,indent=2),encoding='utf-8')
    archive=shutil.make_archive(str(folder),'zip',folder)
    print(archive)

if __name__=='__main__':main()
