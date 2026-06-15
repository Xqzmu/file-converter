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

@app.get("/", response_class=HTMLResponse)
async def main_page():
    return """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Универсальный PDF Конвертер | Кафедра ИиППО</title>
        <style>
            :root {
                --primary-blue: #0084ff;
                --primary-black: #1a1a1a;
                --bg-gray: #f8f9fa;
                --border-color: #e5e7eb;
            }

            html, body {
                width: 100%;
                max-width: 100%;
                overflow-x: hidden; /* Запрещаем горизонтальный скролл на мобилках */
            }

            body {
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
                background-color: var(--bg-gray);
                background-image: 
                    linear-gradient(135deg, rgba(0, 132, 255, 0.04) 25%, transparent 25%),
                    linear-gradient(225deg, rgba(0, 132, 255, 0.03) 25%, transparent 25%),
                    linear-gradient(45deg, rgba(26, 26, 26, 0.01) 25%, transparent 25%);
                background-size: 400px 400px;
                background-position: 0 0, 200px 0, 200px 200px;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                padding: 15px;
                box-sizing: border-box;
                position: relative;
            }

            /* Контейнер для декоративных полос, чтобы они не ломали ширину экрана */
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
                top: -5%;
                left: -10%;
                width: 140%;
                height: 30px;
                background: linear-gradient(90deg, transparent, var(--primary-blue), transparent);
                transform: rotate(-15deg);
                opacity: 0.15;
            }
            .bg-line-2 {
                position: absolute;
                top: 35%;
                right: -20%;
                width: 140%;
                height: 15px;
                background: linear-gradient(90deg, transparent, var(--primary-black), transparent);
                transform: rotate(-15deg);
                opacity: 0.08;
            }

            .container {
                background: white;
                padding: 35px 25px;
                border-radius: 16px;
                box-shadow: 0 15px 35px rgba(0,0,0,0.05);
                border-top: 6px solid var(--primary-blue);
                width: 100%;
                max-width: 540px;
                box-sizing: border-box;
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
                height: 50px;
                width: auto;
                object-fit: contain;
            }
            .title-group {
                text-align: left;
            }
            h1 { 
                color: var(--primary-black); 
                margin: 0; 
                font-size: 20px; 
                font-weight: 700;
                letter-spacing: -0.5px;
                line-height: 1.2;
            }
            .subtitle { 
                color: #6b7280; 
                margin: 2px 0 0 0; 
                font-size: 11px; 
                text-transform: uppercase;
                letter-spacing: 1px;
                font-weight: 600;
            }
            
            .drop-zone {
                border: 2px dashed #cbd5e1;
                border-radius: 10px;
                padding: 30px 15px;
                cursor: pointer;
                background-color: #fff;
                transition: all 0.2s ease;
                margin-bottom: 20px;
                display: flex;
                flex-direction: column;
                align-items: center;
            }
            .drop-zone:hover, .drop-zone.dragover {
                background-color: rgba(0, 132, 255, 0.01);
                border-color: var(--primary-blue);
            }
            .drop-zone svg {
                stroke: var(--primary-blue);
                margin-bottom: 10px;
            }
            .drop-zone-text {
                font-weight: 600; 
                color: var(--primary-black);
                font-size: 14px;
                text-align: center;
            }
            
            .template-section {
                text-align: left;
                background: #fafafa;
                padding: 18px;
                border-radius: 10px;
                border: 1px solid var(--border-color);
                margin-bottom: 20px;
                box-sizing: border-box;
            }
            .template-section h3 { 
                margin-top: 0; 
                color: var(--primary-black); 
                font-size: 14px; 
                font-weight: 600;
                border-left: 3px solid var(--primary-black);
                padding-left: 8px;
            }
            label { display: block; font-size: 11px; color: #4b5563; margin-bottom: 6px; font-weight: 600; }
            
            input[type="text"] {
                width: 100%;
                padding: 11px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                box-sizing: border-box;
                font-family: 'Courier New', Courier, monospace;
                font-size: 14px;
                font-weight: 600;
                color: var(--primary-black);
            }
            
            .tags-info { font-size: 11px; color: #4b5563; margin-top: 10px; line-height: 1.5; }
            .tags-list { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; }
            .tags-list code { 
                background: #e1f0ff; 
                color: #0066cc;
                padding: 2px 5px; 
                border-radius: 4px; 
                font-size: 11px; 
                font-weight: 600;
            }
            
            button {
                background-color: var(--primary-black);
                color: white;
                border: none;
                padding: 14px 20px;
                font-size: 14px;
                font-weight: 600;
                border-radius: 6px;
                cursor: pointer;
                width: 100%;
                transition: all 0.2s;
                box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            }
            button:hover { 
                background-color: var(--primary-blue);
            }
            button:disabled { background-color: #cbd5e1; color: #94a3b8; cursor: not-allowed; box-shadow: none; }
            
            #file-list { text-align: left; max-height: 100px; overflow-y: auto; margin-bottom: 15px; font-size: 12px; }
            .file-item { padding: 5px 8px; background: #f1f5f9; border-left: 3px solid var(--primary-blue); border-radius: 0 4px 4px 0; margin-bottom: 4px; color: var(--primary-black); }

            /* Адаптивные медиа-запросы для мобильных телефонов */
            @media (max-width: 480px) {
                body {
                    padding: 10px;
                }
                .container {
                    padding: 25px 15px;
                    border-radius: 12px;
                }
                .header-block {
                    flex-direction: column;
                    gap: 8px;
                    text-align: center;
                }
                .header-block img {
                    height: 45px;
                }
                .title-group {
                    text-align: center;
                }
                h1 {
                    font-size: 18px;
                }
                .drop-zone {
                    padding: 20px 10px;
                }
                .drop-zone-text {
                    font-size: 13px;
                }
                input[type="text"] {
                    font-size: 13px;
                    padding: 9px;
                }
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
                <svg width="35" height="35" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                <div class="drop-zone-text">Выберите файлы или перетащите их</div>
                <div style="font-size:11px; color:#94a3b8; margin-top:4px; text-align:center;">Поддерживаются любые PDF документы</div>
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