import os
import re
import zipfile
from io import BytesIO
from typing import List

import easyocr
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
import fitz  # Из пакета PyMuPDF
import numpy as np
import pypdf

app = FastAPI()

try:
    # Если на сервере или локально нет GPU, False принудительно запускает на CPU
    reader = easyocr.Reader(['ru', 'en'], gpu=False)
except Exception:
    reader = None

def extract_text_from_pure_scan(file_bytes: bytes) -> str:
    if reader is None:
        return ""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        if len(doc) == 0:
            return ""
        
        ocr_pages_text = []
        # Проходимся максимум по первым 3 страницам скана, если они перепутаны
        for i in range(min(3, len(doc))):
            page = doc[i]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            ocr_result = reader.readtext(img_bytes, detail=0)
            if ocr_result:
                ocr_pages_text.append("\n".join(ocr_result))
                
        return "\n--- PAGE_BREAK ---\n".join(ocr_pages_text)
    except Exception as e:
        print(f"Ошибка OCR распознавания: {e}")
        return ""

def clean_title(title_str: str) -> str:
    """Вспомогательная функция для чистки названий от мусора и переносов строк"""
    if not title_str:
        return ""
    # Заменяем переносы строк и множественные пробелы на одно нижнее подчеркивание
    title_str = re.sub(r'\s+', '_', title_str)
    # Вычищаем запрещенные в путях символы
    title_str = re.sub(r'[\\/*?:"<>|]', "", title_str)
    return title_str.strip().strip('_')

def extract_pdf_info(file_bytes: bytes):
    # Читаем весь текст из PDF, чтобы найти титульный лист, где бы он ни был
    all_pages_text = []
    try:
        pdf_reader = pypdf.PdfReader(BytesIO(file_bytes))
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                all_pages_text.append(page_text)
    except Exception:
        pass

    # Если pypdf не справился или текст слишком короткий, распознаем как скан
    if not all_pages_text or len("".join(all_pages_text).strip()) < 15:
        pure_scan_text = extract_text_from_pure_scan(file_bytes)
        if pure_scan_text:
            all_pages_text = [pure_scan_text]

    full_document_text = "\n".join(all_pages_text)
    
    # ЛОГИКА НАХОЖДЕНИЯ ТИТУЛЬНОГО ЛИСТА / ГЛАВНОГО ЛИСТА
    target_text = full_document_text
    university_markers = ["минобрнауки", "университет", "институт", "кафедра", "мирэа", "бюджетное", "заключение"]
    for page_text in all_pages_text:
        page_lower = page_text.lower()
        matches = sum(1 for marker in university_markers if marker in page_lower)
        if matches >= 2:
            target_text = page_text
            break

    # НОРМАЛИЗАЦИЯ: Убираем избыточные пробелы между буквами (схлопываем "З А К Л Ю Ч Е Н И Е")
    normalized_text = re.sub(r'(?<=[А-Яа-яЁё])\s+(?=[А-Яа-яЁё]\b)', '', target_text)
    text_lower = normalized_text.lower()
    full_text_lower_global = re.sub(r'(?<=[А-Яа-яЁё])\s+(?=[А-Яа-яЁё]\b)', '', full_document_text).lower()

    # 1. УЛУЧШЕННЫЙ ПОИСК КОДА НАПРАВЛЕНИЯ
    code = None
    # А. Ищем стандартный формат XX.XX.XX
    code_match = re.search(r'\b\d{2}\.\d{2}\.\d{2}\b', normalized_text)
    if code_match:
        code = code_match.group(0)
    else:
        # Б. Ищем слитный формат из 6 цифр (090404)
        flat_code_match = re.search(r'\b\d{6}\b', normalized_text)
        if flat_code_match:
            c = flat_code_match.group(0)
            code = f"{c[0:2]}.{c[2:4]}.{c[4:6]}"
            
    # В. РЕЗЕРВНЫЙ ПЛАН: Если кода нет, вытаскиваем его из шифра академической группы (ИКБО, ИКМО и т.д.)
    if not code:
        group_match = re.search(r'\bИК[А-Я]{2}-\d{2}-\d{2}\b', normalized_text, re.IGNORECASE)
        if not group_match:
            group_match = re.search(r'\bИК[А-Я]{2}-\d{2}-\d{2}\b', full_document_text, re.IGNORECASE)
            
        if group_match:
            group_name = group_match.group(0).upper()
            if "КМО" in group_name or "МППО" in group_name:
                code = "09.04.04"
            elif "ППО" in group_name or "ББО" in group_name:
                code = "09.03.04"
                
    if not code:
        code = "00.00.00"

    # 2. Поиск года
    year_match = re.search(r'\b(202[0-9]|201[0-9])\b', normalized_text)
    if not year_match:
        year_match = re.search(r'\b(202[0-9]|201[0-9])\b', full_document_text)
    year = year_match.group(0) if year_match else "2026"

    # 3. ОПРЕДЕЛЕНИЕ ТИПА И НАЗВАНИЯ ДОКУМЕНТА
    doc_type = "Документ"
    title = "Без_названия"

    # Проверяем стандартные маркеры кафедры по очищенному тексту
    if "рабочая программа" in text_lower or "рпд" in text_lower or "rpd" in text_lower:
        doc_type = "РПД"
    elif "фонд оценочных" in text_lower or "фос" in text_lower:
        doc_type = "ФОС"
    elif "аннотация" in text_lower:
        doc_type = "Аннотация"
    elif "заключение" in text_lower:
        doc_type = "Заключение"
    elif "практик" in text_lower:
        doc_type = "Практика"
    elif "вкр" in text_lower or "выпускная квалификационная" in text_lower or "диссертация" in text_lower:
        doc_type = "ВКР"

    # Поиск темы/названия по ключевым фразам
    theme_match = re.search(r'(?:тему|тема|дисциплины|дисциплине|по|название|программа)\s+["«]?([А-Яа-яЁёA-Za-z0-9\s\-,.]{3,120})["»]?', normalized_text, re.IGNORECASE | re.UNICODE)
    
    if theme_match:
        title = theme_match.group(1).strip()
    else:
        # Универсальный хантинг по CapsLock, если ключевых фраз не нашлось
        uppercase_strings = re.findall(r'\b[А-ЯЁ]{4,60}(?:\s+[А-ЯЁ]{2,60})*\b', normalized_text, re.UNICODE)
        ignored_words = ["МИНОБРНАУКИ", "РОССИИ", "УНИВЕРСИТЕТ", "ИНСТИТУТ", "КАФЕДРА", "РТУ", "МИРЭА"]
        valid_titles = [s for s in uppercase_strings if not any(ignored in s for ignored in ignored_words)]
        
        if valid_titles:
            title = valid_titles[0].strip()
            if doc_type == "Документ":
                doc_type = title.capitalize()

    # Фикс для видов практик ({вид})
    practice_type = "Учебная"
    if "преддиплом" in text_lower or "преддиплом" in full_text_lower_global:
        practice_type = "Преддипломная"
    elif "производствен" in text_lower or "производствен" in full_text_lower_global:
        practice_type = "Производственная"
    elif "научно-исслед" in text_lower or "нир" in text_lower or "нир" in full_text_lower_global:
        practice_type = "НИР"

    return {
        "тип": doc_type,
        "код": code,
        "год": year,
        "вид": practice_type,
        "название": clean_title(title)
    }

def apply_template(template: str, info: dict) -> str:
    result = template
    for key, value in info.items():
        result = result.replace(f"{{ {key} }}".replace(" ", ""), str(value))
    result = re.sub(r'[\\/*?:"<>|]', "", result)
    return result.strip() if result.strip() else "Обработанный_документ"

@app.get("/logo.png")
async def get_logo():
    if os.path.exists("logo.png"):
        return FileResponse("logo.png")
    return HTTPException(status_code=404, detail="Logo not found")

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
                --glass-bg: rgba(255, 255, 255, 0.55);
                --glass-border: rgba(255, 255, 255, 0.5);
                --error-red: #ff3b30;
            }

            html, body {
                width: 100%;
                max-width: 100%;
                overflow-x: hidden;
            }

            body {
                font-family: '-apple-system', BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: radial-gradient(circle at 20% 20%, rgba(0, 132, 255, 0.3) 0%, transparent 40%),
                            radial-gradient(circle at 80% 80%, rgba(0, 132, 255, 0.2) 0%, transparent 50%),
                            linear-gradient(135deg, #eef2f7 0%, #d5dadf 100%);
                background-attachment: fixed;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: flex-start;
                min-height: 100vh;
                margin: 0;
                padding: 40px 15px 60px 15px;
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
                backdrop-filter: blur(40px) saturate(200%);
                -webkit-backdrop-filter: blur(40px) saturate(200%);
                border: 1px solid var(--glass-border);
                border-radius: 32px;
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
                margin-bottom: 20px;
            }
            .drop-zone:hover, .drop-zone.dragover {
                background: rgba(255, 255, 255, 0.5);
                border-color: var(--primary-blue);
            }
            .drop-zone svg {
                stroke: var(--primary-blue);
                margin-bottom: 12px;
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
            }
            label { display: block; font-size: 11px; color: rgba(0,0,0,0.6); margin-bottom: 8px; font-weight: 700; text-transform: uppercase; }
            
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
            
            button[type="submit"] {
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
            button[type="submit"]:hover:not(:disabled) { 
                background: linear-gradient(180deg, #1e1e20 0%, #000000 100%);
            }
            button[type="submit"]:disabled { 
                background: rgba(0, 0, 0, 0.05); 
                color: rgba(0, 0, 0, 0.25); 
                border: none;
                cursor: not-allowed; 
                box-shadow: none; 
            }
            
            #file-list { 
                text-align: left; 
                max-height: 240px; 
                overflow-y: auto; 
                margin-top: 5px;
                margin-bottom: 20px;
                font-size: 13px;
                display: flex;
                flex-direction: column;
                gap: 8px;
                width: 100%;
            }
            .file-item { 
                display: flex !important;
                justify-content: space-between !important;
                align-items: center !important;
                padding: 10px 14px; 
                background: rgba(255, 255, 255, 0.7) !important; 
                border-left: 4px solid var(--primary-blue); 
                border-radius: 12px; 
                color: var(--primary-black); 
                font-weight: 500; 
                backdrop-filter: blur(5px);
                box-sizing: border-box;
                width: 100% !important;
                min-width: 0 !important;
            }
            .file-name {
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                margin-right: 12px;
                flex-grow: 1;
                min-width: 0 !important;
            }
            
            .file-delete-btn {
                display: inline-flex !important;
                align-items: center;
                justify-content: center;
                color: var(--error-red) !important;
                background: rgba(255, 59, 48, 0.08) !important;
                padding: 6px 12px !important;
                font-size: 11px !important;
                font-weight: 700 !important;
                text-transform: uppercase !important;
                letter-spacing: 0.5px !important;
                border-radius: 8px !important;
                cursor: pointer !important;
                user-select: none;
                transition: all 0.2s ease;
                border: 1px solid rgba(255, 59, 48, 0.15) !important;
                flex-shrink: 0 !important;
            }
            .file-delete-btn:hover {
                background: var(--error-red) !important;
                color: #ffffff !important;
                border-color: var(--error-red) !important;
            }

            .instruction-card {
                background: rgba(255, 255, 255, 0.35);
                backdrop-filter: blur(25px) saturate(160%);
                -webkit-backdrop-filter: blur(25px) saturate(160%);
                border: 1px solid rgba(255, 255, 255, 0.4);
                border-radius: 24px;
                padding: 25px 30px;
                width: 100%;
                max-width: 500px;
                box-sizing: border-box;
                margin-top: 25px;
                box-shadow: 0 15px 35px rgba(0, 40, 80, 0.04);
                text-align: left;
                z-index: 1;
            }
            .instruction-card h4 { margin: 0 0 15px 0; color: var(--primary-black); font-size: 14px; font-weight: 700; }
            .instruction-step { font-size: 13px; color: rgba(13, 13, 14, 0.7); margin-bottom: 10px; line-height: 1.4; }
            .instruction-grid { margin-top: 15px; padding-top: 15px; border-top: 1px solid rgba(0,0,0,0.06); font-size: 12px; display: flex; flex-direction: column; gap: 8px; }
            .instruction-grid code { display: block; background: rgba(255, 255, 255, 0.5); border: 1px solid rgba(255,255,255,0.4); padding: 8px 12px; border-radius: 8px; margin-top: 4px; font-family: 'SF Mono', monospace; color: var(--primary-black); font-size: 11.5px; word-break: break-all; }

            .page-footer { text-align: center; margin-top: 40px; font-size: 12px; color: rgba(13, 13, 14, 0.45); line-height: 1.6; z-index: 1; }
            .page-footer p { margin: 4px 0; }

            @media (max-width: 480px) {
                body { padding: 30px 10px 40px 10px; }
                .container { padding: 35px 20px; border-radius: 26px; }
                .instruction-card { padding: 20px; border-radius: 20px; }
                .header-block { flex-direction: column; gap: 8px; text-align: center; margin-bottom: 25px; }
                .title-group { text-align: center; }
                h1 { font-size: 20px; }
                .drop-zone { padding: 30px 15px; }
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
        
        <div class="drop-zone" id="drop-zone">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
            <div class="drop-zone-text">Выберите PDF-файлы или перетащите</div>
        </div>
        
        <input type="file" id="file-input" multiple accept=".pdf" style="display: none;">
        
        <div id="file-list"></div>

        <form id="upload-form">
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

    <div class="instruction-card">
        <h4>💡 Памятка по разбору документов</h4>
        <div class="instruction-step">
            <strong>{тип}</strong> — автоматически определяет категорию: РПД, Практика, ФОС, Заключение или название документа с листа.
        </div>
        <div class="instruction-step">
            <strong>{код}</strong> — извлекает шифр направления подготовки (например, 09.03.04, слитный 090404 или вычисляет по шифру группы).
        </div>
        
        <div class="instruction-grid">
            <div>
                <span>Исходный файл:</span>
                <code>rabochaya-programma-discipliny-2026-draft.pdf</code>
            </div>
            <div>
                <span>Результат по умолчанию:</span>
                <code>РПД_00.00.00_Без_названия_2026.pdf</code>
            </div>
        </div>
    </div>

    <div class="page-footer">
        <p>© 2026 Кафедра ИиППО. Все права защищены.</p>
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

        fileList.addEventListener('click', (e) => {
            if (e.target.classList.contains('file-delete-btn')) {
                const index = parseInt(e.target.getAttribute('data-index'), 10);
                selectedFiles.splice(index, 1);
                updateInterface();
            }
        });

        function updateInterface() {
            var htmlContent = '';
            for (var i = 0; i < selectedFiles.length; i++) {
                var file = selectedFiles[i];
                var displayIndex = i + 1;
                htmlContent += '<div class="file-item"><span class="file-name">' + displayIndex + '. ' + file.name + '</span><span class="file-delete-btn" data-index="' + i + '">Удалить</span></div>';
            }
            fileList.innerHTML = htmlContent;
            submitBtn.disabled = selectedFiles.length === 0;
        }

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (selectedFiles.length === 0) return;

            const formData = new FormData();
            selectedFiles.forEach(file => formData.append('files', file));
            formData.append('template', document.getElementById('template-input').value);

            submitBtn.textContent = 'Распознавание и сборка...';
            submitBtn.disabled = true;

            try {
                const response = await fetch('/api/rename', {
                    method: 'POST',
                    body: formData
                });
                if (!response.ok) throw new Error('Ошибка обработки файлов');

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