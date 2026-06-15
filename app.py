import os
import re
import zipfile
from io import BytesIO
from typing import List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
import pypdf

app = FastAPI()

def extract_pdf_info(file_bytes: bytes):
    """Вытаскивает любые текстовые паттерны из первых страниц PDF."""
    text = ""
    try:
        reader = pypdf.PdfReader(BytesIO(file_bytes))
        for i in range(min(3, len(reader.pages))):
            page_text = reader.pages[i].extract_text()
            if page_text:
                text += page_text + "\n"
    except Exception:
        pass

    code_match = re.search(r'\b\d{2}\.\d{2}\.\d{2}\b', text)
    code = code_match.group(0) if code_match else "00.00.00"

    year_match = re.search(r'\b(202[0-9]|201[0-9])\b', text)
    year = year_match.group(0) if year_match else "2026"

    doc_type = "Документ"
    text_lower = text.lower()
    if "рабочая программа" in text_lower or "рпд" in text_lower:
        doc_type = "РПД"
    elif "практик" in text_lower:
        doc_type = "Практика"
    elif "фонд оценочных" in text_lower or "фос" in text_lower:
        doc_type = "ФОС"
    elif "аннотация" in text_lower:
        doc_type = "Аннотация"

    practice_type = "Учебная"
    if "преддиплом" in text_lower:
        practice_type = "Преддипломная"
    elif "производствен" in text_lower:
        practice_type = "Производственная"
    elif "научно-исслед" in text_lower or "нир" in text_lower:
        practice_type = "НИР"

    title = "Без_названия"
    title_match = re.search(r'(?:дисциплины|дисциплине|по|название|программа)\s+["«]?([А-Яа-яA-Za-z\s\-,]{3,50})["»]?', text, re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip().replace(" ", "_")
    
    return {
        "тип": doc_type,
        "код": code,
        "год": year,
        "вид": practice_type,
        "название": title
    }

def apply_template(template: str, info: dict) -> str:
    """Заменяет теги {переменная} на данные из PDF."""
    result = template
    for key, value in info.items():
        result = result.replace(f"{{{key}}}", str(value))
    result = re.sub(r'[\\/*?:"<>|]', "", result)
    return result.strip()

@app.get("/logo.png")
async def get_logo():
    if os.path.exists("logo.png"):
        return FileResponse("logo.png")
    return HTTPException(status_code=404, detail="Logo not found")

# --- ВОТ ЭТОТ ЭНДПОИНТ ПРОПАЛ ИЗ Python-ЛОГИКИ ---
@app.post("/api/rename")
async def rename_pdfs(files: List[UploadFile] = File(...), template: str = Form(...)):
    if not files:
        raise HTTPException(status_code=400, detail="Файлы не загружены")
    
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file in files:
            file_bytes = await file.read()
            info = extract_pdf_info(file_bytes)
            new_name = apply_template(template, info) + ".pdf"
            zip_file.writestr(new_name, file_bytes)
            
    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer, 
        media_type="application/zip", 
        headers={"Content-Disposition": "attachment; filename=archive.zip"}
    )

@app.get("/", response_class=HTMLResponse)
async def main_page():
    return """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>PDF Конвертер | Кафедра ИиППО Liquid Glass</title>
        <style>
            :root {
                --primary-blue: #0084ff;
                --primary-black: #0d0d0e;
                /* Смягчаем цвет подложки стекла, делая его более люксовым */
                --glass-bg: rgba(255, 255, 255, 0.55);
                --glass-border: rgba(255, 255, 255, 0.5);
            }

            html, body {
                width: 100%;
                max-width: 100%;
                overflow-x: hidden;
            }

            body {
                font-family: '-apple-system', BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                /* Делаем градиент фона чуть насыщеннее, чтобы стекло «заиграло» как на скриншоте */
                background: radial-gradient(circle at 20% 20%, rgba(0, 132, 255, 0.3) 0%, transparent 40%),
                            radial-gradient(circle at 80% 80%, rgba(0, 132, 255, 0.2) 0%, transparent 50%),
                            linear-gradient(135deg, #eef2f7 0%, #d5dadf 100%);
                background-attachment: fixed;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                padding: 15px;
                box-sizing: border-box;
                position: relative;
            }

            .bg-lines-wrapper {
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                overflow: hidden;
                pointer-events: none;
                z-index: 0;
            }
            .bg-line-1 {
                position: absolute;
                top: -10%;
                left: -10%;
                width: 140%;
                height: 70px;
                background: linear-gradient(90deg, transparent, var(--primary-blue), transparent);
                transform: rotate(-12deg);
                opacity: 0.15;
                filter: blur(6px);
            }
            .bg-line-2 {
                position: absolute;
                top: 50%;
                right: -20%;
                width: 140%;
                height: 35px;
                background: linear-gradient(90deg, transparent, var(--primary-black), transparent);
                transform: rotate(-12deg);
                opacity: 0.1;
                filter: blur(4px);
            }

            .container {
                background: var(--glass-bg);
                /* Увеличиваем размытие до 40px для глубокого эффекта матовости, как на скрине */
                backdrop-filter: blur(40px) saturate(200%);
                -webkit-backdrop-filter: blur(40px) saturate(200%);
                
                /* Тонкая, едва заметная глянцевая грань */
                border: 1px solid var(--glass-border);
                /* Делаем скругление еще более мягким и жидким */
                border-radius: 32px;
                
                /* Перерабатываем тени: 
                   1. Внутренний белый блик по всему периметру (inset 0 0 0 1px)
                   2. Мягкое внутреннее свечение сверху вниз для объема
                   3. Глубокая, очень мягкая и размытая внешняя тень */
                box-shadow: 
                    inset 0 0 0 1px rgba(255, 255, 255, 0.6),
                    inset 0 15px 30px rgba(255, 255, 255, 0.3),
                    0 1px 3px rgba(0, 0, 0, 0.02),
                    0 10px 30px rgba(0, 0, 0, 0.04),
                    0 30px 60px rgba(0, 50, 100, 0.08);

                padding: 45px 35px;
                width: 100%;
                max-width: 500px;
                box-sizing: border-box;
                position: relative;
                z-index: 1;
                transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
            }
            
            /* Эффект легкого отклика при наведении (как у кнопок на панели iOS) */
            .container:hover {
                transform: translateY(-2px);
                box-shadow: 
                    inset 0 0 0 1px rgba(255, 255, 255, 0.7),
                    inset 0 15px 30px rgba(255, 255, 255, 0.35),
                    0 35px 70px rgba(0, 50, 100, 0.12);
            }
            
            .header-block {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 16px;
                margin-bottom: 35px;
            }
            .header-block img {
                height: 52px;
                width: auto;
                object-fit: contain;
                filter: drop-shadow(0 2px 4px rgba(0,0,0,0.05));
            }
            .title-group {
                text-align: left;
            }
            h1 { 
                color: var(--primary-black); 
                margin: 0; 
                font-size: 23px; 
                font-weight: 700;
                letter-spacing: -0.5px;
                line-height: 1.1;
            }
            .subtitle { 
                color: rgba(13, 13, 14, 0.6); 
                margin: 3px 0 0 0; 
                font-size: 11px; 
                text-transform: uppercase;
                letter-spacing: 1.5px;
                font-weight: 700;
            }
            
            /* Делаем внутреннюю зону сброса файлов тоже стеклянной, но чуть глубже */
            .drop-zone {
                border: 1.5px dashed rgba(0, 132, 255, 0.35);
                border-radius: 20px;
                padding: 40px 20px;
                cursor: pointer;
                background: rgba(255, 255, 255, 0.25);
                backdrop-filter: blur(10px);
                -webkit-backdrop-filter: blur(10px);
                transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
                display: flex;
                flex-direction: column;
                align-items: center;
                box-shadow: inset 0 2px 4px rgba(0,0,0,0.01);
            }
            .drop-zone:hover, .drop-zone.dragover {
                background: rgba(255, 255, 255, 0.5);
                border-color: var(--primary-blue);
                box-shadow: 0 10px 25px rgba(0, 132, 255, 0.06);
                transform: translateY(-1px);
            }
            .drop-zone svg {
                stroke: var(--primary-blue);
                margin-bottom: 12px;
                filter: drop-shadow(0 2px 4px rgba(0,132,255,0.15));
            }
            .drop-zone-text {
                font-weight: 600; 
                color: var(--primary-black);
                font-size: 14.5px;
            }
            
            .template-section {
                text-align: left;
                background: rgba(255, 255, 255, 0.2);
                backdrop-filter: blur(10px);
                -webkit-backdrop-filter: blur(10px);
                padding: 22px;
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 0.4);
                margin-top: 25px;
                margin-bottom: 25px;
                box-sizing: border-box;
            }
            .template-section h3 { 
                margin-top: 0; 
                color: var(--primary-black); 
                font-size: 14.5px; 
                font-weight: 600;
                padding-left: 2px;
            }
            label { display: block; font-size: 11px; color: rgba(0,0,0,0.6); margin-bottom: 8px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
            
            input[type="text"] {
                width: 100%;
                padding: 14px;
                background: rgba(255, 255, 255, 0.4);
                border: 1px solid rgba(255, 255, 255, 0.5);
                border-radius: 12px;
                box-sizing: border-box;
                font-family: 'SF Mono', SFMono-Regular, Consolas, monospace;
                font-size: 14px;
                font-weight: 600;
                color: var(--primary-black);
                box-shadow: inset 0 1px 2px rgba(0,0,0,0.02);
                transition: all 0.2s;
            }
            input[type="text"]:focus {
                outline: none;
                background: rgba(255, 255, 255, 0.7);
                border-color: var(--primary-blue);
                box-shadow: 0 0 0 3px rgba(0, 132, 255, 0.12);
            }
            
            .tags-info { font-size: 11.5px; color: rgba(0,0,0,0.6); margin-top: 12px; line-height: 1.5; }
            .tags-list { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }
            .tags-list code { 
                background: rgba(0, 132, 255, 0.08); 
                color: #0066dd;
                padding: 4px 8px; 
                border-radius: 8px; 
                font-size: 11px; 
                font-weight: 600;
            }
            
            button {
                background: linear-gradient(180deg, #2c2c2e 0%, #0f0f10 100%);
                color: white;
                border: 1px solid rgba(0,0,0,0.2);
                padding: 16px 24px;
                font-size: 15px;
                font-weight: 600;
                border-radius: 14px;
                cursor: pointer;
                width: 100%;
                transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.12);
            }
            button:hover:not(:disabled) { 
                background: linear-gradient(180deg, #1e1e20 0%, #000000 100%);
                box-shadow: 0 8px 25px rgba(0, 132, 255, 0.2);
                transform: translateY(-0.5px);
            }
            button:disabled { 
                background: rgba(0, 0, 0, 0.05); 
                color: rgba(0, 0, 0, 0.25); 
                border: none;
                cursor: not-allowed; 
                box-shadow: none; 
            }
            
            #file-list { text-align: left; max-height: 110px; overflow-y: auto; margin-top: 15px; font-size: 12.5px; }
            .file-item { padding: 6px 10px; background: rgba(255, 255, 255, 0.4); border-left: 3px solid var(--primary-blue); border-radius: 0 6px 6px 0; margin-bottom: 4px; color: var(--primary-black); font-weight: 500; }

            @media (max-width: 480px) {
                body { padding: 10px; }
                .container { padding: 35px 20px; border-radius: 26px; }
                .header-block { flex-direction: column; gap: 8px; text-align: center; margin-bottom: 25px; }
                .header-block img { height: 46px; }
                .title-group { text-align: center; }
                h1 { font-size: 20px; }
                .drop-zone { padding: 30px 15px; }
                .drop-zone-text { font-size: 13.5px; }
                .template-section { padding: 18px; border-radius: 16px; }
            }
        </style>
    </head>
    <body>

    <div class="bg-lines-wrapper">
        <div class="bg-line-1"></div>
        <div class="bg-line-2"></div>
    </div>

    <div class="container">
        <div class="header-block">
            <img src="/logo.png" alt="Логотип Кафедры" onerror="this.style.display='none'">
            <div class="title-group">
                <h1>PDF Конвертер</h1>
                <div class="subtitle">Кафедра ИиППО</div>
            </div>
        </div>
        
        <form id="upload-form">
            <div class="drop-zone" id="drop-zone">
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                <div class="drop-zone-text">Выберите PDF-файлы или перетащите</div>
            </div>
            
            <input type="file" id="file-input" multiple accept=".pdf" style="display: none;">
            
            <div id="file-list"></div>

            <div class="template-section">
                <h3>Конструктор шаблона</h3>
                <label for="template-input">Маска переименования:</label>
                <input type="text" id="template-input" name="template" value="{тип}_{код}_{название}_{год}">
                
                <div class="tags-info">
                    Динамические теги:
                    <div class="tags-list">
                        <code>{тип}</code>
                        <code>{код}</code>
                        <code>{название}</code>
                        <code>{вид}</code>
                        <code>{год}</code>
                    </div>
                </div>
            </div>
            
            <button type="submit" id="submit-btn" disabled>Обработать документы (ZIP)</button>
        </form>
    </div>

    <script>
        const dropZone = document.getElementById('drop-zone');
        const fileInput = document.getElementById('file-input');
        const fileList = document.getElementById('file-list');
        const submitBtn = document.getElementById('submit-btn');
        const form = document.getElementById('upload-form');
        let selectedFiles = [];

        dropZone.addEventListener('click', () => fileInput.click());
        dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
        dropZone.addEventListener('drop', (e) => { e.preventDefault(); dropZone.classList.remove('dragover'); handleFiles(e.dataTransfer.files); });
        fileInput.addEventListener('change', (e) => handleFiles(e.target.files));

        function handleFiles(files) {
            const pdfFiles = Array.from(files).filter(file => file.name.toLowerCase().endsWith('.pdf'));
            if(pdfFiles.length > 0) {
                selectedFiles = [...selectedFiles, ...pdfFiles];
                updateInterface();
            }
        }

        function updateInterface() {
            fileList.innerHTML = '';
            selectedFiles.forEach((file, index) => {
                const item = document.createElement('div');
                item.className = 'file-item';
                item.textContent = `${index + 1}. ${file.name}`;
                fileList.appendChild(item);
            });
            submitBtn.disabled = selectedFiles.length === 0;
        }

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (selectedFiles.length === 0) return;

            const formData = new FormData();
            selectedFiles.forEach(file => formData.append('files', file));
            formData.append('template', document.getElementById('template-input').value);

            submitBtn.textContent = 'Сборка архива...';
            submitBtn.disabled = true;

            try {
                const response = await fetch('/api/rename', {
                    method: 'POST',
                    body: formData
                });
                if (!response.ok) throw new Error('Ошибка обработки');

                const blob = await response.blob();
                const downloadUrl = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = downloadUrl;
                a.download = "Архив_кафедры.zip";
                document.body.appendChild(a);
                a.click();
                a.remove();
                
                selectedFiles = [];
                updateInterface();
            } catch (err) {
                alert(err.message);
            } finally {
                submitBtn.textContent = 'Обработать документы (ZIP)';
                submitBtn.disabled = false;
            }
        });
    </script>
    </body>
    </html>
    """