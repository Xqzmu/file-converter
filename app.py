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
        <title>PDF Конвертер | Кафедра ИиППО Liquid Glass</title>
        <style>
            :root {
                --primary-blue: #0084ff;
                --primary-black: #0d0d0e;
                --glass-bg: rgba(255, 255, 255, 0.45);
                --glass-border: rgba(255, 255, 255, 0.4);
            }

            html, body {
                width: 100%;
                max-width: 100%;
                overflow-x: hidden;
            }

            body {
                font-family: '-apple-system', BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                /* Жидкий глубокий фон в цветах кафедры, подсвечивающий стекло */
                background: radial-gradient(circle at 15% 15%, rgba(0, 132, 255, 0.25) 0%, transparent 35%),
                            radial-gradient(circle at 85% 85%, rgba(0, 132, 255, 0.15) 0%, transparent 45%),
                            linear-gradient(135deg, #eef2f7 0%, #dcdfe4 100%);
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

            /* Фирменные косые полосы, запрятанные «вглубь» за стекло */
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
                height: 60px;
                background: linear-gradient(90deg, transparent, var(--primary-blue), transparent);
                transform: rotate(-12deg);
                opacity: 0.12;
                filter: blur(4px);
            }
            .bg-line-2 {
                position: absolute;
                top: 45%;
                right: -20%;
                width: 140%;
                height: 25px;
                background: linear-gradient(90deg, transparent, var(--primary-black), transparent);
                transform: rotate(-12deg);
                opacity: 0.08;
                filter: blur(2px);
            }

            .container {
                /* Эффект Liquid Glass */
                background: var(--glass-bg);
                backdrop-filter: blur(30px) saturate(190%);
                -webkit-backdrop-filter: blur(30px) saturate(190%);
                
                /* Тонкий глянцевый край стеклянной панели */
                border: 1px solid var(--glass-border);
                border-radius: 24px;
                
                /* Сложные тени: внутренний сильный блик сверху + объемная мягкая тень */
                box-shadow: 
                    inset 0 1.5px 1.5px rgba(255, 255, 255, 0.7),
                    inset 0 12px 24px rgba(255, 255, 255, 0.25),
                    0 4px 10px rgba(0, 0, 0, 0.02),
                    0 20px 50px rgba(0, 84, 160, 0.12);

                padding: 40px 30px;
                width: 100%;
                max-width: 520px;
                box-sizing: border-box;
                position: relative;
                z-index: 1;
                transition: transform 0.3s ease;
            }
            
            .header-block {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 16px;
                margin-bottom: 30px;
            }
            .header-block img {
                height: 52px;
                width: auto;
                object-fit: contain;
                /* Небольшой эффект отражения на логотипе */
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
            
            .drop-zone {
                border: 1.5px dashed rgba(0, 132, 255, 0.4);
                border-radius: 16px;
                padding: 35px 20px;
                cursor: pointer;
                background: rgba(255, 255, 255, 0.35);
                transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
                display: flex;
                flex-direction: column;
                align-items: center;
                box-shadow: inset 0 2px 4px rgba(0,0,0,0.02);
            }
            .drop-zone:hover, .drop-zone.dragover {
                background: rgba(255, 255, 255, 0.6);
                border-color: var(--primary-blue);
                box-shadow: 0 8px 20px rgba(0, 132, 255, 0.08);
                transform: translateY(-1px);
            }
            .drop-zone svg {
                stroke: var(--primary-blue);
                margin-bottom: 12px;
                filter: drop-shadow(0 2px 4px rgba(0,132,255,0.2));
            }
            .drop-zone-text {
                font-weight: 600; 
                color: var(--primary-black);
                font-size: 14.5px;
            }
            
            .template-section {
                text-align: left;
                background: rgba(255, 255, 255, 0.3);
                padding: 20px;
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 0.5);
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
            label { display: block; font-size: 11px; color: rgba(0,0,0,0.6); margin-bottom: 7px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
            
            input[type="text"] {
                width: 100%;
                padding: 13px;
                background: rgba(255, 255, 255, 0.5);
                border: 1px solid rgba(255, 255, 255, 0.6);
                border-radius: 10px;
                box-sizing: border-box;
                font-family: 'SF Mono', SFMono-Regular, Consolas, monospace;
                font-size: 14px;
                font-weight: 600;
                color: var(--primary-black);
                box-shadow: inset 0 1px 2px rgba(0,0,0,0.03);
                transition: all 0.2s;
            }
            input[type="text"]:focus {
                outline: none;
                background: rgba(255, 255, 255, 0.8);
                border-color: var(--primary-blue);
                box-shadow: 0 0 0 3px rgba(0, 132, 255, 0.15);
            }
            
            .tags-info { font-size: 11.5px; color: rgba(0,0,0,0.6); margin-top: 12px; line-height: 1.5; }
            .tags-list { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 5px; }
            .tags-list code { 
                background: rgba(0, 132, 255, 0.1); 
                color: #0066dd;
                padding: 3px 6px; 
                border-radius: 6px; 
                font-size: 11px; 
                font-weight: 600;
            }
            
            button {
                background: linear-gradient(180deg, #242426 0%, #0d0d0e 100%);
                color: white;
                border: 1px solid rgba(0,0,0,0.1);
                padding: 16px 24px;
                font-size: 15px;
                font-weight: 600;
                border-radius: 12px;
                cursor: pointer;
                width: 100%;
                transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            }
            button:hover:not(:disabled) { 
                background: linear-gradient(180deg, #1a1a1c 0%, #000000 100%);
                box-shadow: 0 6px 20px rgba(0, 132, 255, 0.25);
                transform: translateY(-0.5px);
            }
            button:disabled { 
                background: rgba(0, 0, 0, 0.08); 
                color: rgba(0, 0, 0, 0.3); 
                border: none;
                cursor: not-allowed; 
                box-shadow: none; 
            }
            
            #file-list { text-align: left; max-height: 110px; overflow-y: auto; margin-top: 15px; font-size: 12.5px; }
            .file-item { padding: 6px 10px; background: rgba(255, 255, 255, 0.5); border-left: 3px solid var(--primary-blue); border-radius: 0 6px 6px 0; margin-bottom: 4px; color: var(--primary-black); font-weight: 500; }

            @media (max-width: 480px) {
                body { padding: 10px; }
                .container { padding: 30px 18px; border-radius: 20px; }
                .header-block { flex-direction: column; gap: 8px; text-align: center; margin-bottom: 25px; }
                .header-block img { height: 46px; }
                .title-group { text-align: center; }
                h1 { font-size: 20px; }
                .drop-zone { padding: 25px 15px; }
                .drop-zone-text { font-size: 13.5px; }
                .template-section { padding: 15px; border-radius: 12px; }
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