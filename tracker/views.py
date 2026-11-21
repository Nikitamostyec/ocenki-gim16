import csv
import io
import re
from datetime import date
from urllib.parse import quote

import openpyxl
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from .models import SavedLesson


def _get_state(request):
    if 'lesson' not in request.session:
        request.session['lesson'] = {
            'students': [],
            'history': [],
            'raw_rows': [],
            'columns': [],
            'selected_col': 0,
            'pending': [],
            'ee': {'enabled': False, 'threshold': 4, 'message': 'Нужно подтянуть!'}
        }
    return request.session['lesson']


def _save_state(request, state):
    request.session['lesson'] = state
    request.session.modified = True


def _calc_grade(student):
    if not student.get('touched') or student.get('points', 0) == 0:
        return ''
    if student['points'] == 1:
        return 2
    return min(student['points'], 10)


def _extract_surname_and_name(row, col_idx):
    skip_words = {
        'фио', 'фамилия', 'имя', 'отчество', 'ученик', 'обучающийся',
        'список', 'класс', 'итого', 'средний', 'дата', 'номер', 'статус'
    }
    if col_idx >= len(row):
        return ''

    raw_cell = str(row[col_idx] or '').strip()
    if not raw_cell or raw_cell.isdigit():
        return ''

    words = re.findall(r'[А-ЯЁа-яёA-Za-z]+(?:-[А-ЯЁа-яёA-Za-z]+)?', raw_cell)
    words = [w for w in words if len(w) > 1 and w.lower() not in skip_words]

    if not words:
        return ''

    if len(words) == 1 and (col_idx + 1) < len(row):
        next_cell = str(row[col_idx + 1] or '').strip()
        next_words = re.findall(r'[А-ЯЁа-яёA-Za-z]+(?:-[А-ЯЁа-яёA-Za-z]+)?', next_cell)
        next_words = [w for w in next_words if len(w) > 1 and w.lower() not in skip_words]
        if next_words:
            return f"{next(iter(words)).capitalize()} {next(iter(next_words)).capitalize()}"
        return ''

    if len(words) >= 2:
        it = iter(words)
        return f"{next(it).capitalize()} {next(it).capitalize()}"

    return ''


def _build_preview(rows, col_idx):
    result = []
    for row in rows:
        name = _extract_surname_and_name(row, col_idx)
        if name:
            result.append(name)
    return result[:30]


def _detect_columns(rows):
    if not rows:
        return [], 0
    max_cols = max(len(r) for r in rows[:15])
    columns = []
    best_col = 0
    best_score = -1

    for c in range(max_cols):
        sample = ''
        valid_count = 0
        for r in rows[:25]:
            if c < len(r) and r[c] is not None:
                val = str(r[c]).strip()
                if val and not sample:
                    sample = val[:20]
            if _extract_surname_and_name(r, c):
                valid_count += 1

        label = f'Столбец {c + 1}' + (f' ({sample})' if sample else ' (пусто)')
        columns.append({'idx': c, 'label': label})
        if valid_count > best_score:
            best_score = valid_count
            best_col = c

    return columns, best_col


def _write_styled_sheet(ws, rows_data):
    ws.append(['Фамилия Имя', 'Оценка'])

    header_fill = PatternFill(start_color='1E3A8A', end_color='1E3A8A', fill_type='solid')
    header_font = Font(name='Calibri', size=12, bold=True, color='FFFFFF')
    cell_font = Font(name='Calibri', size=11)
    zebra_fill = PatternFill(start_color='F8FAFC', end_color='F8FAFC', fill_type='solid')
    thin_side = Side(border_style='thin', color='CBD5E1')
    border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    ws.row_dimensions.height = 26
    for col_idx in range(1, 3):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center' if col_idx == 2 else 'left', vertical='center')
        cell.border = border

    for row_idx, item in enumerate(rows_data, start=2):
        ws.append([item['name'], item['grade']])
        ws.row_dimensions[row_idx].height = 22
        for col_idx in range(1, 3):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = cell_font
            cell.border = border
            cell.alignment = Alignment(horizontal='center' if col_idx == 2 else 'left', vertical='center')
            if row_idx % 2 == 1:
                cell.fill = zebra_fill

    for col in ws.columns:
        max_len = 0
        col_letter = next(iter(col)).column_letter
        for cell in col:
            val_len = len(str(cell.value or ''))
            if val_len > max_len:
                max_len = val_len
        ws.column_dimensions[col_letter].width = max(max_len + 6, 14)


def _excel_response(wb, raw_name):
    raw_name = re.sub(r'[\\/*?:"<>|]', '_', raw_name.strip())
    if not raw_name:
        raw_name = f'Оценки_{date.today().strftime("%d.%m.%Y")}'
    if not raw_name.lower().endswith('.xlsx'):
        raw_name += '.xlsx'

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)

    encoded_name = quote(raw_name)
    response = HttpResponse(
        out.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f"attachment; filename=\"ocenki.xlsx\"; filename*=UTF-8''{encoded_name}"
    return response


def index(request):
    teacher_code = request.session.get('teacher_code', '')
    if not teacher_code:
        return render(request, 'tracker/index.html', {'need_login': True})

    state = _get_state(request)
    ee = state['ee']
    students_view = []

    for s in state['students']:
        grade = _calc_grade(s)
        note = ''
        if ee['enabled'] and grade != '' and grade < int(ee['threshold']):
            note = ee['message']
        students_view.append({**s, 'grade': grade, 'note': note})

    today_lessons = SavedLesson.objects.filter(
        teacher_code=teacher_code,
        lesson_date=date.today()
    )

    return render(request, 'tracker/index.html', {
        'need_login': False,
        'teacher_code': teacher_code,
        'students': students_view,
        'has_history': len(state.get('history', [])) > 0,
        'pending': state.get('pending', []),
        'columns': state.get('columns', []),
        'selected_col': state.get('selected_col', 0),
        'ee': ee,
        'today_lessons': today_lessons,
        'today_str': date.today().strftime('%d.%m.%Y'),
        'default_filename': f'Класс_{date.today().strftime("%d.%m")}',
        'error': request.session.pop('import_error', None),
    })


def login_teacher(request):
    if request.method == 'POST':
        code = (request.POST.get('teacher_code') or '').strip().lower()
        if code:
            request.session['teacher_code'] = code
    return redirect('index')


def logout_teacher(request):
    request.session.pop('teacher_code', None)
    return redirect('index')


def import_file(request):
    if request.method == 'POST' and request.FILES.get('file'):
        uploaded = request.FILES['file']
        filename = uploaded.name.lower()
        raw = uploaded.read()
        try:
            if filename.endswith('.xlsx'):
                wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
                rows = [
                    [str(c).strip() if c is not None else '' for c in row]
                    for row in wb.active.iter_rows(values_only=True)
                ]
            elif filename.endswith('.csv'):
                text = None
                for enc in ('utf-8-sig', 'cp1251', 'utf-8'):
                    try:
                        text = raw.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
                if text is None:
                    raise ValueError('Не удалось прочитать кодировку CSV')
                first_line = next(iter(text.splitlines()), '')
                sep = ';' if ';' in first_line else ','
                rows = list(csv.reader(io.StringIO(text), delimiter=sep))
            else:
                raise ValueError('Поддерживаются только файлы .xlsx и .csv')

            rows = [r for r in rows if any(cell.strip() for cell in r)]
            columns, best_col = _detect_columns(rows)
            pending = _build_preview(rows, best_col)

            state = _get_state(request)
            state['raw_rows'] = rows[:45]
            state['columns'] = columns
            state['selected_col'] = best_col
            state['pending'] = pending
            _save_state(request, state)
        except Exception as e:
            request.session['import_error'] = str(e)
    return redirect('index')


def select_column(request):
    if request.method == 'POST':
        state = _get_state(request)
        col_idx = int(request.POST.get('col_idx', 0))
        state['selected_col'] = col_idx
        state['pending'] = _build_preview(state.get('raw_rows', []), col_idx)
        _save_state(request, state)
    return redirect('index')


def confirm_import(request):
    state = _get_state(request)
    if state.get('pending'):
        state['students'] = [
            {'id': i + 1, 'name': name, 'points': 0, 'touched': False}
            for i, name in enumerate(state['pending'])
        ]
        state['pending'] = []
        state['raw_rows'] = []
        state['columns'] = []
        state['history'] = []
        _save_state(request, state)
    return redirect('index')


def cancel_import(request):
    state = _get_state(request)
    state['pending'] = []
    state['raw_rows'] = []
    state['columns'] = []
    _save_state(request, state)
    return redirect('index')


def add_point(request, student_id):
    state = _get_state(request)
    for s in state['students']:
        if s['id'] == student_id:
            if s['points'] < 10:
                s['points'] += 1
                s['touched'] = True
                state.setdefault('history', []).append(student_id)
                if len(state['history']) > 50:
                    state['history'].pop(0)
            break

    _save_state(request, state)
    return redirect('index')


def undo(request):
    state = _get_state(request)
    history = state.get('history', [])
    if history:
        last_id = history.pop()
        for s in state['students']:
            if s['id'] == last_id:
                if s['points'] > 0:
                    s['points'] -= 1
                if s['points'] == 0:
                    s['touched'] = False
                break
        _save_state(request, state)
    return redirect('index')


def reset(request):
    state = _get_state(request)
    for s in state['students']:
        s['points'] = 0
        s['touched'] = False
    state['history'] = []
    _save_state(request, state)
    return redirect('index')


def clear_class(request):
    state = _get_state(request)
    state['students'] = []
    state['history'] = []
    state['pending'] = []
    state['raw_rows'] = []
    state['columns'] = []
    _save_state(request, state)
    return redirect('index')


def update_ee(request):
    if request.method == 'POST':
        state = _get_state(request)
        state['ee'] = {
            'enabled': request.POST.get('enabled') == 'on',
            'threshold': int(request.POST.get('threshold') or 4),
            'message': request.POST.get('message', 'Нужно подтянуть!'),
        }
        _save_state(request, state)
    return redirect('index')


def finish_lesson(request):
    teacher_code = request.session.get('teacher_code')
    if request.method == 'POST' and teacher_code:
        state = _get_state(request)
        students = state.get('students', [])
        if students:
            title = (request.POST.get('title') or '').strip() or f'Урок_{date.today().strftime("%d.%m")}'
            any_touched = any(s['touched'] for s in students)
            results = []
            for s in students:
                grade = '' if (not any_touched or not s['touched']) else _calc_grade(s)
                results.append({'name': s['name'], 'grade': grade})

            SavedLesson.objects.create(
                teacher_code=teacher_code,
                title=title,
                results_json=results
            )

            state['students'] = []
            state['history'] = []
            _save_state(request, state)
    return redirect('index')


def export_excel(request):
    state = _get_state(request)
    any_touched = any(s['touched'] for s in state['students'])
    raw_name = request.GET.get('filename') or f'Оценки_{date.today().strftime("%d.%m.%Y")}'

    rows_data = []
    for s in state['students']:
        grade = '' if (not any_touched or not s['touched']) else _calc_grade(s)
        rows_data.append({'name': s['name'], 'grade': grade})

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Оценки'
    _write_styled_sheet(ws, rows_data)
    return _excel_response(wb, raw_name)


def export_saved_lesson(request, lesson_id):
    teacher_code = request.session.get('teacher_code', '')
    lesson = get_object_or_404(SavedLesson, id=lesson_id, teacher_code=teacher_code)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = re.sub(r'[\\/*?:\[\]]', '_', lesson.title)[:30] or 'Оценки'
    _write_styled_sheet(ws, lesson.results_json)
    return _excel_response(wb, lesson.title)


def export_day_excel(request):
    teacher_code = request.session.get('teacher_code', '')
    lessons = list(SavedLesson.objects.filter(teacher_code=teacher_code, lesson_date=date.today()).order_by('created_at'))
    if not lessons:
        return redirect('index')

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    used_titles = set()
    for idx, lesson in enumerate(lessons, start=1):
        base_title = re.sub(r'[\\/*?:\[\]]', '_', lesson.title)[:25] or f'Урок_{idx}'
        sheet_title = base_title
        if sheet_title in used_titles:
            sheet_title = f"{base_title}_{idx}"
        used_titles.add(sheet_title)

        ws = wb.create_sheet(title=sheet_title)
        _write_styled_sheet(ws, lesson.results_json)

    return _excel_response(wb, f'Все_уроки_{date.today().strftime("%d.%m.%Y")}')


def delete_saved_lesson(request, lesson_id):
    teacher_code = request.session.get('teacher_code', '')
    SavedLesson.objects.filter(id=lesson_id, teacher_code=teacher_code).delete()
    return redirect('index')
