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

# Эндпоинт для отдачи логотипа, если он лежит в корне проекта
@app.get("/logo.png")
async def get_logo():
    if os.path.exists("logo.png"):
        return FileResponse("logo.png")
    return HTTPException(status_code=404, detail="Logo not found")

@app.get("/", response_class=HTMLResponse)
async def main_page():
    return """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Универсальный PDF Конвертер | Кафедра ИиППО</title>
        <style>
            :root {
                --primary-blue: #0084ff;
                --primary-black: #1a1a1a;
                --bg-gray: #f8f9fa;
                --border-color: #e5e7eb;
            }

            body {
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
                background-color: var(--bg-gray);
                background-image: 
                    linear-gradient(135deg, rgba(0, 132, 255, 0.06) 25%, transparent 25%),
                    linear-gradient(225deg, rgba(0, 132, 255, 0.04) 25%, transparent 25%),
                    linear-gradient(45deg, rgba(26, 26, 26, 0.02) 25%, transparent 25%);
                background-size: 400px 400px;
                background-position: 0 0, 200px 0, 200px 200px;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                padding: 20px;
                box-sizing: border-box;
                position: relative;
                overflow-x: hidden;
            }

            /* Те самые декоративные полосы наискосок на бэкграунде */
            body::before {
                content: "";
                position: absolute;
                top: -10%;
                left: -5%;
                width: 150%;
                height: 30px;
                background: linear-gradient(90deg, transparent, var(--primary-blue), transparent);
                transform: rotate(-15deg);
                opacity: 0.15;
                z-index: 0;
                pointer-events: none;
            }
            body::after {
                content: "";
                position: absolute;
                top: 40%;
                right: -10%;
                width: 120%;
                height: 15px;
                background: linear-gradient(90deg, transparent, var(--primary-black), transparent);
                transform: rotate(-15deg);
                opacity: 0.08;
                z-index: 0;
                pointer-events: none;
            }

            .container {
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.06);
                border-top: 6px solid var(--primary-blue);
                width: 100%;
                max-width: 580px;
                text-align: center;
                position: relative;
                z-index: 1;
            }
            
            .header-block {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 15px;
                margin-bottom: 25px;
            }
            .header-block img {
                height: 55px;
                width: auto;
                object-fit: contain;
            }
            .title-group {
                text-align: left;
            }
            h1 { 
                color: var(--primary-black); 
                margin: 0; 
                font-size: 22px; 
                font-weight: 700;
                letter-spacing: -0.5px;
            }
            .subtitle { 
                color: #6b7280; 
                margin: 2px 0 0 0; 
                font-size: 13px; 
                text-transform: uppercase;
                letter-spacing: 1px;
                font-weight: 600;
            }
            
            .drop-zone {
                border: 2px dashed #cbd5e1;
                border-radius: 10px;
                padding: 35px 20px;
                cursor: pointer;
                background-color: #fff;
                transition: all 0.2s ease;
                margin-bottom: 25px;
                display: flex;
                flex-direction: column;
                align-items: center;
            }
            .drop-zone:hover, .drop-zone.dragover {
                background-color: rgba(0, 132, 255, 0.02);
                border-color: var(--primary-blue);
            }
            .drop-zone svg {
                stroke: var(--primary-blue);
                margin-bottom: 12px;
            }
            
            .template-section {
                text-align: left;
                background: #fafafa;
                padding: 22px;
                border-radius: 10px;
                border: 1px solid var(--border-color);
                margin-bottom: 25px;
            }
            .template-section h3 { 
                margin-top: 0; 
                color: var(--primary-black); 
                font-size: 15px; 
                font-weight: 600;
                border-left: 3px solid var(--primary-black);
                padding-left: 8px;
            }
            label { display: block; font-size: 12px; color: #4b5563; margin-bottom: 6px; font-weight: 600; }
            
            input[type="text"] {
                width: 100%;
                padding: 12px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                box-sizing: border-box;
                font-family: 'Courier New', Courier, monospace;
                font-size: 15px;
                font-weight: 600;
                color: var(--primary-black);
                transition: border 0.2s;
            }
            input[type="text"]:focus {
                outline: none;
                border-color: var(--primary-blue);
            }
            
            .tags-info { font-size: 12px; color: #4b5563; margin-top: 12px; line-height: 1.6; }
            .tags-list { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; }
            .tags-list code { 
                background: #e1f0ff; 
                color: #0066cc;
                padding: 3px 6px; 
                border-radius: 4px; 
                font-size: 11px; 
                font-weight: 600;
            }
            
            button {
                background-color: var(--primary-black);
                color: white;
                border: none;
                padding: 15px 28px;
                font-size: 15px;
                font-weight: 600;
                border-radius: 6px;
                cursor: pointer;
                width: 100%;
                transition: all 0.2s;
                letter-spacing: 0.3px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            }
            button:hover { 
                background-color: var(--primary-blue);
                box-shadow: 0 4px 12px rgba(0, 132, 255, 0.3);
            }
            button:disabled { background-color: #cbd5e1; color: #94a3b8; cursor: not-allowed; box-shadow: none; }
            
            #file-list { text-align: left; max-height: 120px; overflow-y: auto; margin-bottom: 20px; font-size: 13px; }
            .file-item { padding: 6px 10px; background: #f1f5f9; border-left: 3px solid var(--primary-blue); border-radius: 0 4px 4px 0; margin-bottom: 4px; color: var(--primary-black); }
        </style>
    </head>
    <body>

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
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                <div style="font-weight:600; color: var(--primary-black);">Выберите файлы или перетащите их сюда</div>
                <div style="font-size:12px; color:#94a3b8; margin-top:4px;">Доступно для любых вузовских PDF документов</div>
            </div>
            
            <input type="file" id="file-input" multiple accept=".pdf" style="display: none;">
            
            <div id="file-list"></div>

            <div class="template-section">
                <h3>Конструктор шаблона имен</h3>
                <label for="template-input">Задайте маску переименования:</label>
                <input type="text" id="template-input" name="template" value="{тип}_{код}_{название}_{год}">
                
                <div class="tags-info">
                    Доступные динамические теги:
                    <div class="tags-list">
                        <code>{тип}</code>
                        <code>{код}</code>
                        <code>{название}</code>
                        <code>{вид}</code>
                        <code>{год}</code>
                    </div>
                </div>
            </div>
            
            <button type="submit" id="submit-btn" disabled>Запустить обработку (ZIP)</button>
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

            submitBtn.textContent = 'Обработка...';
            submitBtn.disabled = true;

            try {
                const response = await fetch('/api/rename', {
                    method: 'POST',
                    body: formData
                });
                if (!response.ok) throw new Error('Ошибка при разборе PDF');

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
                submitBtn.textContent = 'Запустить обработку (ZIP)';
                submitBtn.disabled = false;
            }
        });
    </script>
    </body>
    </html>
    """

@app.post("/api/rename")
async def rename_files(
    files: List[UploadFile] = File(...),
    template: str = Form("{тип}_{код}_{название}_{год}")
):
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
        headers={"Content-Disposition": "attachment; filename=renamed_files.zip"}
    )