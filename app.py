import os
import re
import zipfile
from io import BytesIO
from typing import List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
import pypdf

app = FastAPI()

def extract_pdf_info(file_bytes: bytes):
    """Вытаскивает ключевые данные из первых страниц PDF."""
    text = ""
    try:
        reader = pypdf.PdfReader(BytesIO(file_bytes))
        # Читаем первые 3 страницы для надежности
        for i in range(min(3, len(reader.pages))):
            page_text = reader.pages[i].extract_text()
            if page_text:
                text += page_text + "\n"
    except Exception:
        pass

    # 1. Ищем код направления (например, 09.03.04 или 09.04.01)
    code_match = re.search(r'\b\d{2}\.\d{2}\.\d{2}\b', text)
    code = code_match.group(0) if code_match else "00.00.00"

    # 2. Ищем год (4 цифры, обычно внизу или в шапке)
    year_match = re.search(r'\b(202[0-9]|201[0-9])\b', text)
    year = year_match.group(0) if year_match else "2026"

    # 3. Определяем тип документа и вид практики
    doc_type = "РПД"
    practice_type = "Учебная"
    
    if "практик" in text.lower() or "производствен" in text.lower() or "учебн" in text.lower():
        doc_type = "Практика"
        if "преддиплом" in text.lower():
            practice_type = "Преддипломная"
        elif "производствен" in text.lower():
            practice_type = "Производственная"
        elif "научно-исслед" in text.lower() or "нир" in text.lower():
            practice_type = "НИР"

    # 4. Пробуем вытащить название дисциплины (ищем строки после слов Дисциплина/Блок/РПД по)
    title = "Неизвестная_дисциплина"
    title_match = re.search(r'(?:дисциплины|дисциплине|по|название)\s+["«]?([А-Яа-яA-Za-z\s\-,]{3,50})["»]?', text, re.IGNORECASE)
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
    """Заменяет теги {переменная} в шаблоне на реальные данные."""
    result = template
    for key, value in info.items():
        result = result.replace(f"{{{key}}}", str(value))
    # Удаляем запрещенные в именах файлов символы
    result = re.sub(r'[\\/*?:"<>|]', "", result)
    return result.strip()

@app.get("/", response_class=HTMLResponse)
async def main_page():
    return """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Конвертер названий РПД и практик</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f4f6f9;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                padding: 20px;
                box-sizing: border-box;
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 8px 24px rgba(0,0,0,0.05);
                width: 100%;
                max-width: 600px;
                text-align: center;
            }
            h1 { color: #2c3e50; margin-bottom: 10px; font-size: 24px; }
            p { color: #7f8c8d; margin-bottom: 30px; font-size: 14px; }
            
            .drop-zone {
                border: 2px dashed #3498db;
                border-radius: 8px;
                padding: 40px 20px;
                cursor: pointer;
                background-color: #fcfdfe;
                transition: all 0.3s ease;
                margin-bottom: 25px;
            }
            .drop-zone:hover, .drop-zone.dragover {
                background-color: #ebf5fb;
                border-color: #2980b9;
            }
            .drop-zone img { width: 50px; opacity: 0.6; margin-bottom: 15px; }
            
            .template-section {
                text-align: left;
                background: #f8fafc;
                padding: 20px;
                border-radius: 8px;
                border: 1px solid #e2e8f0;
                margin-bottom: 25px;
            }
            .template-section h3 { margin-top: 0; color: #334155; font-size: 16px; }
            .template-group { margin-bottom: 15px; }
            .template-group:last-child { margin-bottom: 0; }
            label { display: block; font-size: 13px; color: #64748b; margin-bottom: 5px; font-weight: 600; }
            input[type="text"] {
                width: 100%;
                padding: 10px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                box-sizing: border-box;
                font-family: monospace;
                font-size: 14px;
            }
            .tags-info { font-size: 11px; color: #94a3b8; margin-top: 5px; }
            
            button {
                background-color: #2ecc71;
                color: white;
                border: none;
                padding: 14px 28px;
                font-size: 16px;
                font-weight: bold;
                border-radius: 6px;
                cursor: pointer;
                width: 100%;
                transition: background 0.2s;
            }
            button:hover { background-color: #27ae60; }
            button:disabled { background-color: #bdc3c7; cursor: not-allowed; }
            
            #file-list { text-align: left; max-height: 150px; overflow-y: auto; margin-bottom: 20px; font-size: 13px; color: #2c3e50; }
            .file-item { padding: 4px 8px; background: #f1f5f9; border-radius: 4px; margin-bottom: 4px; }
        </style>
    </head>
    <body>

    <div class="container">
        <h1>Конвертер названий РПД и практик</h1>
        <p>Перетащите файлы .pdf для автоматического переименования</p>
        
        <form id="upload-form">
            <div class="drop-zone" id="drop-zone">
                <svg width="50" height="50" viewBox="0 0 24 24" fill="none" stroke="#3498db" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom:10px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                <div style="font-weight:500; color:#34495e;">Выберите файлы или перетащите их сюда</div>
                <div style="font-size:12px; color:#bdc3c7; margin-top:5px;">Поддерживаются только документы .pdf</div>
            </div>
            
            <input type="file" id="file-input" multiple accept=".pdf" style="display: none;">
            
            <div id="file-list"></div>

            <div class="template-section">
                <h3>Настройка шаблонов имен</h3>
                <div class="template-group">
                    <label for="template-rpd">Шаблон для РПД:</label>
                    <input type="text" id="template-rpd" name="template_rpd" value="{тип}_{код}_{название}_{год}">
                </div>
                <div class="template-group">
                    <label for="template-prakt">Шаблон для Практик:</label>
                    <input type="text" id="template-prakt" name="template_prakt" value="Практика_{вид}_{код}_{год}">
                </div>
                <div class="tags-info">
                    Доступные теги: <code>{тип}</code>, <code>{код}</code>, <code>{название}</code>, <code>{вид}</code>, <code>{год}</code>
                </div>
            </div>
            
            <button type="submit" id="submit-btn" disabled>Переименовать и скачать ZIP</button>
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

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });

        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            handleFiles(e.dataTransfer.files);
        });

        fileInput.addEventListener('change', (e) => {
            handleFiles(e.target.files);
        });

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
            formData.append('template_rpd', document.getElementById('template-rpd').value);
            formData.append('template_prakt', document.getElementById('template-prakt').value);

            submitBtn.textContent = 'Обработка...';
            submitBtn.disabled = true;

            try {
                const response = await fetch('/api/rename', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) throw new Error('Ошибка при обработке файлов');

                const blob = await response.blob();
                const downloadUrl = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = downloadUrl;
                a.download = "Переименованные_документы.zip";
                document.body.appendChild(a);
                a.click();
                a.remove();
                
                // Сброс формы после успеха
                selectedFiles = [];
                updateInterface();
            } catch (err) {
                alert(err.message);
            } finally {
                submitBtn.textContent = 'Переименовать и скачать ZIP';
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
    template_rpd: str = Form("{тип}_{код}_{название}_{год}"),
    template_prakt: str = Form("Практика_{вид}_{код}_{год}")
):
    zip_buffer = BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file in files:
            file_bytes = await file.read()
            
            # Извлекаем метаданные из контента PDF
            info = extract_pdf_info(file_bytes)
            
            # Выбираем нужный шаблон в зависимости от типа дока
            chosen_template = template_prakt if info["тип"] == "Практика" else template_rpd
            
            # Формируем новое имя
            new_name = apply_template(chosen_template, info) + ".pdf"
            
            # Записываем файл в zip-архив с новым именем
            zip_file.writestr(new_name, file_bytes)
            
    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=renamed_files.zip"}
    )