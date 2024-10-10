from flask import Flask, render_template, request, send_file
import os
from werkzeug.utils import secure_filename
from PIL import Image
import numpy as np
import shutil
import colorsys
import base64

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['PREVIEW_FOLDER'] = 'static/preview'
app.config['OUTPUT_FOLDER'] = 'static/output'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Создаем папки, если их нет
for folder in [app.config['UPLOAD_FOLDER'], app.config['PREVIEW_FOLDER'], app.config['OUTPUT_FOLDER']]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Проверка разрешенных расширений файлов
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Определение преобладающего цвета изображения
def get_dominant_color(image_path):
    image = Image.open(image_path).convert('RGB')
    image = image.resize((50, 50))
    data = np.array(image)
    data = data.reshape(-1, 3)
    data = data[np.any(data != [0, 0, 0], axis=1)]
    avg_color = np.mean(data, axis=0)
    return avg_color

# Преобразование RGB в HSV
def rgb_to_hsv(color):
    r, g, b = color / 255.0
    return colorsys.rgb_to_hsv(r, g, b)

# Определение цветовой категории по диапазонам оттенков
def get_color_category(hue_deg):
    hue_deg = hue_deg % 360
    if (hue_deg >= 0 and hue_deg < 15) or (hue_deg >= 345 and hue_deg <= 360):
        return 'Красный', 0
    elif hue_deg >= 15 and hue_deg < 45:
        return 'Оранжевый', 30
    elif hue_deg >= 45 and hue_deg < 75:
        return 'Желтый', 60
    elif hue_deg >= 75 and hue_deg < 150:
        return 'Зеленый', 120
    elif hue_deg >= 150 and hue_deg < 195:
        return 'Голубой', 180
    elif hue_deg >= 195 and hue_deg < 255:
        return 'Синий', 225
    elif hue_deg >= 255 and hue_deg < 345:
        return 'Фиолетовый', 300
    else:
        return 'Неопределенный', None

# Вычисление расстояния между оттенками
def hue_distance(hue1, hue2):
    if hue2 is None:
        return 360
    dh = min(abs(hue1 - hue2), 360 - abs(hue1 - hue2))
    return dh

# Маршрут для главной страницы
@app.route('/', methods=['GET', 'POST'])
def upload_files():
    if request.method == 'POST':
        # Очищаем папки перед загрузкой
        shutil.rmtree(app.config['UPLOAD_FOLDER'])
        os.makedirs(app.config['UPLOAD_FOLDER'])
        # Получаем параметры
        files = request.files.getlist('files[]')
        sorting_method = request.form.get('sorting_method')
        dominant_color = request.form.get('dominant_color')
        top_n = int(request.form.get('top_n', 0))
        images_per_row = int(request.form.get('images_per_row', 5))
        image_size = int(request.form.get('image_size', 100))

        # Сохраняем загруженные файлы
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        # Обрабатываем изображения
        image_paths = [os.path.join(app.config['UPLOAD_FOLDER'], f) for f in os.listdir(app.config['UPLOAD_FOLDER'])]
        image_data_list = []
        for path in image_paths:
            avg_color = get_dominant_color(path)
            hsv_color = rgb_to_hsv(avg_color)
            h_deg = hsv_color[0] * 360  # Hue в градусах
            category_name, category_center = get_color_category(h_deg)
            distance_to_center = hue_distance(h_deg, category_center)
            image_data_list.append({
                'path': path,
                'avg_color': avg_color,
                'hsv': hsv_color,
                'hue_deg': h_deg,
                'category': category_name,
                'distance_to_center': distance_to_center
            })

        # Сортируем изображения
        if sorting_method == 'spectrum':
            # Определяем порядок категорий
            spectrum_order = ['Красный', 'Оранжевый', 'Желтый', 'Зеленый', 'Голубой', 'Синий', 'Фиолетовый']
            # Создаем словарь для хранения изображений по категориям
            category_images_dict = {category: [] for category in spectrum_order}
            for img in image_data_list:
                if img['category'] in spectrum_order:
                    category_images_dict[img['category']].append(img)
            # Сортируем изображения внутри каждой категории
            sorted_images = []
            for category in spectrum_order:
                category_images = category_images_dict[category]
                category_images.sort(key=lambda x: x['distance_to_center'])
                sorted_images.extend(category_images)
            image_data_list = sorted_images
        elif sorting_method == 'top_n':
            # Определяем целевой оттенок
            color_hues = {
                'Красный': 0,
                'Оранжевый': 30,
                'Желтый': 60,
                'Зеленый': 120,
                'Голубой': 180,
                'Синий': 225,
                'Фиолетовый': 300
            }
            target_hue = color_hues.get(dominant_color, 0)

            # Вычисляем расстояние до целевого оттенка для всех изображений
            for img in image_data_list:
                img_hue = img['hue_deg']
                distance = hue_distance(img_hue, target_hue)
                img['distance'] = distance

            # Сортируем все изображения по расстоянию до целевого оттенка
            image_data_list.sort(key=lambda x: x['distance'])

            # Выбираем топ N изображений
            image_data_list = image_data_list[:top_n]

        # Сохраняем отсортированные изображения для предварительного просмотра
        shutil.rmtree(app.config['PREVIEW_FOLDER'])
        os.makedirs(app.config['PREVIEW_FOLDER'])
        image_filenames = []
        for idx, img_data in enumerate(image_data_list):
            img = Image.open(img_data['path'])
            img = img.resize((image_size, image_size))
            # Конвертируем изображение в режим RGB перед сохранением в JPEG
            if img.mode in ('RGBA', 'LA'):
                img = img.convert('RGB')
            filename = f'image_{idx}.jpg'
            img.save(os.path.join(app.config['PREVIEW_FOLDER'], filename), format='JPEG')
            image_filenames.append(filename)

        return render_template('preview.html', images=image_filenames,
                               images_per_row=images_per_row, image_size=image_size)
    return render_template('upload.html')

# Маршрут для генерации и скачивания HTML-страницы
@app.route('/generate', methods=['POST'])
def generate_html():
    images_per_row = int(request.form.get('images_per_row', 5))
    image_size = int(request.form.get('image_size', 100))
    image_filenames = request.form.get('image_filenames').split(',')


    images_base64 = []

    for image in image_filenames:
        image_path = os.path.join(app.config['PREVIEW_FOLDER'], image)
        with open(image_path, 'rb') as img_file:
            encoded_string = base64.b64encode(img_file.read()).decode('utf-8')
            # Определяем MIME-тип
            mime_type = 'image/jpeg'  # Мы сохраняем все изображения в формате JPEG
            data_uri = f"data:{mime_type};base64,{encoded_string}"
            images_base64.append(data_uri)

    # Создаем HTML-код
    html_content = render_template('output.html', images=images_base64,
                                   images_per_row=images_per_row, image_size=image_size)
    output_html_path = os.path.join(app.config['OUTPUT_FOLDER'], 'output.html')
    with open(output_html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    # Отправляем HTML-файл для скачивания
    return send_file(output_html_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
