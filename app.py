import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import List
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="MIREA File Renamer")

# Разрешаем CORS на случай интеграций
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TRANSLIT_DICT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
    'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
    'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
    'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Shch',
    'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
}

def transliterate(text: str) -> str:
    text = text.replace(' ', '_')
    res = "".join(TRANSLIT_DICT.get(char, char) for char in text)
    res = re.sub(r'[^A-Za-z0-9_]', '', res)
    return re.sub(r'_+', '_', res).strip('_')

# Главная страница с красивым интерфейсом Drag-and-Drop
@app.get("/", response_class=HTMLResponse)
async def get_index():
    html_content = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Конвертер файлов МИРЭА</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
            body { background: #f4f6f9; display: flex; justify-content: center; align-items: center; min-height: 100vh; color: #333; }
            .container { background: #ffffff; padding: 40px; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.05); width: 100%; max-width: 600px; text-align: center; }
            h1 { font-size: 24px; font-weight: 700; margin-bottom: 8px; color: #1e293b; }
            p.subtitle { color: #64748b; font-size: 14px; margin-bottom: 30px; }
            
            .drop-zone { border: 2px dashed #cbd5e1; border-radius: 12px; padding: 40px 20px; cursor: pointer; transition: all 0.3s ease; background: #f8fafc; position: relative; }
            .drop-zone:hover, .drop-zone.dragover { border-color: #3b82f6; background: #eff6ff; }
            .drop-zone svg { width: 48px; height: 48px; color: #94a3b8; margin-bottom: 16px; transition: color 0.3s; }
            .drop-zone:hover svg, .drop-zone.dragover svg { color: #3b82f6; }
            .drop-zone p { font-size: 15px; font-weight: 500; color: #475569; }
            .drop-zone span { font-size: 13px; color: #94a3b8; display: block; margin-top: 6px; }
            
            #file-input { display: none; }
            
            .file-list { margin-top: 24px; text-align: left; max-height: 180px; overflow-y: auto; display: none; }
            .file-item { background: #f1f5f9; padding: 10px 14px; border-radius: 8px; font-size: 13px; color: #334155; display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
            .file-item span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 85%; }
            
            .btn { display: inline-block; width: 100%; background: #3b82f6; color: white; padding: 14px; border: none; border-radius: 12px; font-size: 16px; font-weight: 600; margin-top: 24px; cursor: pointer; transition: background 0.3s; display: none; }
            .btn:hover { background: #2563eb; }
            .btn:disabled { background: #94a3b8; cursor: not-allowed; }
            
            .loader { display: none; margin: 20px auto 0; border: 4px solid #f3f3f3; border-top: 4px solid #3b82f6; border-radius: 50%; width: 30px; height: 30px; animation: spin 1s linear infinite; }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Конвертер названий РПД и практик</h1>
            <p class="subtitle">Перетащите файлы .pdf для автоматического переименования</p>
            
            <div class="drop-zone" id="drop-zone">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p>Выберите файлы или перетащите их сюда</p>
                <span>Поддерживаются только документы .pdf</span>
                <input type="file" id="file-input" multiple accept=".pdf">
            </div>
            
            <div class="file-list" id="file-list"></div>
            <div class="loader" id="loader"></div>
            <button class="btn" id="upload-btn">Переименовать и скачать архив</button>
        </div>

        <script>
            const dropZone = document.getElementById('drop-zone');
            const fileInput = document.getElementById('file-input');
            const fileList = document.getElementById('file-list');
            const uploadBtn = document.getElementById('upload-btn');
            const loader = document.getElementById('loader');
            let selectedFiles = [];

            dropZone.addEventListener('click', () => fileInput.click());

            dropZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropZone.classList.add('dragover');
            });

            dropZone.addEventListener('dragleave', () => {
                dropZone.classList.remove('dragover');
            });

            dropZone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropZone.classList.remove('dragover');
                handleFiles(e.dataTransfer.files);
            });

            fileInput.addEventListener('change', () => {
                handleFiles(fileInput.files);
            });

            function handleFiles(files) {
                const filtered = Array.from(files).filter(file => file.name.endsWith('.pdf'));
                if (filtered.length === 0) return;
                
                selectedFiles = [...selectedFiles, ...filtered];
                updateInterface();
            }

            function updateInterface() {
                fileList.innerHTML = '';
                if (selectedFiles.length > 0) {
                    fileList.style.display = 'block';
                    uploadBtn.style.style = 'block';
                    uploadBtn.style.display = 'inline-block';
                    
                    selectedFiles.forEach((file, index) => {
                        const item = document.createElement('div');
                        item.className = 'file-item';
                        item.innerHTML = `<span>📄 ${file.name}</span><b style="color:#ef4444; cursor:pointer;" onclick="removeFile(${index})">✕</b>`;
                        fileList.appendChild(item);
                    });
                } else {
                    fileList.style.display = 'none';
                    uploadBtn.style.display = 'none';
                }
            }

            window.removeFile = function(index) {
                selectedFiles.splice(index, 1);
                updateInterface();
            }

            uploadBtn.addEventListener('click', async () => {
                if (selectedFiles.length === 0) return;
                
                uploadBtn.disabled = true;
                loader.style.display = 'block';
                
                const formData = new FormData();
                selectedFiles.forEach(file => {
                    formData.append('files', file);
                });
                
                try {
                    const response = await fetch('/rename-batch', {
                        method: 'POST',
                        body: formData
                    });
                    
                    if (response.ok) {
                        // Скачиваем полученный ZIP архив
                        const blob = await response.blob();
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = "converted_files.zip";
                        document.body.appendChild(a);
                        a.click();
                        a.remove();
                        
                        // Сброс интерфейса
                        selectedFiles = [];
                        updateInterface();
                    } else {
                        alert('Произошла ошибка при обработке файлов.');
                    }
                } catch (error) {
                    console.error(error);
                    alert('Не удалось связаться с сервером.');
                } finally {
                    uploadBtn.disabled = false;
                    loader.style.display = 'none';
                }
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# Эндпоинт пакетной обработки файлов
@app.post("/rename-batch")
async def rename_batch(files: List[UploadFile] = File(...)):
    # Шаблон для разбора структуры имени файла
    pattern = re.compile(r"^(\d{2})[\._](\d{2})[\._](\d{2})_([А-Яа-яA-Za-z0-9]+)_([А-Яа-яA-Za-z0-9]+)_(\d{4})_plx_(.+)$")
    
    # Создаем временные директории
    temp_dir = Path("temp_processing")
    temp_dir.mkdir(exist_ok=True)
    
    zip_path = Path("converted_files.zip")
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, 'w') as zip_file:
        for file in files:
            filename = Path(file.filename).stem.strip()
            suffix = Path(file.filename).suffix
            
            match = pattern.match(filename)
            
            if match:
                ch1, ch2, ch3, profile_raw, institute_raw, year, subject_raw = match.groups()
                code = f"{ch1}.{ch2}.{ch3}"
                
                # Автоопределение типа по названию дисциплины
                if "практика" in subject_raw.lower() or "prakt" in filename.lower():
                    prefix = "prakt"
                else:
                    prefix = "rpd"
                
                # Транслитерация
                profile = transliterate(profile_raw)
                institute = transliterate(institute_raw)
                subject = transliterate(subject_raw)
                
                new_filename = f"{prefix}_{code}_{profile}_{subject}_{institute}_{year}{suffix}"
            else:
                # Если имя не по шаблону МИРЭА, просто делаем ему транслит и чистку
                new_filename = transliterate(filename) + suffix

            # Сохраняем файл временно
            target_path = temp_dir / new_filename
            with target_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Кладем файл в архив
            zip_file.write(target_path, arcname=new_filename)
            # Удаляем временный файл
            target_path.unlink()

    # Удаляем временную папку
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
        
    return FileResponse(path=zip_path, filename="converted_files.zip", media_type="application/zip")


if __name__ == "__main__":
    import uvicorn
    # Запуск локально
    uvicorn.run(app, host="0.0.0.0", port=8000)